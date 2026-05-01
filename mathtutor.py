#!/usr/bin/env python3
"""
AI Math Tutor — works for JEE Main, JEE Advanced, ISI, CMI, BITSAT, anything.

Usage:
  python3 mathtutor.py solve photo.jpg              # Evaluate handwritten solution
  python3 mathtutor.py solve photo.jpg --exam jee    # JEE-specific feedback
  python3 mathtutor.py solve photo.jpg --exam isi    # ISI/CMI proof-style feedback
  python3 mathtutor.py practice --exam jee --topic quadratics  # Generate a practice problem
  python3 mathtutor.py progress                      # Show weak areas + what to work on next
  python3 mathtutor.py history                       # Show all past attempts

Setup:
  export GEMINI_API_KEY="your-key-from-aistudio.google.com"
  pip install google-genai Pillow

That's it. No frameworks, no servers, no accounts. One script.
"""

import argparse
import base64
import json
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

try:
    from google import genai
except ImportError:
    print("Install: pip install google-genai")
    sys.exit(1)

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tutor.db")
MODEL = "gemini-2.5-flash"


def get_client():
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        print("Set GEMINI_API_KEY environment variable.")
        print("Get free key: https://aistudio.google.com/apikey")
        sys.exit(1)
    return genai.Client(api_key=key)


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            exam TEXT DEFAULT 'general',
            topic TEXT,
            subtopic TEXT,
            image_path TEXT,
            correctness INTEGER,  -- 0-5 scale
            confidence INTEGER,   -- 0-5 how confident student seemed
            mistakes TEXT,        -- JSON list of mistake types
            feedback TEXT,        -- full AI feedback
            suggestion TEXT       -- what to practice next
        )
    """)
    conn.commit()
    return conn


def load_image_as_base64(path):
    with open(path, "rb") as f:
        return base64.standard_b64encode(f.read()).decode("utf-8")


def get_mime_type(path):
    ext = Path(path).suffix.lower()
    return {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png", ".webp": "image/webp",
        ".gif": "image/gif", ".heic": "image/heic",
    }.get(ext, "image/jpeg")


# ─── PROMPTS ───

SOLVE_PROMPT = """You are a math tutor evaluating a student's handwritten work.

EXAM CONTEXT: {exam_context}

Look at the student's handwritten solution in the image. Analyze it carefully.

Respond in this EXACT JSON format (no markdown, no code fences, just raw JSON):
{{
  "topic": "main math topic (e.g. quadratics, calculus, combinatorics, number theory)",
  "subtopic": "specific subtopic (e.g. AM-GM inequality, integration by parts)",
  "correctness": <0-5 where 0=completely wrong, 3=right idea but execution errors, 5=perfect>,
  "confidence": <1-5 how confident/fluent the student seems from handwriting>,
  "is_complete": <true/false whether the solution reaches a final answer>,
  "mistakes": ["list", "of", "specific", "mistakes"],
  "what_went_right": "what the student did well — be specific",
  "where_it_broke": "the exact step or line where reasoning went wrong (or 'nowhere' if correct)",
  "missing_concept": "the key concept/technique the student needs to learn (or 'none' if correct)",
  "hint_not_answer": "a hint that would help them fix it WITHOUT giving the answer",
  "next_practice": "specific topic/problem type to practice next based on this weakness",
  "encouragement": "one honest, non-generic sentence of encouragement based on what they actually did well"
}}

Be HONEST. Don't sugarcoat. A wrong step is wrong — say so clearly.
But also be specific about what's RIGHT. "Good attempt" is useless. "Your induction base case was set up correctly" is useful.
"""

EXAM_CONTEXTS = {
    "jee": "JEE Main / JEE Advanced. Focus on: speed of approach selection, calculation accuracy, whether they picked the optimal method. MCQ context — is the answer among likely options?",
    "isi": "ISI B.Stat/B.Math entrance. Focus on: proof rigor, logical flow, whether each step follows from the previous. No MCQ — full written proofs required. Evaluate mathematical maturity.",
    "cmi": "CMI BSc entrance. Similar to ISI — proof-based. Evaluate clarity of argument, correct use of definitions, completeness of proof.",
    "bitsat": "BITSAT. Focus on: speed, shortcut usage, quick approximation skills.",
    "general": "General math problem. Evaluate correctness, approach selection, and clarity of work.",
    "advanced": "JEE Advanced. Focus on: multi-concept problems, whether student identified all the layers, proof-style numerical problems.",
}

PRACTICE_PROMPT = """Generate ONE {difficulty} math problem suitable for {exam} preparation.
Topic: {topic}

