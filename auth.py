"""
GradesGenie — Authentication.

Google OAuth for login + Firebase phone OTP for signup verification.
Session cookie persists 30 days.
"""

import functools
import hashlib
import logging
import os
import secrets
from datetime import datetime, timedelta

from flask import redirect, request, session, jsonify, url_for

import db
from config import (
    GOOGLE_CLIENT_ID,
    GOOGLE_CLIENT_SECRET,
    SESSION_DURATION_DAYS,
    TRIAL_DURATION_DAYS,
    MAX_SIGNUPS_PER_IP,
)

logger = logging.getLogger(__name__)


# ─── Session Helpers ───


def get_current_student():
    """Return the current student dict from session, or None."""
    student_id = session.get("student_id")
    if not student_id:
        return None
    return db.get_student(student_id)


def require_auth(f):
    """Decorator: redirect to login if not authenticated."""
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        student = get_current_student()
        if not student:
            if request.is_json or request.path.startswith("/api/"):
                return jsonify({"error": "Not logged in", "redirect": "/login"}), 401
            return redirect("/login")
        # Check trial/plan status
        plan = student.get("plan", "free_trial")
        if plan == "expired":
            if request.is_json or request.path.startswith("/api/"):
                return jsonify({"error": "Trial expired", "redirect": "/subscribe"}), 403
            return redirect("/subscribe")
        if plan == "free_trial":
            trial_start = datetime.fromisoformat(student["trial_start"])
            if datetime.now() > trial_start + timedelta(days=TRIAL_DURATION_DAYS):
                db.update_student_plan(student["id"], "expired")
                if request.is_json or request.path.startswith("/api/"):
                    return jsonify({"error": "Trial expired", "redirect": "/subscribe"}), 403
                return redirect("/subscribe")
        request.student = student
        return f(*args, **kwargs)
    return decorated


# ─── Google OAuth Routes ───


