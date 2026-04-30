"""Tests for auth.py — Google OAuth, phone OTP, session, trial gating."""

import sys
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

import pytest

# Mock firebase_admin module since it's not installed locally
_mock_firebase_admin = MagicMock()
_mock_firebase_auth = MagicMock()
_mock_firebase_admin.auth = _mock_firebase_auth
_mock_firebase_admin._apps = {}
sys.modules.setdefault("firebase_admin", _mock_firebase_admin)
sys.modules.setdefault("firebase_admin.auth", _mock_firebase_auth)


class TestRequireAuth:
    def test_unauthenticated_api_returns_401(self, app_client):
        resp = app_client.get("/api/progress")
        assert resp.status_code == 401
        data = resp.get_json()
        assert "Not logged in" in data["error"]

    def test_unauthenticated_page_redirects_to_login(self, app_client):
        # /pc requires auth now — but actually /pc doesn't have @require_auth
        # Only /api/* routes have it. Test with /api/history
        resp = app_client.get("/api/history")
        assert resp.status_code == 401

    def test_authenticated_passes(self, authed_client):
        resp = authed_client.get("/api/progress")
        assert resp.status_code == 200

    def test_expired_trial_returns_403(self, authed_client, db_module):
        # Expire the student's trial
        student_id = authed_client._student_id
        db_module.update_student_plan(student_id, "expired")
        resp = authed_client.get("/api/progress")
        assert resp.status_code == 403
        data = resp.get_json()
        assert "Trial expired" in data["error"]

    def test_trial_auto_expires_after_duration(self, app_client, db_module):
        """Student whose trial_start is old gets auto-expired."""
        old_date = (datetime.now() - timedelta(days=15)).isoformat()
        conn = db_module.get_db()
        sid = db_module.create_student("gexp", "exp@test.com", "Expired", "", "+910000000099")
        conn = db_module.get_db()
        conn.execute("UPDATE students SET trial_start = ? WHERE id = ?", (old_date, sid))
        conn.commit()
        conn.close()

        with app_client.session_transaction() as sess:
            sess["student_id"] = sid

        resp = app_client.get("/api/progress")
        assert resp.status_code == 403

    def test_paid_user_passes(self, app_client, db_module):
        sid = db_module.create_student("gpaid", "paid@test.com", "Paid", "", "+910000000088")
        db_module.update_student_plan(sid, "paid", "2028-01-01")
        with app_client.session_transaction() as sess:
            sess["student_id"] = sid
        resp = app_client.get("/api/progress")
        assert resp.status_code == 200


class TestLoginPage:
    def test_login_page_renders(self, app_client):
        resp = app_client.get("/login")
        assert resp.status_code == 200
        assert b"GradesGenie" in resp.data

    def test_login_redirects_if_already_authed(self, authed_client):
        resp = authed_client.get("/login")
        assert resp.status_code == 302  # redirect to /


class TestGoogleCallback:
    @patch("google.oauth2.id_token.verify_oauth2_token")
    def test_existing_user_login(self, mock_verify, app_client, db_module):
        """Existing Google user logs in without phone verification."""
        # Create existing student
        db_module.create_student("gexist", "existing@test.com", "Existing", "", "+910000000077")

        # Mock Google token verification
        mock_verify.return_value = {
            "sub": "gexist",
            "email": "existing@test.com",
            "name": "Existing",
            "picture": "",
        }

        resp = app_client.post("/auth/google/callback",
                               json={"credential": "fake-token"},
                               content_type="application/json")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["needs_phone"] is False

    @patch("google.oauth2.id_token.verify_oauth2_token")
    def test_new_user_needs_phone(self, mock_verify, app_client):
        """New Google user gets needs_phone=True."""
        mock_verify.return_value = {
            "sub": "gnew123",
            "email": "new@test.com",
            "name": "New User",
            "picture": "http://pic.jpg",
        }

        resp = app_client.post("/auth/google/callback",
                               json={"credential": "fake-token"},
                               content_type="application/json")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["needs_phone"] is True

    def test_callback_no_credential(self, app_client):
        resp = app_client.post("/auth/google/callback",
                               json={},
                               content_type="application/json")
        assert resp.status_code == 400

    @patch("google.oauth2.id_token.verify_oauth2_token")
    def test_callback_invalid_token(self, mock_verify, app_client):
        """Invalid token returns 401."""
        mock_verify.side_effect = ValueError("Invalid token")
        resp = app_client.post("/auth/google/callback",
                               json={"credential": "bad-token"},
                               content_type="application/json")
        assert resp.status_code == 401


class TestPhoneVerification:
    def test_verify_phone_without_google_first(self, app_client):
        """Phone verify fails if Google OAuth not done first."""
        resp = app_client.post("/auth/verify-phone",
                               json={"id_token": "fake"},
                               content_type="application/json")
        assert resp.status_code == 400

    def test_verify_phone_duplicate(self, app_client, db_module):
        """Phone already registered returns 409."""
        db_module.create_student("gdup", "dup@test.com", "Dup", "", "+919111111111")

        _mock_firebase_admin._apps = {"default": True}
        _mock_firebase_auth.verify_id_token.return_value = {"phone_number": "+919111111111"}

        with app_client.session_transaction() as sess:
            sess["pending_google_id"] = "gnewdup"
            sess["pending_email"] = "newdup@test.com"
            sess["pending_name"] = "NewDup"
            sess["pending_avatar"] = ""

        resp = app_client.post("/auth/verify-phone",
                               json={"id_token": "phone-token"},
                               content_type="application/json")
        assert resp.status_code == 409

    def test_verify_phone_success(self, app_client, db_module):
        """Successful phone verification creates student."""
        _mock_firebase_admin._apps = {"default": True}
        _mock_firebase_auth.verify_id_token.return_value = {"phone_number": "+919222222222"}

        with app_client.session_transaction() as sess:
            sess["pending_google_id"] = "gnewuser"
            sess["pending_email"] = "newuser@test.com"
            sess["pending_name"] = "New User"
            sess["pending_avatar"] = ""

        resp = app_client.post("/auth/verify-phone",
                               json={"id_token": "phone-token"},
                               content_type="application/json")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "ok"
        assert "student_id" in data

    def test_verify_phone_rate_limit(self, app_client, db_module):
        """Too many signups from same IP returns 429."""
        # Create 2 students from same IP (MAX_SIGNUPS_PER_IP=2)
        db_module.create_student("grl1", "rl1@test.com", "RL1", "", "+919333333331", signup_ip="10.0.0.1")
        db_module.create_student("grl2", "rl2@test.com", "RL2", "", "+919333333332", signup_ip="10.0.0.1")

        _mock_firebase_admin._apps = {"default": True}
        _mock_firebase_auth.verify_id_token.return_value = {"phone_number": "+919333333333"}

        with app_client.session_transaction() as sess:
            sess["pending_google_id"] = "grl3"
            sess["pending_email"] = "rl3@test.com"
            sess["pending_name"] = "RL3"
            sess["pending_avatar"] = ""

        resp = app_client.post("/auth/verify-phone",
                               json={"id_token": "phone-token"},
                               content_type="application/json",
                               headers={"X-Forwarded-For": "10.0.0.1"})
        assert resp.status_code == 429


class TestLogout:
    def test_logout_clears_session(self, authed_client):
        resp = authed_client.get("/auth/logout")
        assert resp.status_code == 302

        # After logout, API should return 401
        resp = authed_client.get("/api/progress")
        assert resp.status_code == 401
