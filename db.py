"""Database layer for mentor progress tracking."""

import json
import os
import sqlite3
from collections import Counter
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tutor.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = get_db()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS evaluations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            subject TEXT NOT NULL,
            exam TEXT DEFAULT 'general',
            problem_number TEXT,
            question_summary TEXT,
            question_text TEXT,
            correct_answer TEXT,
            source TEXT,
            topic TEXT,
            subtopic TEXT,
            correctness INTEGER DEFAULT 0,
            is_complete BOOLEAN DEFAULT 0,
            what_went_right TEXT,
            where_it_broke TEXT,
            mistakes TEXT,
            missing_concept TEXT,
            hint TEXT,
            next_practice TEXT,
            encouragement TEXT,
            question_images TEXT,
            answer_images TEXT,
            raw_response TEXT
        );

        CREATE TABLE IF NOT EXISTS practice_problems (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            subject TEXT,
            exam TEXT,
            topic TEXT,
            difficulty TEXT,
            problem_text TEXT,
            hints TEXT,
            attempted BOOLEAN DEFAULT 0
        );

        CREATE INDEX IF NOT EXISTS idx_eval_timestamp ON evaluations(timestamp);
        CREATE INDEX IF NOT EXISTS idx_eval_subject ON evaluations(subject);
        CREATE INDEX IF NOT EXISTS idx_eval_batch ON evaluations(batch_id);

        CREATE TABLE IF NOT EXISTS aha_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            subject TEXT,
            topic TEXT,
            note TEXT NOT NULL,
            source TEXT DEFAULT 'debate'
        );
        CREATE INDEX IF NOT EXISTS idx_aha_timestamp ON aha_notes(timestamp);
    """
    )
    conn.commit()
    # Migrate existing databases — add new columns if they don't exist yet
    for _col, _coltype in [("question_text", "TEXT"), ("correct_answer", "TEXT"), ("source", "TEXT")]:
        try:
            conn.execute(f"ALTER TABLE evaluations ADD COLUMN {_col} {_coltype}")
            conn.commit()
        except Exception:
            pass  # Column already exists
    conn.close()


def save_evaluation(
    batch_id, subject, exam, result, question_images=None, answer_images=None, raw_response=None
):
    conn = get_db()
    conn.execute(
        """INSERT INTO evaluations
           (batch_id, timestamp, subject, exam, problem_number, question_summary,
            question_text, correct_answer, source,
            topic, subtopic, correctness, is_complete, what_went_right, where_it_broke,
            mistakes, missing_concept, hint, next_practice, encouragement,
            question_images, answer_images, raw_response)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            batch_id,
            datetime.now().isoformat(),
            subject,
            exam,
            str(result.get("problem_number", "")),
            result.get("question_summary", ""),
            result.get("question_text", ""),
            result.get("correct_answer", ""),
            result.get("source", ""),
            result.get("topic", ""),
            result.get("subtopic", ""),
            result.get("correctness", 0),
            result.get("is_complete", False),
            result.get("what_went_right", ""),
            result.get("where_it_broke", ""),
            json.dumps(result.get("mistakes", [])),
            result.get("missing_concept", ""),
            result.get("hint_not_answer", ""),
            result.get("next_practice", ""),
            result.get("encouragement", ""),
            json.dumps(question_images or []),
            json.dumps(answer_images or []),
            raw_response,
        ),
    )
    conn.commit()
    conn.close()


