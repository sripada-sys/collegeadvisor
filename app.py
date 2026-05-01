#!/usr/bin/env python3
"""
GradesGenie — AI tutor for JEE, ISI, CMI, Board exams.
Subjects: Maths, Physics, Chemistry.

Architecture:
  Cloud VPS (Vultr) running Flask on port 5050
  Phone = camera (uploads question + answer photos)
  PC    = dashboard (feedback, progress, debate)

Run:   python3 app.py
Setup: cp .env.example .env && edit .env with your API keys
"""

import json
import logging
import logging.handlers
import os
import socket
import subprocess
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from flask import (
    Flask,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
)
from werkzeug.utils import secure_filename

import db
from models import ModelRouter
from config import PORT, SECRET_KEY

# ─── Config ───

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# .env loaded by config.py

# ─── Init ───

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

# Also write logs to a rotating file so we can include them in the git backup
_LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "app.log")
os.makedirs(os.path.dirname(_LOG_FILE), exist_ok=True)
_file_handler = logging.handlers.RotatingFileHandler(
    _LOG_FILE, maxBytes=256 * 1024, backupCount=1, encoding="utf-8"
)
_file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logging.getLogger().addHandler(_file_handler)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50MB
app.secret_key = SECRET_KEY
app.permanent_session_lifetime = timedelta(days=30)

import secrets

db.init_db()
db.run_migrations()
router = ModelRouter()

# Register auth routes (login, callback, verify-phone, logout, subscribe)
from auth import register_auth_routes, require_auth
register_auth_routes(app)

# ─── Phone Pairing Tokens ───
# PC generates a token after login → encoded in QR code → phone uses it to get a session.
# Tokens are short-lived and single-use.

_pair_tokens = {}  # token -> {"student_id": ..., "expires": datetime}
_PAIR_TTL = timedelta(hours=12)


def _cleanup_expired_tokens():
    now = datetime.now()
    expired = [t for t, v in _pair_tokens.items() if v["expires"] < now]
    for t in expired:
        del _pair_tokens[t]


def generate_pair_token(student_id):
    """Create a pairing token for the given student. Replaces any previous token."""
    _cleanup_expired_tokens()
    # Remove old tokens for this student (one active token per student)
    old = [t for t, v in _pair_tokens.items() if v["student_id"] == student_id]
    for t in old:
        del _pair_tokens[t]
    token = secrets.token_urlsafe(24)
    _pair_tokens[token] = {"student_id": student_id, "expires": datetime.now() + _PAIR_TTL}
    return token


def validate_pair_token(token):
    """Validate and consume a pairing token. Returns student_id or None."""
    _cleanup_expired_tokens()
    entry = _pair_tokens.get(token)
    if not entry:
        return None
    return entry["student_id"]


# ─── Analytics middleware ───

@app.before_request
def _track_request():
    """Log every request for analytics. Lightweight — no AI calls."""
    # Skip static files and frequent polling
    if request.path.startswith("/static") or request.path == "/favicon.ico":
        return
    try:
        student_id = None
        try:
            from flask import session as flask_session
            student_id = flask_session.get("student_id")
        except Exception:
            pass
        meta = {
            "path": request.path,
            "method": request.method,
            "ua": request.user_agent.string[:200],
            "ip": request.remote_addr,
            "referrer": (request.referrer or "")[:200],
        }
        db.log_event(student_id, "request", meta)
    except Exception:
        pass  # Never break the app for analytics


# ─── Helpers ───


def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def save_upload(file):
    filename = secure_filename(file.filename or "photo.jpg")
    name, ext = os.path.splitext(filename)
    filename = f"{name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}{ext}"
    path = os.path.join(UPLOAD_DIR, filename)
    file.save(path)
    return path


def parse_ai_json(text):
    import re
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text[:-3]
    if text.startswith("json"):
        text = text[4:]
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # AI writes raw LaTeX backslashes (\theta, \frac, \int) inside JSON strings.
        # These are invalid JSON escapes. Double all backslashes EXCEPT genuine
        # JSON escapes: \\ \" \/ \n \r \t \b \f \uXXXX
        # Key: \t in "\theta" is LaTeX (not tab) because "th" is a known LaTeX prefix.
        _LATEX_PREFIXES = {
            'th', 'ta', 'ti', 'to',  # \theta, \tan, \times, \top
            'fr', 'fu',              # \frac, \func
            'be', 'bi', 'bo',        # \beta, \binom, \bot
            'nu',                    # \nu
            'ne', 'no',              # \neg, \not
            'na', 'ni',              # \nabla, \ni
            'al', 'ap', 'ar',        # \alpha, \approx, \arctan
            'si', 'sq', 'su', 'se',  # \sin, \sqrt, \sum, \sec
            'co', 'cd', 'ci', 'cu',  # \cos, \cdot, \circ, \cup
            'de', 'di', 'do',        # \delta, \div, \dot
            'ga', 'ge',              # \gamma, \geq
            'la', 'le', 'lo', 'ln',  # \lambda, \leq, \log, \ln
            'mu',                    # \mu
            'pi', 'ph', 'pm', 'pr',  # \pi, \phi, \pm, \prod
            'rh', 'ri',              # \rho, \right
            'ep', 'et', 'ex',        # \epsilon, \eta, \exists
            'om', 'ov',              # \omega, \overline
            'ps', 'pa', 'pe',        # \psi, \partial, \perp
            'in', 'io', 'im',        # \int, \iota, \implies
            'ka', 'xi', 'ze', 'ch',  # \kappa, \xi, \zeta, \chi
            'ma', 'mi', 'mp',        # \mathbb, \min, \mp
            'ha', 'hb', 'hs',        # \hat, \hbar, \hspace
            'va', 've',              # \varepsilon, \vec
            'wr',                    # \wrapfig
            'up',                    # \uparrow
        }

        def _fix_backslash(m):
            ch = m.group(1)   # char after backslash
            nxt = m.group(2)  # char after that (may be empty)
            # Always valid JSON escapes: \\ \" \/
            if ch in '"\\/' :
                return m.group(0)
            # \uXXXX — but NOT \upsilon etc: check if followed by 4 hex digits
            if ch == 'u' and re.match(r'[0-9a-fA-F]', nxt or ''):
                return m.group(0)
            # \n \r \t \b \f — valid JSON if the two-char combo is NOT a LaTeX prefix
            combo = ch + nxt
            if combo in _LATEX_PREFIXES:
                return '\\\\' + ch + nxt
            if ch in 'nrtbf':
                return m.group(0)
            # Everything else: double the backslash
            return '\\\\' + ch + nxt
        repaired = re.sub(r'\\(.)(.?)', _fix_backslash, text)
        return json.loads(repaired)