Requirements:
- The problem must be solvable by a Class 11-12 student
- Include the problem statement clearly
- {exam_specific_req}
- At the end, include a HINTS section (3 progressive hints, from vague to specific)
- Do NOT include the full solution

Format:
PROBLEM:
[problem statement]

HINTS:
Hint 1: [vague conceptual hint]
Hint 2: [more specific direction]
Hint 3: [nearly gives it away but still requires work]

TOPIC: [topic]
SUBTOPIC: [subtopic]
DIFFICULTY: [easy/medium/hard]
"""

EXAM_PRACTICE_REQS = {
    "jee": "Format as MCQ with 4 options (one correct). Make distractors based on common mistakes.",
    "isi": "Make it a proof-based problem. 'Show that...' or 'Prove that...' format.",
    "cmi": "Proof-based. Can be 'Find all...' or 'Prove that...' style.",
    "bitsat": "MCQ with 4 options. Should be solvable in 2-3 minutes with the right trick.",
    "general": "Can be any format.",
    "advanced": "Can be MCQ, numerical, or multi-part. Should require 2+ concepts.",
}


# ─── COMMANDS ───

def cmd_solve(args):
    """Evaluate a handwritten solution from an image."""
    if not os.path.exists(args.image):
        print(f"File not found: {args.image}")
        sys.exit(1)

    client = get_client()
    conn = init_db()

    exam = args.exam or "general"
    exam_context = EXAM_CONTEXTS.get(exam, EXAM_CONTEXTS["general"])
    prompt = SOLVE_PROMPT.format(exam_context=exam_context)

    print(f"Analyzing solution ({exam} mode)...")

    img_data = load_image_as_base64(args.image)
    mime = get_mime_type(args.image)

    response = client.models.generate_content(
        model=MODEL,
        contents=[
            {
                "role": "user",
                "parts": [
                    {"inline_data": {"mime_type": mime, "data": img_data}},
                    {"text": prompt},
                ],
            }
        ],
    )

    raw = response.text.strip()
    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
    if raw.endswith("```"):
        raw = raw[:-3]
    if raw.startswith("json"):
        raw = raw[4:]
    raw = raw.strip()

    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        print("AI response (couldn't parse as JSON):")
        print(raw)
        return

    # Save to DB
    conn.execute(
        """INSERT INTO attempts 
           (timestamp, exam, topic, subtopic, image_path, correctness, confidence, mistakes, feedback, suggestion)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            datetime.now().isoformat(),
            exam,
            result.get("topic", "unknown"),
            result.get("subtopic", ""),
            os.path.abspath(args.image),
            result.get("correctness", 0),
            result.get("confidence", 0),
            json.dumps(result.get("mistakes", [])),
            json.dumps(result),
            result.get("next_practice", ""),
        ),
    )
    conn.commit()

    # Display
    score = result.get("correctness", 0)
    bar = "█" * score + "░" * (5 - score)
    print(f"\n{'─' * 50}")
    print(f"  Topic: {result.get('topic', '?')} → {result.get('subtopic', '?')}")
    print(f"  Score: [{bar}] {score}/5")
    print(f"  Complete: {'Yes' if result.get('is_complete') else 'No — solution incomplete'}")
    print(f"{'─' * 50}")

    if result.get("what_went_right"):
        print(f"\n  ✓ What's good: {result['what_went_right']}")

    if result.get("where_it_broke") and result["where_it_broke"].lower() != "nowhere":
        print(f"\n  ✗ Where it broke: {result['where_it_broke']}")

    if result.get("mistakes"):
        print(f"\n  Mistakes:")
        for m in result["mistakes"]:
            print(f"    • {m}")

    if result.get("missing_concept") and result["missing_concept"].lower() != "none":
        print(f"\n  📚 Missing concept: {result['missing_concept']}")

    if result.get("hint_not_answer"):
        print(f"\n  💡 Hint: {result['hint_not_answer']}")

    if result.get("next_practice"):
        print(f"\n  → Practice next: {result['next_practice']}")

    if result.get("encouragement"):
        print(f"\n  {result['encouragement']}")

    print()
    conn.close()


