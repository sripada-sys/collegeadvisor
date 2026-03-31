"""Database layer for tutor progress tracking."""

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
    """
    )
    conn.commit()
    conn.close()


def save_evaluation(
    batch_id, subject, exam, result, question_images=None, answer_images=None, raw_response=None
):
    conn = get_db()
    conn.execute(
        """INSERT INTO evaluations
           (batch_id, timestamp, subject, exam, problem_number, question_summary,
            topic, subtopic, correctness, is_complete, what_went_right, where_it_broke,
            mistakes, missing_concept, hint, next_practice, encouragement,
            question_images, answer_images, raw_response)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            batch_id,
            datetime.now().isoformat(),
            subject,
            exam,
            str(result.get("problem_number", "")),
            result.get("question_summary", ""),
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
