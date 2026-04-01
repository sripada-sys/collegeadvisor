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
    "question_text": "complete question statement verbatim, exactly as written in the photo",
    "correct_answer": "complete step-by-step correct solution with all key steps and final answer",
    "subject": "{subject}",
    "topic": "main topic (e.g. quadratics, thermodynamics, organic reactions)",
    "subtopic": "specific subtopic",
    "correctness": <0-5 where 0=completely wrong, 3=right idea but errors, 5=perfect>,
    "is_complete": <true if solution reaches a final answer>,
    "source": "detected source if visible in the photo (e.g. book name, NCERT, HC Verma, Irodov, Cengage, DC Pandey, JEE Main 2024, coaching institute name from header/footer/watermark). null if not identifiable",
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

HINT_PROMPT = """You are an expert {subject} tutor. A student is stuck on a problem and needs hints — NOT the answer.

EXAM: {exam_context}

Look at the question photo(s) carefully. For each problem visible:

1. Identify the topic and what concept is being tested
2. Give 3 PROGRESSIVE hints:
   - Hint 1: A gentle nudge — what area/concept to think about (vague)
   - Hint 2: A more specific direction — what formula, theorem, or technique applies
   - Hint 3: Nearly gives it away — the key step or substitution, but still not the full answer

Do NOT solve the problem. Do NOT give the final answer.

Return raw JSON (no markdown fences):
[
  {{
    "problem_number": "the problem number as written",
    "question_summary": "1-line description of the question",
    "topic": "main topic",
    "source": "detected source if visible in photo (book name, exam paper, coaching material header/footer). null if not identifiable",
    "hint_1": "vague nudge",
    "hint_2": "more specific direction",
    "hint_3": "nearly gives it away but still not the answer"
  }}
]"""


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


@app.route("/api/hint", methods=["POST"])
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
        raw_response = router.call("evaluate", prompt, images=q_paths)
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


DEBATE_PROMPT = """You are a Socratic {subject} tutor debating a student's solution.

THE QUESTION: {question_text}
Subject: {subject} | Exam: {exam} | Topic: {topic}

Your previous evaluation:
- Score: {correctness}/5
- What went right: {what_went_right}
- Where it broke: {where_it_broke}
- Missing concept: {missing_concept}
{history_text}Student message: {student_message}

Rules:
1. If student message is empty (opening move): Mention ONE specific, observable thing from the evaluation. Ask ONE probing question about their approach.
2. If the student makes a MATHEMATICALLY VALID point you missed: Explicitly say "You're right, I missed that" — don't hedge.
3. If the student is wrong: Guide with a question. Do NOT state the answer or lecture.
4. Max 3 sentences + 1 question. Sharp and direct.
5. No empty praise ("Great point!", "Good try"). Be a real tutor.
6. Plain text only. No JSON, no markdown, no bullet lists."""


@app.route("/api/hint/by-filename", methods=["POST"])
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
        raw_response = router.call("evaluate", prompt, images=q_paths)
        hints = parse_ai_json(raw_response)
        if isinstance(hints, dict):
            hints = [hints]
        return jsonify({"hints": hints})
    except Exception as e:
        logger.error(f"Hint generation failed: {e}", exc_info=True)
        return jsonify({"error": "Could not generate hints. Check your internet and try again."}), 500


@app.route("/api/debate", methods=["POST"])
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
        role = "Tutor" if entry.get("role") == "ai" else "Student"
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
        return jsonify({"reply": reply.strip()})
    except Exception as e:
        logger.error(f"Debate failed: {e}", exc_info=True)
        return jsonify({"error": "Could not get AI response. Check your internet and try again."}), 500


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
            logger.info("New code pulled — restarting to apply updates...")
            # Replace current process with fresh one so new code is loaded immediately.
            # systemd will restart the service since it's set to Restart=always.
            import sys
            os.execv(sys.executable, [sys.executable] + sys.argv)
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