def register_auth_routes(app):
    """Register all auth-related routes on the Flask app."""

    @app.route("/login")
    def login_page():
        """Show login page with Google sign-in button."""
        if get_current_student():
            return redirect("/")
        return app.send_static_file("login.html") if os.path.exists(
            os.path.join(app.static_folder, "login.html")
        ) else _login_html()

    @app.route("/auth/google/callback", methods=["POST"])
    def google_callback():
        """Verify Google ID token and create/login user."""
        try:
            from google.oauth2 import id_token
            from google.auth.transport import requests as google_requests

            token = request.json.get("credential") or request.form.get("credential")
            if not token:
                return jsonify({"error": "No credential provided"}), 400

            idinfo = id_token.verify_oauth2_token(
                token, google_requests.Request(), GOOGLE_CLIENT_ID
            )

            google_id = idinfo["sub"]
            email = idinfo.get("email", "")
            name = idinfo.get("name", "")
            avatar = idinfo.get("picture", "")

            # Check if student exists
            student = db.get_student_by_google_id(google_id)

            if student:
                # Existing user — log them in
                session["student_id"] = student["id"]
                session.permanent = True
                logger.info(f"Login: {email}")
                return jsonify({"status": "ok", "needs_phone": False})
            else:
                # New user — need phone verification
                session["pending_google_id"] = google_id
                session["pending_email"] = email
                session["pending_name"] = name
                session["pending_avatar"] = avatar
                return jsonify({"status": "ok", "needs_phone": True})

        except ValueError as e:
            logger.warning(f"Google auth failed: {e}")
            return jsonify({"error": "Invalid Google token"}), 401

    @app.route("/verify-phone")
    def verify_phone_page():
        """Show phone verification page for new signups."""
        if not session.get("pending_google_id"):
            return redirect("/login")
        from config import FIREBASE_API_KEY
        return f"""<!DOCTYPE html>
<html><head><title>GradesGenie — Verify Phone</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<script src="https://www.gstatic.com/firebasejs/9.23.0/firebase-app-compat.js"></script>
<script src="https://www.gstatic.com/firebasejs/9.23.0/firebase-auth-compat.js"></script>
</head><body style="display:flex;align-items:center;justify-content:center;min-height:100vh;font-family:system-ui;background:#f9fafb">
<div style="text-align:center;max-width:400px;padding:2rem">
<h1 style="font-size:1.5rem;margin-bottom:0.5rem">Verify Your Phone</h1>
<p style="color:#6b7280;margin-bottom:1.5rem">One-time verification to prevent abuse</p>
<div id="step1">
  <input id="phoneInput" type="tel" placeholder="+91 98765 43210"
    style="width:100%;padding:0.75rem;border:1px solid #d1d5db;border-radius:8px;font-size:1rem;margin-bottom:1rem">
  <div id="recaptcha-container"></div>
  <button onclick="sendOTP()" id="sendBtn"
    style="width:100%;padding:0.75rem;background:#4285f4;color:white;border:none;border-radius:8px;font-size:1rem;cursor:pointer;margin-top:1rem">
    Send OTP</button>
</div>
<div id="step2" style="display:none">
  <input id="otpInput" type="text" placeholder="6-digit OTP" maxlength="6"
    style="width:100%;padding:0.75rem;border:1px solid #d1d5db;border-radius:8px;font-size:1rem;margin-bottom:1rem;text-align:center;letter-spacing:0.5em">
  <button onclick="verifyOTP()" id="verifyBtn"
    style="width:100%;padding:0.75rem;background:#34a853;color:white;border:none;border-radius:8px;font-size:1rem;cursor:pointer">
    Verify</button>
</div>
<p id="msg" style="color:#ef4444;margin-top:1rem"></p>
<script>
firebase.initializeApp({{apiKey: "{FIREBASE_API_KEY}", authDomain: "gradesgenie.firebaseapp.com"}});
const auth = firebase.auth();
let confirmationResult;
window.recaptchaVerifier = new firebase.auth.RecaptchaVerifier('recaptcha-container', {{size: 'normal'}});
function sendOTP() {{
    const phone = document.getElementById('phoneInput').value.trim();
    if (!phone.startsWith('+')) {{ document.getElementById('msg').textContent = 'Include country code, e.g. +91...'; return; }}
    document.getElementById('sendBtn').disabled = true;
    document.getElementById('sendBtn').textContent = 'Sending...';
    auth.signInWithPhoneNumber(phone, window.recaptchaVerifier)
        .then(r => {{ confirmationResult = r; document.getElementById('step1').style.display='none'; document.getElementById('step2').style.display='block'; }})
        .catch(e => {{ document.getElementById('msg').textContent = e.message; document.getElementById('sendBtn').disabled = false; document.getElementById('sendBtn').textContent = 'Send OTP'; }});
}}
function verifyOTP() {{
    const code = document.getElementById('otpInput').value.trim();
    document.getElementById('verifyBtn').disabled = true;
    document.getElementById('verifyBtn').textContent = 'Verifying...';
    confirmationResult.confirm(code).then(result => {{
        return result.user.getIdToken();
    }}).then(idToken => {{
        return fetch('/auth/verify-phone', {{
            method: 'POST',
            headers: {{'Content-Type': 'application/json'}},
            body: JSON.stringify({{id_token: idToken}})
        }});
    }}).then(r => r.json()).then(data => {{
        if (data.error) {{ document.getElementById('msg').textContent = data.error; document.getElementById('verifyBtn').disabled = false; document.getElementById('verifyBtn').textContent = 'Verify'; }}
        else window.location = '/';
    }}).catch(e => {{ document.getElementById('msg').textContent = e.message; document.getElementById('verifyBtn').disabled = false; document.getElementById('verifyBtn').textContent = 'Verify'; }});
}}
</script>
</div></body></html>"""

    @app.route("/auth/verify-phone", methods=["POST"])
    def verify_phone():
        """Verify Firebase phone OTP token and complete signup."""
        google_id = session.get("pending_google_id")
        if not google_id:
            return jsonify({"error": "Start with Google sign-in first"}), 400

        phone_token = request.json.get("id_token")
        if not phone_token:
            return jsonify({"error": "No phone token"}), 400

        try:
            import firebase_admin
            from firebase_admin import auth as firebase_auth

            # Initialize Firebase if not already done
            if not firebase_admin._apps:
                firebase_admin.initialize_app()

            decoded = firebase_auth.verify_id_token(phone_token)
            phone = decoded.get("phone_number", "")

            if not phone:
                return jsonify({"error": "No phone number in token"}), 400

            # Check if phone already registered
            existing = db.get_student_by_phone(phone)
            if existing:
                return jsonify({
                    "error": "Phone already registered. Sign in with your original Google account.",
                    "existing_email": existing.get("email", "")[:3] + "***"
                }), 409

            # Anti-abuse: check signups from this IP
            client_ip = request.headers.get("X-Forwarded-For", request.remote_addr)
            recent_signups = db.count_recent_signups_from_ip(client_ip, days=7)
            if recent_signups >= MAX_SIGNUPS_PER_IP:
                return jsonify({"error": "Too many signups from this network. Try later."}), 429

            # Create the student
            student_id = db.create_student(
                google_id=google_id,
                email=session.get("pending_email", ""),
                name=session.get("pending_name", ""),
                avatar_url=session.get("pending_avatar", ""),
                phone=phone,
                signup_ip=client_ip,
            )

            # Clear pending state, set session
            session.pop("pending_google_id", None)
            session.pop("pending_email", None)
            session.pop("pending_name", None)
            session.pop("pending_avatar", None)
            session["student_id"] = student_id
            session.permanent = True

            logger.info(f"New signup: {session.get('pending_email', '')} / {phone}")
            return jsonify({"status": "ok", "student_id": student_id})

        except Exception as e:
            logger.error(f"Phone verification failed: {e}", exc_info=True)
            return jsonify({"error": "Phone verification failed. Try again."}), 500

    @app.route("/auth/logout")
    def logout():
        session.clear()
        return redirect("/login")

    @app.route("/subscribe")
    def subscribe_page():
        """Show subscription page when trial expires."""
        return "<h1>Trial ended</h1><p>Contact us on WhatsApp to subscribe (₹499/month)</p>"


def _login_html():
    """Minimal login page if static/login.html doesn't exist."""
    return f"""<!DOCTYPE html>
<html><head><title>GradesGenie — Login</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<script src="https://accounts.google.com/gsi/client" async></script>
</head><body style="display:flex;align-items:center;justify-content:center;min-height:100vh;font-family:system-ui;background:#f9fafb">
<div style="text-align:center;max-width:400px;padding:2rem">
<h1 style="font-size:2rem;margin-bottom:0.5rem">GradesGenie</h1>
<p style="color:#6b7280;margin-bottom:2rem">AI tutor that finds exactly where your child goes wrong</p>
<div id="g_id_onload"
     data-client_id="{GOOGLE_CLIENT_ID}"
     data-callback="handleCredentialResponse"
     data-auto_prompt="false"></div>
<div class="g_id_signin" data-type="standard" data-size="large" data-theme="outline" data-text="sign_in_with" data-shape="rectangular"></div>
<script>
function handleCredentialResponse(response) {{
    fetch('/auth/google/callback', {{
        method: 'POST',
        headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify({{credential: response.credential}})
    }}).then(r => r.json()).then(data => {{
        if (data.needs_phone) window.location = '/verify-phone';
        else window.location = '/';
    }});
}}
</script>
</div></body></html>"""