def cmd_practice(args):
    """Generate a practice problem based on weak areas or requested topic."""
    client = get_client()
    conn = init_db()

    exam = args.exam or "jee"
    topic = args.topic
    difficulty = args.difficulty or "medium"

    # If no topic specified, find the weakest area from history
    if not topic:
        row = conn.execute(
            """SELECT topic, AVG(correctness) as avg_score, COUNT(*) as attempts
               FROM attempts 
               WHERE correctness < 4
               GROUP BY topic 
               ORDER BY avg_score ASC, attempts DESC
               LIMIT 1"""
        ).fetchone()
        if row:
            topic = row[0]
            print(f"Weakest area detected: {topic} (avg score: {row[1]:.1f}/5 across {row[2]} attempts)")
        else:
            topic = "algebra"
            print("No history yet. Starting with algebra.")

    exam_req = EXAM_PRACTICE_REQS.get(exam, EXAM_PRACTICE_REQS["general"])
    prompt = PRACTICE_PROMPT.format(
        difficulty=difficulty, exam=exam, topic=topic, exam_specific_req=exam_req
    )

    print(f"\nGenerating {difficulty} {exam.upper()} problem on {topic}...\n")

    response = client.models.generate_content(model=MODEL, contents=prompt)
    print(response.text)
    conn.close()


def cmd_progress(args):
    """Show progress dashboard — weak areas, trends, what to focus on."""
    conn = init_db()

    total = conn.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]
    if total == 0:
        print("No attempts yet. Start with: python3 mathtutor.py solve <image>")
        return

    print(f"\n{'═' * 55}")
    print(f"  PROGRESS REPORT — {total} problems attempted")
    print(f"{'═' * 55}")

    # Overall by exam type
    rows = conn.execute(
        """SELECT exam, COUNT(*), AVG(correctness), 
                  SUM(CASE WHEN correctness >= 4 THEN 1 ELSE 0 END)
           FROM attempts GROUP BY exam ORDER BY AVG(correctness)"""
    ).fetchall()

    print(f"\n  By Exam Type:")
    for exam, count, avg, good in rows:
        bar = "█" * int(avg) + "░" * (5 - int(avg))
        print(f"    {exam.upper():10s}  [{bar}] {avg:.1f}/5  ({good}/{count} solid)")

    # Weakest topics
    rows = conn.execute(
        """SELECT topic, COUNT(*), AVG(correctness)
           FROM attempts GROUP BY topic 
           ORDER BY AVG(correctness) ASC LIMIT 5"""
    ).fetchall()

    print(f"\n  Weakest Topics (focus here):")
    for topic, count, avg in rows:
        color = "🔴" if avg < 2 else "🟡" if avg < 3.5 else "🟢"
        print(f"    {color} {topic:25s}  avg {avg:.1f}/5  ({count} attempts)")

    # Strongest topics
    rows = conn.execute(
        """SELECT topic, COUNT(*), AVG(correctness)
           FROM attempts GROUP BY topic 
           HAVING AVG(correctness) >= 4
           ORDER BY AVG(correctness) DESC LIMIT 3"""
    ).fetchall()

    if rows:
        print(f"\n  Strong Topics (maintain):")
        for topic, count, avg in rows:
            print(f"    🟢 {topic:25s}  avg {avg:.1f}/5  ({count} attempts)")

    # Common mistakes
    rows = conn.execute("SELECT mistakes FROM attempts WHERE mistakes != '[]'").fetchall()
    all_mistakes = []
    for (m,) in rows:
        try:
            all_mistakes.extend(json.loads(m))
        except:
            pass

    if all_mistakes:
        from collections import Counter
        common = Counter(all_mistakes).most_common(5)
        print(f"\n  Most Common Mistakes:")
        for mistake, count in common:
            print(f"    • {mistake} ({count}x)")

    # Recent trend (last 10 vs prior 10)
    recent = conn.execute(
        "SELECT AVG(correctness) FROM attempts ORDER BY id DESC LIMIT 10"
    ).fetchone()[0]
    older = conn.execute(
        """SELECT AVG(correctness) FROM attempts 
           WHERE id NOT IN (SELECT id FROM attempts ORDER BY id DESC LIMIT 10)"""
    ).fetchone()[0]

    if older is not None and recent is not None:
        diff = recent - older
        arrow = "↑" if diff > 0 else "↓" if diff < 0 else "→"
        print(f"\n  Trend: {arrow} Recent avg {recent:.1f} vs earlier {older:.1f} ({diff:+.1f})")

    # Recommendation
    weak = conn.execute(
        """SELECT topic FROM attempts 
           GROUP BY topic ORDER BY AVG(correctness) ASC LIMIT 1"""
    ).fetchone()
    if weak:
        print(f"\n  📌 NEXT SESSION: Practice {weak[0]}")
        print(f"     Run: python3 mathtutor.py practice --topic \"{weak[0]}\"")

    print(f"\n{'═' * 55}\n")
    conn.close()