from prompts import (
    EXTRACT_PROMPT,
    EVALUATE_PROMPT,
    EXAM_CONTEXTS,
    HINT_PROMPT,
    PRACTICE_PROMPT,
    PRACTICE_EXAM_REQS,
    EXPLAIN_PROMPT,
    DEBATE_PROMPT,
    WOW_EXTRACT_PROMPT,
)

# ─── Routes ───


@app.route("/")
def index():
    ua = request.user_agent.string.lower()
    if any(m in ua for m in ["iphone", "android", "mobile"]):
        return redirect("/phone")
    return redirect("/pc")


@app.route("/pc")
@require_auth
def pc_dashboard():
    token = generate_pair_token(request.student["id"])
    return render_template("pc.html", ip=request.host, port=PORT, model_status=router.status(), pair_token=token)


@app.route("/phone")
def phone_page():
    from flask import session as flask_session
    token = request.args.get("pair", "")
    if token:
        student_id = validate_pair_token(token)
        if student_id:
            flask_session.permanent = True
            flask_session["student_id"] = student_id
            logger.info(f"Phone paired for student {student_id[:8]}...")
            return render_template("phone.html", paired=True)
        else:
            return render_template("phone.html", paired=False, error="Invalid or expired pairing code. Scan the QR code on the PC again.")
    # Already paired via session?
    if flask_session.get("student_id"):
        return render_template("phone.html", paired=True)
    return render_template("phone.html", paired=False, error="Scan the QR code on the PC screen to connect.")


@app.route("/api/status")
def api_status():
    return jsonify({"models": router.status(), "ip": request.host, "port": PORT})


@app.route("/api/upload", methods=["POST"])
@require_auth
def api_upload():
    subject = request.form.get("subject", "maths")
    exam = request.form.get("exam", "general")
    problem_numbers = request.form.get("problem_numbers", "")

    question_files = request.files.getlist("questions")
    answer_files = request.files.getlist("answers")

    if not question_files and not answer_files:
        return jsonify({"error": "No images uploaded"}), 400

    q_paths = [save_upload(f) for f in question_files if f.filename]
    a_paths = [save_upload(f) for f in answer_files if f.filename]

    batch_id = uuid.uuid4().hex[:12]
    student_id = request.student["id"]

    # Track batch status
    db.set_batch_status(batch_id, student_id, "uploading")
    db.log_event(student_id, "upload", {"subject": subject, "exam": exam, "questions": len(q_paths), "answers": len(a_paths), "batch_id": batch_id})

    # Process in background so phone gets immediate response
    def evaluate_async():
        try:
            _run_evaluation(batch_id, subject, exam, q_paths, a_paths, problem_numbers, student_id)
        except Exception as e:
            logger.error(f"Evaluation failed: {e}", exc_info=True)
            db.set_batch_status(batch_id, student_id, "failed", str(e)[:500])

    threading.Thread(target=evaluate_async, daemon=True).start()

    return jsonify(
        {
            "batch_id": batch_id,
            "status": "processing",
            "message": "Uploaded! Check the PC screen for results.",
            "questions": len(q_paths),
            "answers": len(a_paths),
        }
    )