def get_latest_batch():
    conn = get_db()
    row = conn.execute(
        "SELECT DISTINCT batch_id FROM evaluations ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if not row:
        conn.close()
        return None
    batch_id = row["batch_id"]
    rows = conn.execute(
        "SELECT * FROM evaluations WHERE batch_id = ? ORDER BY id", (batch_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_batch(batch_id):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM evaluations WHERE batch_id = ? ORDER BY id", (batch_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_progress():
    conn = get_db()
    stats = {}

    stats["total"] = conn.execute("SELECT COUNT(*) as c FROM evaluations").fetchone()["c"]
    if stats["total"] == 0:
        conn.close()
        return stats

    # By subject
    rows = conn.execute(
        """SELECT subject, COUNT(*) as count, ROUND(AVG(correctness), 1) as avg_score,
                  SUM(CASE WHEN correctness >= 4 THEN 1 ELSE 0 END) as solid
           FROM evaluations GROUP BY subject"""
    ).fetchall()
    stats["by_subject"] = [dict(r) for r in rows]

    # By exam
    rows = conn.execute(
        """SELECT exam, COUNT(*) as count, ROUND(AVG(correctness), 1) as avg_score
           FROM evaluations GROUP BY exam"""
    ).fetchall()
    stats["by_exam"] = [dict(r) for r in rows]

    # Weakest topics
    rows = conn.execute(
        """SELECT topic, subject, COUNT(*) as count, ROUND(AVG(correctness), 1) as avg_score
           FROM evaluations WHERE topic != ''
           GROUP BY topic ORDER BY avg_score ASC LIMIT 8"""
    ).fetchall()
    stats["weak_topics"] = [dict(r) for r in rows]

    # Strongest topics
    rows = conn.execute(
        """SELECT topic, subject, COUNT(*) as count, ROUND(AVG(correctness), 1) as avg_score
           FROM evaluations WHERE topic != ''
           GROUP BY topic HAVING AVG(correctness) >= 4
           ORDER BY avg_score DESC LIMIT 5"""
    ).fetchall()
    stats["strong_topics"] = [dict(r) for r in rows]

    # Common mistakes
    rows = conn.execute("SELECT mistakes FROM evaluations WHERE mistakes != '[]'").fetchall()
    all_mistakes = []
    for r in rows:
        try:
            all_mistakes.extend(json.loads(r["mistakes"]))
        except (json.JSONDecodeError, TypeError):
            pass
    if all_mistakes:
        stats["common_mistakes"] = Counter(all_mistakes).most_common(5)

    # Daily trend (last 14 days)
    rows = conn.execute(
        """SELECT DATE(timestamp) as day, COUNT(*) as count,
                  ROUND(AVG(correctness), 1) as avg_score
           FROM evaluations
           GROUP BY DATE(timestamp) ORDER BY day DESC LIMIT 14"""
    ).fetchall()
    stats["daily_trend"] = [dict(r) for r in rows]

    stats["avg_score"] = round(
        conn.execute("SELECT AVG(correctness) FROM evaluations").fetchone()[0] or 0, 1
    )

    conn.close()
    return stats


def get_history(limit=50):
    conn = get_db()
    rows = conn.execute(
        """SELECT id, timestamp, subject, exam, problem_number, topic, subtopic,
                  correctness, is_complete, encouragement, batch_id
           FROM evaluations ORDER BY id DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def save_aha_note(note, subject="", topic="", source="debate"):
    conn = get_db()
    conn.execute(
        "INSERT INTO aha_notes (timestamp, subject, topic, note, source) VALUES (?,?,?,?,?)",
        (datetime.now().isoformat(), subject, topic, note, source),
    )
    conn.commit()
    conn.close()


def get_aha_notes(limit=100):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM aha_notes ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_voice_context():
    """Build a rich student dossier for Gemini Live's system prompt.

    Returns a plain-text string covering:
    - Today's session (latest batch)
    - 30-day recurring weak concepts and mistakes
    - Subject-wise strengths and averages
    - Overall stats
    """
    conn = get_db()

    # ── Overall stats ──────────────────────────────────────────────────────
    total = conn.execute("SELECT COUNT(*) FROM evaluations").fetchone()[0]
    if total == 0:
        conn.close()
        return "No evaluation history yet. This is a fresh start."

    avg = conn.execute("SELECT ROUND(AVG(correctness),1) FROM evaluations").fetchone()[0] or 0

    # ── Latest batch (today's session) ────────────────────────────────────
    batch_row = conn.execute(
        "SELECT DISTINCT batch_id FROM evaluations ORDER BY id DESC LIMIT 1"
    ).fetchone()
    latest_lines = []
    if batch_row:
        rows = conn.execute(
            "SELECT problem_number, topic, subtopic, correctness, where_it_broke, "
            "missing_concept, what_went_right, question_text FROM evaluations "
            "WHERE batch_id = ? ORDER BY id",
            (batch_row["batch_id"],),
        ).fetchall()
        for r in rows:
            score = r["correctness"] or 0
            status = "correct" if score >= 4 else "almost" if score == 3 else "needs work"
            line = f"  Q{r['problem_number']} ({r['topic'] or 'unknown'}) — {status} [{score}/5]"
            if r["where_it_broke"] and r["where_it_broke"].lower() not in ("nowhere", "none", ""):
                line += f". Slipped: {r['where_it_broke']}"
            if r["missing_concept"] and r["missing_concept"].lower() not in ("none", ""):
                line += f". Missing: {r['missing_concept']}"
            latest_lines.append(line)

    # ── 30-day weak concepts (frequency ranked) ───────────────────────────
    mc_rows = conn.execute(
        """SELECT missing_concept, COUNT(*) as cnt
           FROM evaluations
           WHERE missing_concept != '' AND missing_concept IS NOT NULL
             AND LOWER(missing_concept) NOT IN ('none','n/a','unknown','')
             AND timestamp >= datetime('now','-30 days')
           GROUP BY LOWER(missing_concept)
           ORDER BY cnt DESC LIMIT 8"""
    ).fetchall()

    # ── 30-day recurring mistakes ─────────────────────────────────────────
    mistake_rows = conn.execute(
        "SELECT mistakes FROM evaluations "
        "WHERE mistakes != '[]' AND timestamp >= datetime('now','-30 days')"
    ).fetchall()
    all_mistakes: list = []
    for r in mistake_rows:
        try:
            all_mistakes.extend(json.loads(r["mistakes"]))
        except Exception:
            pass
    mistake_counts = Counter(all_mistakes).most_common(6)

    # ── Subject averages (last 30 days) ───────────────────────────────────
    subj_rows = conn.execute(
        """SELECT subject, COUNT(*) as cnt, ROUND(AVG(correctness),1) as avg
           FROM evaluations
           WHERE timestamp >= datetime('now','-30 days')
           GROUP BY subject ORDER BY avg ASC"""
    ).fetchall()

    # ── Weak topics (all time) ────────────────────────────────────────────
    weak_rows = conn.execute(
        """SELECT topic, subject, COUNT(*) as cnt, ROUND(AVG(correctness),1) as avg
           FROM evaluations WHERE topic != ''
           GROUP BY topic HAVING cnt >= 2
           ORDER BY avg ASC LIMIT 6"""
    ).fetchall()

    conn.close()

    # ── Assemble plain-text dossier ───────────────────────────────────────
    lines = [
        f"STUDENT DOSSIER (Class 12, JEE prep)",
        f"Total questions evaluated all-time: {total} | Overall avg score: {avg}/5",
        "",
    ]

    if latest_lines:
        lines.append("TODAY'S SESSION:")
        lines.extend(latest_lines)
        lines.append("")

    if mc_rows:
        lines.append("TOP RECURRING KNOWLEDGE GAPS (last 30 days):")
        for r in mc_rows:
            lines.append(f"  • {r['missing_concept']} (missed {r['cnt']} time{'s' if r['cnt']>1 else ''})")
        lines.append("")

    if mistake_counts:
        lines.append("MOST COMMON MISTAKES (last 30 days):")
        for m, cnt in mistake_counts:
            lines.append(f"  • {m} ({cnt}x)")
        lines.append("")

    if weak_rows:
        lines.append("WEAKEST TOPICS (all-time, ≥2 attempts):")
        for r in weak_rows:
            lines.append(f"  • {r['topic']} ({r['subject']}) — avg {r['avg']}/5 over {r['cnt']} questions")
        lines.append("")

    if subj_rows:
        lines.append("SUBJECT PERFORMANCE (last 30 days):")
        for r in subj_rows:
            lines.append(f"  • {r['subject'].capitalize()}: avg {r['avg']}/5 ({r['cnt']} questions)")
        lines.append("")

    return "\n".join(lines)


def export_for_backup():
    """Export entire DB as JSON for git backup."""
    conn = get_db()
    evaluations = conn.execute("SELECT * FROM evaluations ORDER BY id").fetchall()
    practice = conn.execute("SELECT * FROM practice_problems ORDER BY id").fetchall()
    conn.close()
    return {
        "exported_at": datetime.now().isoformat(),
        "evaluations": [dict(r) for r in evaluations],
        "practice_problems": [dict(r) for r in practice],
    }
