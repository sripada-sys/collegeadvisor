#!/usr/bin/env python3
"""
MathTutor Web — AI tutor for JEE, ISI, CMI, Board exams.
Subjects: Maths, Physics, Chemistry.

Architecture:
  Linux PC = server + main dashboard (feedback, progress, QR code)
  Phone    = camera (uploads question + answer photos)
  iPad     = optional Canvas scratch pad

All on same WiFi. No install — just a browser.

Run:   python3 app.py
Setup: cp .env.example .env && edit .env with your API keys
"""

import json
import logging
import os
import socket
import subprocess
import threading
import uuid
import webbrowser
from datetime import datetime
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

# ─── Config ───

PORT = 5000
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Load .env file
env_path = os.path.join(BASE_DIR, ".env")
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))

# ─── Init ───

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50MB

db.init_db()
router = ModelRouter()


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
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text[:-3]
    if text.startswith("json"):
        text = text[4:]
    return json.loads(text.strip())


# ─── Prompts ───

EVALUATE_PROMPT = """You are an expert tutor evaluating a student's work.

SUBJECT: {subject}
EXAM: {exam_context}

You are given photo(s) of questions from a textbook/paper, and photo(s) of the student's handwritten answers.

Carefully:
1. Identify each problem number visible in both question and answer images
2. For each problem, read the question and the student's solution
3. Evaluate correctness, approach, and completeness

Return a JSON array (no markdown fences, raw JSON only):
[
  {{
    "problem_number": "the problem number as written",
    "question_summary": "1-line description of the question",
    "subject": "{subject}",
    "topic": "main topic (e.g. quadratics, thermodynamics, organic reactions)",
    "subtopic": "specific subtopic",
    "correctness": <0-5 where 0=completely wrong, 3=right idea but errors, 5=perfect>,
    "is_complete": <true if solution reaches a final answer>,
    "what_went_right": "specific thing done well",
    "where_it_broke": "exact step where reasoning went wrong, or 'nowhere' if correct",
    "mistakes": ["list of specific mistakes"],
    "missing_concept": "key concept to learn, or 'none' if correct",
    "hint_not_answer": "a hint to fix it WITHOUT giving the answer",
    "next_practice": "what to practice next",
    "encouragement": "one honest, specific sentence — not generic praise"
  }}
]

Be HONEST — wrong is wrong. But be SPECIFIC about what's right too.
"Good attempt" is useless. "Your free body diagram correctly identified all three forces" is useful.
If only some problems are visible, evaluate those."""

EXAM_CONTEXTS = {
    "jee_main": "JEE Main — MCQ, speed matters, check optimal method",
    "jee_advanced": "JEE Advanced — multi-concept, check all layers identified",
    "isi": "ISI B.Stat/B.Math — written proofs, evaluate rigor and logical flow",
    "cmi": "CMI BSc — proof-based, evaluate argument clarity and completeness",
    "bitsat": "BITSAT — speed and tricks, check shortcut usage",
    "board": "CBSE Board — step marking matters, check all steps shown, units, format",
    "general": "General preparation — evaluate correctness, approach, clarity",
}

PRACTICE_PROMPT = """Generate ONE {difficulty} {subject} problem for {exam} preparation.
Topic: {topic}

Requirements:
- Solvable by a Class 11-12 student
- {exam_specific}
- Clear problem statement
- Include 3 progressive hints (vague → specific)
- Do NOT include the full solution

Return raw JSON (no markdown fences):
{{
  "problem": "the full problem statement",
  "topic": "topic",
  "subtopic": "subtopic",
  "difficulty": "{difficulty}",
  "hints": ["vague hint", "more specific", "nearly gives it away"],
  "exam": "{exam}",
  "subject": "{subject}"
}}"""

PRACTICE_EXAM_REQS = {
    "jee_main": "MCQ with 4 options. Distractors based on common mistakes.",
    "jee_advanced": "MCQ, numerical, or multi-part. Require 2+ concepts.",
    "isi": 'Proof-based. "Show that..." or "Prove that..." format.',
    "cmi": 'Proof-based or "Find all..." style.',
    "bitsat": "MCQ solvable in 2-3 minutes with the right trick.",
    "board": "Long-answer format. Include marks allocation (e.g. [4 marks]).",
    "general": "Any format.",
}