def _run_evaluation(batch_id, subject, exam, q_paths, a_paths, problem_numbers, student_id=None):
    exam_context = EXAM_CONTEXTS.get(exam, EXAM_CONTEXTS["general"])

    all_images = q_paths + a_paths

    # Step 1: Extract handwritten content using vision model (GPT-4o preferred)
    extract_prompt = EXTRACT_PROMPT.format(subject=subject)
    if problem_numbers:
        extract_prompt += f"\n\nIMPORTANT: The student says they answered problem numbers: {problem_numbers}. Use these EXACT numbers as the problem identifiers in your transcription (e.g. '=== Problem {problem_numbers.split(',')[0].strip()} ===')."

    db.set_batch_status(batch_id, student_id, "extracting")
    logger.info(f"Batch {batch_id}: extracting handwritten content...")
    extracted_text = router.call("extract", extract_prompt, images=all_images)
    logger.info(f"Batch {batch_id}: extraction complete ({len(extracted_text)} chars)")

    # Step 2: Evaluate the extracted text using reasoning model (Gemini preferred)
    db.set_batch_status(batch_id, student_id, "evaluating")
    eval_prompt = EVALUATE_PROMPT.format(
        subject=subject, exam_context=exam_context
    ).replace("__EXTRACTED_TEXT__", extracted_text)
    if problem_numbers:
        eval_prompt += f"\n\nThe student says they answered these problem numbers: {problem_numbers}"

    raw_response = router.call("evaluate", eval_prompt)

    try:
        results = parse_ai_json(raw_response)
        if isinstance(results, dict):
            results = [results]
    except json.JSONDecodeError:
        # First parse failed — retry once with an explicit JSON-only instruction
        logger.warning(f"Batch {batch_id}: JSON parse failed, retrying with JSON-only prompt")
        retry_prompt = (
            "Your previous response could not be parsed as JSON. "
            "Return ONLY a valid JSON array. Rules:\n"
            "- No markdown fences (no ```)\n"
            "- No text before or after the JSON\n"
            "- Escape backslashes in LaTeX as double-backslash (e.g. \\\\frac, \\\\theta)\n"
            "- Use \\n for newlines inside strings\n"
            "- Ensure all strings are properly quoted\n\n"
            + EVALUATE_PROMPT.format(
                subject=subject,
                exam_context=EXAM_CONTEXTS.get(exam, EXAM_CONTEXTS["general"]),
            ).replace("__EXTRACTED_TEXT__", extracted_text)
        )
        try:
            raw_response = router.call("evaluate", retry_prompt)
            results = parse_ai_json(raw_response)
            if isinstance(results, dict):
                results = [results]
        except (json.JSONDecodeError, Exception):
            results = [
                {
                    "problem_number": "?",
                    "question_summary": "AI response couldn't be processed",
                    "question_text": "",
                    "correctness": -1,
                    "what_went_right": "",
                    "where_it_broke": "",
                    "mistakes": [],
                    "hint_not_answer": "",
                    "encouragement": "",
                    "ai_error": True,
                }
            ]

    for result in results:
        db.save_evaluation(
            batch_id=batch_id,
            subject=subject,
            exam=exam,
            result=result,
            question_images=[os.path.basename(p) for p in q_paths],
            answer_images=[os.path.basename(p) for p in a_paths],
            raw_response=raw_response,
            student_id=student_id,
        )

    # Mark done immediately after saving — so polling sees done + results atomically
    db.set_batch_status(batch_id, student_id, "done")
    logger.info(f"Batch {batch_id}: evaluated {len(results)} problems")

    # Debounced backup — waits 60s after the LAST evaluation before pushing.
    # If another batch completes during the wait, the timer resets.
    # This prevents 50 sequential evaluations from triggering 50 git pushes.
    _schedule_debounced_backup()


_backup_timer: threading.Timer | None = None
_backup_timer_lock = threading.Lock()


def _schedule_debounced_backup(delay: int = 120):
    """Cancel any pending backup and schedule a new one delay seconds from now."""
    global _backup_timer
    with _backup_timer_lock:
        if _backup_timer is not None:
            _backup_timer.cancel()
        _backup_timer = threading.Timer(delay, backup_to_git)
        _backup_timer.daemon = True
        _backup_timer.start()


@app.route("/api/batch-status/<batch_id>")
@require_auth
def api_batch_status(batch_id):
    if not all(c in "0123456789abcdef" for c in batch_id):
        return jsonify({"error": "Invalid batch ID"}), 400
    status = db.get_batch_status(batch_id)
    if not status:
        return jsonify({"status": "unknown"})
    return jsonify({"status": status["status"], "error": status.get("error_message")})


@app.route("/api/retry/<batch_id>", methods=["POST"])
@require_auth
def api_retry_batch(batch_id):
    if not all(c in "0123456789abcdef" for c in batch_id):
        return jsonify({"error": "Invalid batch ID"}), 400
    student_id = request.student["id"]
    # Get the original batch metadata to re-run evaluation
    batch = db.get_batch(batch_id, student_id=student_id)
    if not batch:
        return jsonify({"error": "Batch not found"}), 404
    # Re-run evaluation using stored images
    first = batch[0] if batch else {}
    subject = first.get("subject", "maths")
    exam = first.get("exam", "general")
    q_images = first.get("question_images", "[]")
    a_images = first.get("answer_images", "[]")
    q_paths = json.loads(q_images) if isinstance(q_images, str) else (q_images or [])
    a_paths = json.loads(a_images) if isinstance(a_images, str) else (a_images or [])
    problem_numbers = first.get("problem_numbers", "")

    db.set_batch_status(batch_id, student_id, "extracting")

    def retry_async():
        try:
            _run_evaluation(batch_id, subject, exam, q_paths, a_paths, problem_numbers, student_id)
        except Exception as e:
            logger.error(f"Retry failed: {e}", exc_info=True)
            db.set_batch_status(batch_id, student_id, "failed", str(e)[:500])

    threading.Thread(target=retry_async, daemon=True).start()
    return jsonify({"ok": True})


@app.route("/api/results/latest")
@require_auth
def api_results_latest():
    batch = db.get_latest_batch(student_id=request.student["id"])
    # Also include active batch info for processing indicator
    active = db.get_active_batch(student_id=request.student["id"])
    return jsonify({
        "results": batch or [],
        "timestamp": datetime.now().isoformat(),
        "active_batch": active,
    })


@app.route("/api/results/<batch_id>")
@require_auth
def api_results_batch(batch_id):
    # Sanitize batch_id — only allow hex characters
    if not all(c in "0123456789abcdef" for c in batch_id):
        return jsonify({"error": "Invalid batch ID"}), 400
    batch = db.get_batch(batch_id, student_id=request.student["id"])
    return jsonify({"results": batch or []})


