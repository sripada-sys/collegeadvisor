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

db.init_db()
db.run_migrations()
router = ModelRouter()

# Register auth routes (login, callback, verify-phone, logout, subscribe)
from auth import register_auth_routes, require_auth
register_auth_routes(app)


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
        # AI often writes raw LaTeX backslashes (\int, \frac, \,) inside JSON strings
        # which are invalid JSON escape sequences. Fix by doubling lone backslashes.
        # Only keep \\ \" \/ \n \r \t \uXXXX as valid — everything else must be doubled.
        repaired = re.sub(r'\\(?!["\\\/nrtu])', r'\\\\', text)
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
def pc_dashboard():
    return render_template("pc.html", ip=request.host, port=PORT, model_status=router.status())


@app.route("/phone")
def phone_page():
    return render_template("phone.html")


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
    db.set_batch_status(batch_id, student_id, "processing")

    # Process in background so phone gets immediate response
    def evaluate_async():
        try:
            _run_evaluation(batch_id, subject, exam, q_paths, a_paths, problem_numbers, student_id)
            db.set_batch_status(batch_id, student_id, "done")
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
        extract_prompt += f"\n\nThe student says they answered these problem numbers: {problem_numbers}"

    logger.info(f"Batch {batch_id}: extracting handwritten content...")
    extracted_text = router.call("extract", extract_prompt, images=all_images)
    logger.info(f"Batch {batch_id}: extraction complete ({len(extracted_text)} chars)")

    # Step 2: Evaluate the extracted text using reasoning model (Gemini preferred)
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
            "Return ONLY a raw JSON array with no markdown, no backticks, no commentary. "
            "Use the same structure as before.\n\n"
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
                    "question_summary": "Could not parse structured response",
                    "correctness": 0,
                    "what_went_right": "",
                    "where_it_broke": raw_response[:500],
                    "mistakes": [],
                    "hint_not_answer": "",
                    "encouragement": "",
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
        )

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


@app.route("/api/results/latest")
@require_auth
def api_results_latest():
    batch = db.get_latest_batch()
    return jsonify({"results": batch or [], "timestamp": datetime.now().isoformat()})


@app.route("/api/results/<batch_id>")
@require_auth
def api_results_batch(batch_id):
    # Sanitize batch_id — only allow hex characters
    if not all(c in "0123456789abcdef" for c in batch_id):
        return jsonify({"error": "Invalid batch ID"}), 400
    batch = db.get_batch(batch_id)
    return jsonify({"results": batch or []})


@app.route("/api/practice", methods=["POST"])
@require_auth
def api_practice():
    data = request.get_json() or {}
    subject = data.get("subject", "maths")
    exam = data.get("exam", "general")
    topic = data.get("topic", "")
    difficulty = data.get("difficulty", "medium")

    if not topic:
        stats = db.get_progress()
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

    prompt = EXPLAIN_PROMPT.format(subject=subject, exam=exam, topic=topic)
    response = router.call("explain", prompt)
    return jsonify({"explanation": response, "topic": topic, "subject": subject})


@app.route("/api/progress")
@require_auth
def api_progress():
    return jsonify(db.get_progress())


@app.route("/api/history")
@require_auth
def api_history():
    limit = request.args.get("limit", 50, type=int)
    return jsonify(db.get_history(min(limit, 200)))


@app.route("/uploads/<filename>")
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


@app.route("/api/guide/pdf")
def api_guide_pdf():
    """Download the college guide PDF."""
    pdf_path = os.path.join(BASE_DIR, "output", "college_guide_2027.pdf")
    if not os.path.exists(pdf_path):
        return jsonify({"error": "Guide PDF not found. Run generate_guide.py first."}), 404
    return send_from_directory(
        os.path.join(BASE_DIR, "output"), "college_guide_2027.pdf",
        as_attachment=True, download_name="College_Guide_JEE_2027.pdf"
    )


@app.route("/api/guide/html")
def api_guide_html():
    """Return the guide HTML body content for in-app reading."""
    # Reads from pre-built static file — no Python imports, no weasyprint dependency.
    guide_file = os.path.join(BASE_DIR, "data", "guide_content.html")
    try:
        return Path(guide_file).read_text(encoding="utf-8")
    except FileNotFoundError:
        return "<p style='color:#f87171'>Guide file not found. Run: python3 generate_guide.py</p>", 404
    except Exception as e:
        logger.error(f"Guide HTML load failed: {e}", exc_info=True)
        return f"<p style='color:#f87171'>Error loading guide: {e}</p>", 500


def _auto_save_wow(subject, topic, mentor_reply, student_message):
    """Background: extract and auto-save insight from a debate exchange."""
    try:
        prompt = WOW_EXTRACT_PROMPT.format(
            subject=subject, topic=topic,
            mentor_reply=mentor_reply[:600],
            student_message=student_message[:400],
        )
        insight = router.call("explain", prompt).strip()
        if insight and insight.upper() != "SKIP" and len(insight) > 20:
            db.save_wow_note(note=insight, subject=subject, topic=topic, source="auto")
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
            args=(subject, topic, question_text, message or "", reply),
            daemon=True,
        ).start()
        # Auto-extract and save key insight in background — no latency impact
        threading.Thread(
            target=_auto_save_wow,
            args=(subject, topic, reply, message or ""),
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
    )
    return jsonify({"ok": True})


@app.route("/api/wow")
@require_auth
def api_get_wow():
    notes = db.get_wow_notes()
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