def cmd_history(args):
    """Show recent attempt history."""
    conn = init_db()
    rows = conn.execute(
        """SELECT timestamp, exam, topic, subtopic, correctness 
           FROM attempts ORDER BY id DESC LIMIT 20"""
    ).fetchall()

    if not rows:
        print("No attempts yet.")
        return

    print(f"\n  {'Date':12s} {'Exam':8s} {'Topic':20s} {'Score':6s}")
    print(f"  {'─' * 50}")
    for ts, exam, topic, sub, score in rows:
        date = ts[:10]
        bar = "█" * score + "░" * (5 - score)
        label = f"{topic}"
        if sub:
            label += f" → {sub}"
        print(f"  {date:12s} {exam:8s} {label:20s} [{bar}]")

    print()
    conn.close()


# ─── MAIN ───

def main():
    parser = argparse.ArgumentParser(
        description="AI Math Tutor — JEE, ISI, CMI, anything",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 mathtutor.py solve photo.jpg --exam jee
  python3 mathtutor.py solve scan.png --exam isi  
  python3 mathtutor.py practice --exam jee --topic trigonometry
  python3 mathtutor.py practice --exam isi  (auto-picks weak topic)
  python3 mathtutor.py progress
  python3 mathtutor.py history
        """,
    )
    sub = parser.add_subparsers(dest="command")

    # solve
    p_solve = sub.add_parser("solve", help="Evaluate handwritten solution from image")
    p_solve.add_argument("image", help="Path to image (jpg/png/webp)")
    p_solve.add_argument("--exam", choices=["jee", "advanced", "isi", "cmi", "bitsat", "general"], default="general")

    # practice
    p_prac = sub.add_parser("practice", help="Generate a practice problem")
    p_prac.add_argument("--exam", choices=["jee", "advanced", "isi", "cmi", "bitsat", "general"], default="jee")
    p_prac.add_argument("--topic", help="Math topic (auto-picks weakest if omitted)")
    p_prac.add_argument("--difficulty", choices=["easy", "medium", "hard"], default="medium")

    # progress
    sub.add_parser("progress", help="Show progress dashboard")

    # history
    sub.add_parser("history", help="Show recent attempts")

    args = parser.parse_args()

    if args.command == "solve":
        cmd_solve(args)
    elif args.command == "practice":
        cmd_practice(args)
    elif args.command == "progress":
        cmd_progress(args)
    elif args.command == "history":
        cmd_history(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