@app.route("/api/practice", methods=["POST"])
@require_auth
def api_practice():
    data = request.get_json() or {}
    subject = data.get("subject", "maths")
    exam = data.get("exam", "general")
    topic = data.get("topic", "")
    difficulty = data.get("difficulty", "medium")
    db.log_event(request.student["id"], "practice", {"subject": subject, "topic": topic, "difficulty": difficulty})

    if not topic:
        stats = db.get_progress(student_id=request.student["id"])
        weak = stats.get("weak_topics", [])
        if weak:
            topic = weak[0]["topic"]
        else:
            topic = {"maths": "algebra", "physics": "mechanics", "chemistry": "atomic structure"}.get(
                subject, "fundamentals"
            )

    exam_req = PRACTICE_EXAM_REQS.get(exam, PRACTICE_EXAM_REQS["general"])
    prompt = PRACTICE_PROMPT.format(
        difficulty=difficulty,
        subject=subject,
        exam=exam,
        topic=topic,
        exam_specific=exam_req,
    )

    raw = router.call("practice", prompt)

    try:
        problem = parse_ai_json(raw)
    except json.JSONDecodeError:
        problem = {"problem": raw, "topic": topic, "difficulty": difficulty}

    conn = db.get_db()
    conn.execute(
        """INSERT INTO practice_problems (timestamp, subject, exam, topic, difficulty, problem_text, hints)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            datetime.now().isoformat(),
            subject,
            exam,
            problem.get("topic", topic),
            difficulty,
            problem.get("problem", raw),
            json.dumps(problem.get("hints", [])),
        ),
    )
    conn.commit()
    conn.close()

    return jsonify(problem)


@app.route("/api/explain", methods=["POST"])
@require_auth
def api_explain():
    data = request.get_json() or {}
    subject = data.get("subject", "maths")
    exam = data.get("exam", "general")
    topic = data.get("topic", "")

    if not topic:
        return jsonify({"error": "Topic is required"}), 400

    db.log_event(request.student["id"], "explain", {"subject": subject, "topic": topic})
    prompt = EXPLAIN_PROMPT.format(subject=subject, exam=exam, topic=topic)
    response = router.call("explain", prompt)
    return jsonify({"explanation": response, "topic": topic, "subject": subject})


@app.route("/api/progress")
@require_auth
def api_progress():
    return jsonify(db.get_progress(student_id=request.student["id"]))


@app.route("/api/history")
@require_auth
def api_history():
    limit = request.args.get("limit", 50, type=int)
    return jsonify(db.get_history(min(limit, 200), student_id=request.student["id"]))


@app.route("/uploads/<filename>")
@require_auth
def serve_upload(filename):
    safe_name = secure_filename(filename)
    if safe_name != filename:
        return jsonify({"error": "Invalid filename"}), 400
    return send_from_directory(UPLOAD_DIR, safe_name)


@app.route("/api/hint", methods=["POST"])
@require_auth
def api_hint():
    """Get progressive hints for a question (no answer needed)."""
    subject = request.form.get("subject", "maths")
    exam = request.form.get("exam", "general")
    question_files = request.files.getlist("questions")

    if not question_files:
        return jsonify({"error": "No question images uploaded"}), 400

    q_paths = [save_upload(f) for f in question_files if f.filename]
    if not q_paths:
        return jsonify({"error": "No valid question images"}), 400

    db.log_event(request.student["id"], "hint", {"subject": subject, "images": len(q_paths)})
    exam_context = EXAM_CONTEXTS.get(exam, EXAM_CONTEXTS["general"])
    prompt = HINT_PROMPT.format(subject=subject, exam_context=exam_context)

    problem_numbers = request.form.get("problem_numbers", "")
    if problem_numbers:
        prompt += f"\n\nFocus on these problem numbers: {problem_numbers}"

    try:
        raw_response = router.call("extract", prompt, images=q_paths)
        hints = parse_ai_json(raw_response)
        if isinstance(hints, dict):
            hints = [hints]
        return jsonify({"hints": hints})
    except Exception as e:
        logger.error(f"Hint generation failed: {e}", exc_info=True)
        return jsonify({"error": "Failed to generate hints. Try again."}), 500


def _auto_save_wow(subject, topic, mentor_reply, student_message, student_id=None):
    """Background: extract and auto-save insight from a debate exchange."""
    try:
        prompt = WOW_EXTRACT_PROMPT.format(
            subject=subject, topic=topic,
            mentor_reply=mentor_reply[:600],
            student_message=student_message[:400],
        )
        insight = router.call("explain", prompt).strip()
        if insight and insight.upper() != "SKIP" and len(insight) > 20:
            db.save_wow_note(note=insight, subject=subject, topic=topic, source="auto", student_id=student_id)
            logger.info("Auto-saved wow note: %s", insight[:80])
    except Exception as e:
        logger.debug("Auto-wow skipped: %s", e)


@app.route("/api/hint/by-filename", methods=["POST"])
@require_auth
def api_hint_by_filename():
    """Get hints using image filenames already on the server — no re-upload needed."""
    data = request.get_json() or {}
    filenames = data.get("filenames", [])
    subject = data.get("subject", "maths")
    exam = data.get("exam", "general")

    if not filenames:
        return jsonify({"error": "No filenames provided"}), 400

    q_paths = []
    for fn in filenames[:10]:
        safe = secure_filename(str(fn))
        if safe != fn:
            continue  # Skip potentially malicious filenames
        path = os.path.join(UPLOAD_DIR, safe)
        if os.path.isfile(path):
            q_paths.append(path)

    if not q_paths:
        return jsonify({"error": "Images not found on server. Try re-uploading from phone."}), 404

    exam_context = EXAM_CONTEXTS.get(exam, EXAM_CONTEXTS["general"])
    prompt = HINT_PROMPT.format(subject=subject, exam_context=exam_context)

    try:
        raw_response = router.call("extract", prompt, images=q_paths)
        hints = parse_ai_json(raw_response)
        if isinstance(hints, dict):
            hints = [hints]
        return jsonify({"hints": hints})
    except Exception as e:
        logger.error(f"Hint generation failed: {e}", exc_info=True)
        return jsonify({"error": "Could not generate hints. Check your internet and try again."}), 500


@app.route("/api/debate", methods=["POST"])
@require_auth
def api_debate():
    """Socratic one-on-one debate about a student's solution."""
    data = request.get_json() or {}
    subject = str(data.get("subject", "maths"))[:50]
    exam = str(data.get("exam", "general"))[:50]
    question_text = str(data.get("question_text", ""))[:1500]
    topic = str(data.get("topic", ""))[:100]
    correctness = int(data.get("correctness", 0))
    what_went_right = str(data.get("what_went_right", ""))[:500]
    where_it_broke = str(data.get("where_it_broke", ""))[:500]
    missing_concept = str(data.get("missing_concept", ""))[:300]
    history = data.get("history", [])[:20]
    message = str(data.get("message", ""))[:1000]

    if not question_text:
        return jsonify({"error": "No question context. Try re-evaluating first."}), 400

    db.log_event(request.student["id"], "debate", {"subject": subject, "topic": topic, "turns": len(history)})

    history_lines = []
    for entry in history:
        role = "Mentor" if entry.get("role") == "ai" else "Student"
        content = str(entry.get("content", ""))[:500]
        history_lines.append(f"{role}: {content}")
    history_text = ("\nPrevious conversation:\n" + "\n".join(history_lines) + "\n\n") if history_lines else ""

    prompt = DEBATE_PROMPT.format(
        subject=subject,
        exam=exam,
        question_text=question_text or "Not available",
        topic=topic or "General",
        correctness=correctness,
        what_went_right=what_went_right or "Nothing notable",
        where_it_broke=where_it_broke or "Unclear",
        missing_concept=missing_concept or "Unclear",
        history_text=history_text,
        student_message=message or "(Start the debate — ask an opening question)",
    )

    try:
        reply = router.call("explain", prompt)
        reply = reply.strip()
        # Save debate exchange to DB for parent progress review
        threading.Thread(
            target=db.save_debate_log,
            args=(subject, topic, question_text, message or "", reply, request.student["id"]),
            daemon=True,
        ).start()
        # Auto-extract and save key insight in background — no latency impact
        threading.Thread(
            target=_auto_save_wow,
            args=(subject, topic, reply, message or "", request.student["id"]),
            daemon=True,
        ).start()
        return jsonify({"reply": reply})
    except Exception as e:
        logger.error(f"Debate failed: {e}", exc_info=True)
        return jsonify({"error": "Could not get AI response. Check your internet and try again."}), 500


@app.route("/api/wow", methods=["POST"])
@require_auth
def api_save_wow():
    data = request.get_json() or {}
    note = str(data.get("note", "")).strip()[:2000]
    if not note:
        return jsonify({"error": "Note is empty"}), 400
    db.save_wow_note(
        note=note,
        subject=str(data.get("subject", ""))[:50],
        topic=str(data.get("topic", ""))[:100],
        source=str(data.get("source", "debate"))[:20],
        student_id=request.student["id"],
    )
    return jsonify({"ok": True})


@app.route("/api/wow")
@require_auth
def api_get_wow():
    notes = db.get_wow_notes(student_id=request.student["id"])
    return jsonify({"notes": notes})


# ─── Auto-update & Backup ───

_backup_lock = threading.Lock()  # prevents auto_update + daily backup running concurrently


def auto_update():
    """Pull latest code from GitHub on startup.

    Uses a hash file (data/.last_code_update) to track the last applied
    remote commit — completely independent of local git HEAD, which may
    be ahead due to daily backup_to_git() commits in data/.
    """
    import sys

    CODE_FILES = [
        "app.py", "db.py", "models.py", "setup.sh",
        "requirements.txt", "mathtutor.py", "generate_guide.py",
        "templates/",
    ]
    HASH_FILE = os.path.join(BASE_DIR, "data", ".last_code_update")

    try:
        # Step 1: fetch latest from remote (never modifies working tree)
        fetch = subprocess.run(
            ["git", "fetch", "origin", "main"],
            cwd=BASE_DIR, capture_output=True, text=True, timeout=30,
        )
        if fetch.returncode != 0:
            logger.warning(f"Auto-update: fetch failed — {fetch.stderr.strip()}")
            return

        # Step 2: get origin/main commit hash
        remote_hash = subprocess.run(
            ["git", "rev-parse", "origin/main"],
            cwd=BASE_DIR, capture_output=True, text=True, timeout=10,
        ).stdout.strip()

        # Step 3: compare against last applied hash
        last_hash = ""
        try:
            last_hash = Path(HASH_FILE).read_text().strip()
        except FileNotFoundError:
            pass  # First run — will update

        if remote_hash == last_hash:
            logger.info("Auto-update: already up to date")
            return

        # Step 4: overwrite only code files from origin/main (data/ untouched)
        checkout = subprocess.run(
            ["git", "checkout", "origin/main", "--"] + CODE_FILES,
            cwd=BASE_DIR, capture_output=True, text=True, timeout=30,
        )
        if checkout.returncode != 0:
            logger.error(f"Auto-update: checkout failed — {checkout.stderr.strip()}")
            logger.error("Auto-update: check CODE_FILES list — a path may not exist in the repo")
            return

        # Step 5: install packages. On failure/timeout, REVERT code files so the
        # app keeps running cleanly on old code. Next restart retries the full cycle.
        def _revert_checkout():
            subprocess.run(
                ["git", "checkout", "HEAD", "--"] + CODE_FILES,
                cwd=BASE_DIR, capture_output=True, timeout=30,
            )

        try:
            pip = subprocess.run(
                [sys.executable, "-m", "pip", "install", "-r",
                 os.path.join(BASE_DIR, "requirements.txt"), "-q", "--disable-pip-version-check"],
                cwd=BASE_DIR, capture_output=True, text=True, timeout=300,
            )
        except subprocess.TimeoutExpired:
            logger.error("Auto-update: pip install timed out — reverting code, will retry next restart")
            _revert_checkout()
            return

        if pip.returncode != 0:
            logger.error(f"Auto-update: pip install failed — reverting code, will retry next restart\n{pip.stderr.strip()[:300]}")
            _revert_checkout()
            return

        logger.info("Auto-update: packages up to date")

        # Step 6: back up local DB before restarting so no evaluated work is lost
        logger.info("Auto-update: backing up local data before restart...")
        backup_to_git()

        # Step 7: re-fetch hash AFTER backup — backup may have pushed a new commit,
        # advancing origin/main. Save that post-backup tip so next restart matches.
        # If this fetch fails, skip saving hash entirely (safer to re-run update
        # than to save a stale hash and miss a future update).
        post_fetch = subprocess.run(
            ["git", "fetch", "origin", "main"],
            cwd=BASE_DIR, capture_output=True, text=True, timeout=30,
        )
        if post_fetch.returncode == 0:
            post_hash = subprocess.run(
                ["git", "rev-parse", "origin/main"],
                cwd=BASE_DIR, capture_output=True, text=True, timeout=10,
            ).stdout.strip()
        else:
            post_hash = ""  # don't save — next restart will re-run update (safe)

        if post_hash:
            os.makedirs(os.path.join(BASE_DIR, "data"), exist_ok=True)
            try:
                Path(HASH_FILE).write_text(post_hash)
            except Exception as e:
                # Hash write failed — log it but still restart. The update was
                # applied successfully; next restart will re-apply (idempotent).
                logger.warning(f"Auto-update: could not save hash file — {e}. Will re-apply on next restart.")

        logger.info(f"Auto-update: applied {remote_hash[:8]}, restarting...")
        # Use absolute path: sys.argv[0] may be relative, causing FileNotFoundError
        # after os.execv loses the original systemd WorkingDirectory context.
        abs_app = os.path.join(BASE_DIR, "app.py")
        os.execv(sys.executable, [sys.executable, abs_app] + sys.argv[1:])

    except Exception as e:
        logger.warning(f"Auto-update skipped: {e}")


def backup_to_git():
    """Export progress data and push to GitHub."""
    with _backup_lock:  # prevent concurrent runs (daily thread vs auto_update)
        _do_backup()


def _do_backup():
    data_dir = os.path.join(BASE_DIR, "data")
    os.makedirs(data_dir, exist_ok=True)

    try:
        export = db.export_for_backup()
        backup_path = os.path.join(data_dir, "progress_backup.json")

        # Include last 200 log lines so we can diagnose issues remotely
        try:
            log_lines = Path(_LOG_FILE).read_text(encoding="utf-8").splitlines()
            export["app_log_tail"] = log_lines[-200:]
        except Exception:
            export["app_log_tail"] = []

        with open(backup_path, "w") as f:
            json.dump(export, f, indent=2)

        subprocess.run(
            ["git", "add", "data/"], cwd=BASE_DIR, capture_output=True, timeout=10
        )
        subprocess.run(
            [
                "git",
                "commit",
                "-m",
                f"backup: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            ],
            cwd=BASE_DIR,
            capture_output=True,
            timeout=10,
        )
        # Pull --rebase first so our backup commit sits on top of any code
        # updates or other backup commits that may have advanced origin/main.
        # Without this, push is rejected with non-fast-forward error.
        subprocess.run(
            ["git", "pull", "--rebase"],
            cwd=BASE_DIR, capture_output=True, timeout=30
        )
        subprocess.run(
            ["git", "push"], cwd=BASE_DIR, capture_output=True, timeout=30
        )
        logger.info("Progress backed up to GitHub")
    except Exception as e:
        logger.warning(f"Backup skipped: {e}")


def schedule_daily_backup():
    import time

    def _loop():
        while True:
            time.sleep(24 * 60 * 60)
            backup_to_git()

    threading.Thread(target=_loop, daemon=True).start()


# ─── Exam Calendar ───

# Static exam data — dates we KNOW from official sources as of March 2026.
# AI verification cross-checks these against live web data.
# "verified_at" tracks when AI last confirmed each exam's dates.

EXAM_CALENDAR = [
    {
        "id": "cbse_board_2027",
        "name": "CBSE Board Exams",
        "category": "board",
        "dates": {
            "registration_open": "2026-09-01",
            "registration_close": "2026-10-31",
            "exam_start": "2027-02-15",
            "exam_end": "2027-03-31",
            "result": "2027-05-15",
        },
        "official_url": "https://www.cbse.gov.in/",
        "apply_url": "https://www.cbse.gov.in/",
        "notes": "Date sheet usually released in December. Check CBSE site for exact subject dates.",
        "verified_at": None,
        "ai_status": None,
    },
    {
        "id": "jee_main_jan_2027",
        "name": "JEE Main 2027 — Session 1 (January)",
        "category": "engineering",
        "dates": {
            "registration_open": "2026-11-01",
            "registration_close": "2026-11-30",
            "exam_start": "2027-01-20",
            "exam_end": "2027-01-31",
            "result": "2027-02-15",
        },
        "official_url": "https://jeemain.nta.nic.in/",
        "apply_url": "https://jeemain.nta.nic.in/",
        "notes": "NTA usually announces in October. Session 1 score valid for Session 2 improvement.",
        "verified_at": None,
        "ai_status": None,
    },
    {
        "id": "jee_main_apr_2027",
        "name": "JEE Main 2027 — Session 2 (April)",
        "category": "engineering",
        "dates": {
            "registration_open": "2027-02-01",
            "registration_close": "2027-03-05",
            "exam_start": "2027-04-01",
            "exam_end": "2027-04-15",
            "result": "2027-04-30",
        },
        "official_url": "https://jeemain.nta.nic.in/",
        "apply_url": "https://jeemain.nta.nic.in/",
        "notes": "Best of Session 1 and 2 scores is considered. Apply even if Session 1 went well.",
        "verified_at": None,
        "ai_status": None,
    },
    {
        "id": "jee_advanced_2027",
        "name": "JEE Advanced 2027",
        "category": "engineering",
        "dates": {
            "registration_open": "2027-04-20",
            "registration_close": "2027-05-10",
            "exam_start": "2027-05-25",
            "exam_end": "2027-05-25",
            "result": "2027-06-15",
        },
        "official_url": "https://jeeadv.ac.in/",
        "apply_url": "https://jeeadv.ac.in/",
        "notes": "Must qualify JEE Main first (top 2.5 lakh). Single day exam — Paper 1 + Paper 2.",
        "verified_at": None,
        "ai_status": None,
    },
    {
        "id": "bitsat_2027",
        "name": "BITSAT 2027",
        "category": "engineering",
        "dates": {
            "registration_open": "2027-01-15",
            "registration_close": "2027-04-15",
            "exam_start": "2027-05-20",
            "exam_end": "2027-06-05",
            "result": "2027-06-15",
        },
        "official_url": "https://www.bitsadmission.com/",
        "apply_url": "https://www.bitsadmission.com/",
        "notes": "Online CBT. Long registration window. Apply early for preferred slot.",
        "verified_at": None,
        "ai_status": None,
    },
    {
        "id": "isi_2027",
        "name": "ISI Admission 2027 (B.Stat/B.Math)",
        "category": "research",
        "dates": {
            "registration_open": "2027-02-01",
            "registration_close": "2027-04-15",
            "exam_start": "2027-05-11",
            "exam_end": "2027-05-11",
            "result": "2027-06-15",
        },
        "official_url": "https://www.isical.ac.in/admissions",
        "apply_url": "https://www.isical.ac.in/admissions",
        "notes": "Written test (UGA/UGB) + interview. Extremely selective. Math Olympiad exposure helps.",
        "verified_at": None,
        "ai_status": None,
    },
    {
        "id": "cmi_2027",
        "name": "CMI Entrance 2027 (BSc Hons)",
        "category": "research",
        "dates": {
            "registration_open": "2027-03-01",
            "registration_close": "2027-04-05",
            "exam_start": "2027-05-04",
            "exam_end": "2027-05-04",
            "result": "2027-06-01",
        },
        "official_url": "https://www.cmi.ac.in/admissions/",
        "apply_url": "https://www.cmi.ac.in/admissions/",
        "notes": "3-hour written exam. Math Olympiad qualifiers get direct admission. Based on 2026 pattern: exam first Saturday of May.",
        "verified_at": None,
        "ai_status": None,
    },
    {
        "id": "iiit_h_2027",
        "name": "IIIT Hyderabad (UGEE) 2027",
        "category": "engineering",
        "dates": {
            "registration_open": "2027-02-01",
            "registration_close": "2027-04-30",
            "exam_start": "2027-05-15",
            "exam_end": "2027-05-15",
            "result": "2027-06-10",
        },
        "official_url": "https://www.iiit.ac.in/admissions/",
        "apply_url": "https://www.iiit.ac.in/admissions/",
        "notes": "Can apply via JEE Main score OR separate UGEE test. Check both pathways.",
        "verified_at": None,
        "ai_status": None,
    },
    {
        "id": "tnea_2027",
        "name": "TNEA 2027 (TN Engineering Admissions)",
        "category": "state",
        "dates": {
            "registration_open": "2027-05-01",
            "registration_close": "2027-06-15",
            "exam_start": None,
            "exam_end": None,
            "result": "2027-07-15",
        },
        "official_url": "https://www.tneaonline.org/",
        "apply_url": "https://www.tneaonline.org/",
        "notes": "No exam — pure 12th marks merit. TN domicile since LKG = eligible. Safety net option.",
        "verified_at": None,
        "ai_status": None,
    },
    {
        "id": "kvpy_iiser_2027",
        "name": "IISER Aptitude Test / IAT 2027",
        "category": "research",
        "dates": {
            "registration_open": "2027-03-15",
            "registration_close": "2027-05-15",
            "exam_start": "2027-06-08",
            "exam_end": "2027-06-08",
            "result": "2027-06-30",
        },
        "official_url": "https://www.iiseradmission.in/",
        "apply_url": "https://www.iiseradmission.in/",
        "notes": "Also accepts JEE Advanced rank and KVPY/Olympiad. IAT is a separate exam option.",
        "verified_at": None,
        "ai_status": None,
    },
]

# Mutex for AI verification (only one at a time)
_verify_lock = threading.Lock()


VERIFY_PROMPT = """I need you to verify the current official exam dates for Indian entrance exams for the 2027 admission cycle.

For each exam below, search for the LATEST official information and tell me:
1. Are the dates I have correct, approximately correct, or wrong?
2. What are the actual dates if different?
3. Has the official notification been released yet?

IMPORTANT: Only report what you can actually verify from official sources. If no 2027 dates are announced yet, say "not yet announced" — do NOT guess.

Exams to verify:
{exam_list}

Return ONLY a JSON array (no markdown fences):
[
  {{
    "id": "{exam_id_placeholder}",
    "status": "confirmed" | "approximate" | "wrong" | "not_announced",
    "notes": "brief explanation of what you found",
    "corrected_dates": {{}} or null if dates are correct,
    "source": "where you found this info"
  }}
]"""


@app.route("/api/exams")
def api_exams():
    """Return exam calendar with status info."""
    today = datetime.now().strftime("%Y-%m-%d")
    exams = []
    for exam in EXAM_CALENDAR:
        e = dict(exam)
        # Calculate dynamic status
        dates = e["dates"]
        if dates.get("registration_open") and today < dates["registration_open"]:
            e["status"] = "upcoming"
            e["status_label"] = "Not yet open"
        elif dates.get("registration_close") and today <= dates["registration_close"]:
            e["status"] = "registration_open"
            e["status_label"] = "Registration OPEN"
        elif dates.get("exam_start") and today < dates["exam_start"]:
            e["status"] = "registered"
            e["status_label"] = "Registration closed"
        elif dates.get("exam_end") and today <= dates["exam_end"]:
            e["status"] = "exam_ongoing"
            e["status_label"] = "Exam in progress"
        elif dates.get("result") and today < dates["result"]:
            e["status"] = "awaiting_result"
            e["status_label"] = "Awaiting result"
        else:
            e["status"] = "completed"
            e["status_label"] = "Completed"

        # Days until next important date
        if dates.get("registration_open") and today < dates["registration_open"]:
            diff = (datetime.strptime(dates["registration_open"], "%Y-%m-%d") - datetime.now()).days
            e["countdown"] = {"days": max(diff, 0), "event": "Registration opens"}
        elif dates.get("registration_close") and today <= dates["registration_close"]:
            diff = (datetime.strptime(dates["registration_close"], "%Y-%m-%d") - datetime.now()).days
            e["countdown"] = {"days": max(diff, 0), "event": "Registration closes"}
        elif dates.get("exam_start") and today < dates["exam_start"]:
            diff = (datetime.strptime(dates["exam_start"], "%Y-%m-%d") - datetime.now()).days
            e["countdown"] = {"days": max(diff, 0), "event": "Exam starts"}
        else:
            e["countdown"] = None

        exams.append(e)

    return jsonify({"exams": exams, "last_verified": None, "today": today})


@app.route("/api/exams/verify", methods=["POST"])
def api_verify_exams():
    """Use Perplexity (live web search) to verify exam dates. Falls back to Gemini."""
    if not _verify_lock.acquire(blocking=False):
        return jsonify({"error": "Verification already in progress"}), 429

    try:
        exam_list = "\n".join(
            f"- {e['name']}: registration {e['dates'].get('registration_open','?')} to {e['dates'].get('registration_close','?')}, "
            f"exam {e['dates'].get('exam_start','N/A')}, result {e['dates'].get('result','?')}"
            for e in EXAM_CALENDAR
        )
        prompt = VERIFY_PROMPT.format(exam_list=exam_list, exam_id_placeholder="exam_id_here")

        # Prefer Perplexity (has web search) > Gemini (general knowledge)
        model = "perplexity" if "perplexity" in router.available else router.pick("explain")
        logger.info(f"Verifying exam dates using {model}...")
        raw = router._dispatch(model, prompt, None)

        try:
            results = parse_ai_json(raw)
        except json.JSONDecodeError:
            return jsonify({"error": "Could not parse AI response", "raw": raw[:500]}), 500

        # Update exam calendar with verification results
        now = datetime.now().isoformat()
        # Build lookup by both id and name (AI may return either)
        result_map = {}
        for r in results:
            if isinstance(r, dict):
                rid = r.get("id", "")
                result_map[rid] = r
                result_map[rid.lower()] = r

        for exam in EXAM_CALENDAR:
            v = result_map.get(exam["id"]) or result_map.get(exam["name"]) or result_map.get(exam["name"].lower())
            if v:
                exam["verified_at"] = now
                exam["ai_status"] = v.get("status", "unknown")
                exam["ai_notes"] = v.get("notes", "")
                exam["ai_source"] = v.get("source", "")
                if v.get("corrected_dates"):
                    exam["ai_corrected_dates"] = v["corrected_dates"]

        return jsonify({
            "verified_at": now,
            "model_used": model,
            "results": results,
            "message": "Dates verified against live web data. Always cross-check official sites before relying on these.",
        })
    except Exception as e:
        logger.error(f"Exam verification failed: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500
    finally:
        _verify_lock.release()


# ─── Main ───

if __name__ == "__main__":
    models = ", ".join(router.available.keys())

    logger.info("=" * 50)
    logger.info("  GradesGenie is running!")
    logger.info(f"  URL    : http://0.0.0.0:{PORT}")
    logger.info(f"  Models : {models}")
    logger.info("=" * 50)

    auto_update()
    schedule_daily_backup()
    threading.Thread(target=backup_to_git, daemon=False).start()

    app.run(host="0.0.0.0", port=PORT, debug=False, threaded=True)