EXPLAIN_PROMPT = """Explain this concept clearly for a Class 11-12 student preparing for {exam}.
Subject: {subject}
Topic: {topic}

Give:
1. Core concept in simple terms
2. Key formulas/principles (if any)
3. One worked example
4. Common mistakes students make
5. How this connects to other topics

Keep it concise but thorough. Use analogies if helpful."""


# ─── Routes ───


@app.route("/")
def index():
    ua = request.user_agent.string.lower()
    if any(m in ua for m in ["iphone", "android", "mobile"]):
        return redirect("/phone")
    return redirect("/pc")


@app.route("/pc")
def pc_dashboard():
    ip = get_local_ip()
    return render_template("pc.html", ip=ip, port=PORT, model_status=router.status())


@app.route("/phone")
def phone_page():
    return render_template("phone.html")


@app.route("/api/status")
def api_status():
    return jsonify({"models": router.status(), "ip": get_local_ip(), "port": PORT})


@app.route("/api/upload", methods=["POST"])
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

    # Process in background so phone gets immediate response
    def evaluate_async():
        try:
            _run_evaluation(batch_id, subject, exam, q_paths, a_paths, problem_numbers)
        except Exception as e:
            logger.error(f"Evaluation failed: {e}", exc_info=True)

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


def _run_evaluation(batch_id, subject, exam, q_paths, a_paths, problem_numbers):
    exam_context = EXAM_CONTEXTS.get(exam, EXAM_CONTEXTS["general"])
    prompt = EVALUATE_PROMPT.format(subject=subject, exam_context=exam_context)

    if problem_numbers:
        prompt += f"\n\nThe student says they answered these problem numbers: {problem_numbers}"

    all_images = q_paths + a_paths
    raw_response = router.call("evaluate", prompt, images=all_images)

    try:
        results = parse_ai_json(raw_response)
        if isinstance(results, dict):
            results = [results]
    except json.JSONDecodeError:
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


@app.route("/api/results/latest")
def api_results_latest():
    batch = db.get_latest_batch()
    return jsonify({"results": batch or [], "timestamp": datetime.now().isoformat()})


@app.route("/api/results/<batch_id>")
def api_results_batch(batch_id):
    # Sanitize batch_id — only allow hex characters
    if not all(c in "0123456789abcdef" for c in batch_id):
        return jsonify({"error": "Invalid batch ID"}), 400
    batch = db.get_batch(batch_id)
    return jsonify({"results": batch or []})


@app.route("/api/practice", methods=["POST"])
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
def api_progress():
    return jsonify(db.get_progress())


@app.route("/api/history")
def api_history():
    limit = request.args.get("limit", 50, type=int)
    return jsonify(db.get_history(min(limit, 200)))


@app.route("/uploads/<filename>")
def serve_upload(filename):
    safe_name = secure_filename(filename)
    if safe_name != filename:
        return jsonify({"error": "Invalid filename"}), 400
    return send_from_directory(UPLOAD_DIR, safe_name)


# ─── Auto-update & Backup ───


def auto_update():
    """Pull latest code from GitHub on startup."""
    try:
        result = subprocess.run(
            ["git", "pull", "--ff-only"],
            cwd=BASE_DIR,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0 and "Already up to date" not in result.stdout:
            logger.info(f"Updated from GitHub: {result.stdout.strip()}")
        else:
            logger.info("Code is up to date")
    except Exception as e:
        logger.warning(f"Auto-update skipped: {e}")


def backup_to_git():
    """Export progress data and push to GitHub."""
    data_dir = os.path.join(BASE_DIR, "data")
    os.makedirs(data_dir, exist_ok=True)

    try:
        export = db.export_for_backup()
        backup_path = os.path.join(data_dir, "progress_backup.json")
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


# ─── Main ───

if __name__ == "__main__":
    ip = get_local_ip()
    url = f"http://{ip}:{PORT}"
    models = ", ".join(router.available.keys())

    logger.info("=" * 50)
    logger.info("  MathTutor is running!")
    logger.info(f"  PC dashboard : http://localhost:{PORT}/pc")
    logger.info(f"  Phone upload : {url}/phone")
    logger.info(f"  Models       : {models}")
    logger.info("=" * 50)

    auto_update()
    schedule_daily_backup()
    threading.Thread(target=backup_to_git, daemon=True).start()

    webbrowser.open(f"http://localhost:{PORT}/pc")

    app.run(host="0.0.0.0", port=PORT, debug=False, threaded=True)
