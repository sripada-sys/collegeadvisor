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

        CREATE TABLE IF NOT EXISTS wow_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            subject TEXT,
            topic TEXT,
            note TEXT NOT NULL,
            source TEXT DEFAULT 'debate'
        );
        CREATE INDEX IF NOT EXISTS idx_wow_timestamp ON wow_notes(timestamp);

        CREATE TABLE IF NOT EXISTS debate_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            subject TEXT,
            topic TEXT,
            question_text TEXT,
            student_message TEXT,
            mentor_reply TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_debate_timestamp ON debate_logs(timestamp);
    """
    )
    conn.commit()
    # Migrate existing databases — rename aha_notes → wow_notes if old name exists
    try:
        conn.execute("ALTER TABLE aha_notes RENAME TO wow_notes")
        conn.commit()
    except Exception:
        pass  # Already renamed or doesn't exist
    # Add new columns if they don't exist yet
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
                  correctness, is_complete, encouragement, batch_id,
                  question_text, question_summary, what_went_right, where_it_broke,
                  mistakes, missing_concept, correct_answer
           FROM evaluations ORDER BY id DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def save_wow_note(note, subject="", topic="", source="debate"):
    conn = get_db()
    conn.execute(
        "INSERT INTO wow_notes (timestamp, subject, topic, note, source) VALUES (?,?,?,?,?)",
        (datetime.now().isoformat(), subject, topic, note, source),
    )
    conn.commit()
    conn.close()


def get_wow_notes(limit=100):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM wow_notes ORDER BY id DESC LIMIT ?", (limit,)
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

    # ── Recent wow notes (last 20) ────────────────────────────────────────
    conn2 = get_db()
    wow_rows = conn2.execute(
        "SELECT note, subject, topic, source FROM wow_notes ORDER BY id DESC LIMIT 20"
    ).fetchall()
    conn2.close()
    if wow_rows:
        lines.append("STUDENT'S WOW NOTES (key insights they've captured):")
        for r in wow_rows:
            tag = "(student)" if r["source"] == "debate" and r["source"] != "auto" else "(auto-captured)"
            lines.append(f"  • [{r['topic'] or r['subject'] or 'general'}] {r['note']} {tag}")
        lines.append("")

    return "\n".join(lines)


def save_debate_log(subject, topic, question_text, student_message, mentor_reply):
    conn = get_db()
    conn.execute(
        """INSERT INTO debate_logs
           (timestamp, subject, topic, question_text, student_message, mentor_reply)
           VALUES (?,?,?,?,?,?)""",
        (datetime.now().isoformat(), subject or "", topic or "",
         question_text or "", student_message or "", mentor_reply or ""),
    )
    conn.commit()
    conn.close()


def export_for_backup():
    """Export entire DB as JSON for git backup."""
    conn = get_db()
    evaluations = conn.execute("SELECT * FROM evaluations ORDER BY id").fetchall()
    practice = conn.execute("SELECT * FROM practice_problems ORDER BY id").fetchall()
    wow_notes = conn.execute("SELECT * FROM wow_notes ORDER BY id").fetchall()
    debate_logs = conn.execute("SELECT * FROM debate_logs ORDER BY id").fetchall()
    conn.close()
    return {
        "exported_at": datetime.now().isoformat(),
        "evaluations": [dict(r) for r in evaluations],
        "practice_problems": [dict(r) for r in practice],
        "wow_notes": [dict(r) for r in wow_notes],
        "debate_logs": [dict(r) for r in debate_logs],
    }


# ─── Multi-Tenant (GradesGenie) ───


def run_migrations():
    """Run schema migrations for multi-tenant support. Safe to call multiple times."""
    conn = get_db()

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS students (
            id TEXT PRIMARY KEY,
            google_id TEXT UNIQUE,
            email TEXT UNIQUE,
            name TEXT,
            avatar_url TEXT,
            phone TEXT UNIQUE,
            grade TEXT,
            target_exams TEXT,
            plan TEXT DEFAULT 'free_trial',
            trial_start TEXT,
            paid_until TEXT,
            signup_ip TEXT,
            created_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_students_google ON students(google_id);
        CREATE INDEX IF NOT EXISTS idx_students_phone ON students(phone);

        CREATE TABLE IF NOT EXISTS batch_status (
            batch_id TEXT PRIMARY KEY,
            student_id TEXT,
            status TEXT DEFAULT 'processing',
            error_message TEXT,
            created_at TEXT,
            updated_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_batch_student ON batch_status(student_id);

        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT,
            event TEXT,
            metadata TEXT,
            created_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_events_student ON events(student_id);
    """)
    conn.commit()

    # Add student_id to existing tables (ALTER TABLE is no-op if column exists)
    for table in ["evaluations", "practice_problems", "wow_notes", "debate_logs"]:
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN student_id TEXT")
            conn.commit()
        except Exception:
            pass  # Column already exists

    conn.close()


def create_student(google_id, email, name, avatar_url, phone, signup_ip=""):
    """Create a new student account. Returns student_id."""
    import uuid
    student_id = uuid.uuid4().hex[:16]
    conn = get_db()
    conn.execute(
        """INSERT INTO students (id, google_id, email, name, avatar_url, phone,
           plan, trial_start, signup_ip, created_at)
           VALUES (?, ?, ?, ?, ?, ?, 'free_trial', ?, ?, ?)""",
        (student_id, google_id, email, name, avatar_url, phone,
         datetime.now().isoformat(), signup_ip, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()
    return student_id


def get_student(student_id):
    """Get student by ID."""
    conn = get_db()
    row = conn.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_student_by_google_id(google_id):
    """Get student by Google OAuth ID."""
    conn = get_db()
    row = conn.execute("SELECT * FROM students WHERE google_id = ?", (google_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_student_by_phone(phone):
    """Get student by phone number."""
    conn = get_db()
    row = conn.execute("SELECT * FROM students WHERE phone = ?", (phone,)).fetchone()
    conn.close()
    return dict(row) if row else None


def update_student_plan(student_id, plan, paid_until=None):
    """Update a student's plan status."""
    conn = get_db()
    if paid_until:
        conn.execute("UPDATE students SET plan = ?, paid_until = ? WHERE id = ?",
                     (plan, paid_until, student_id))
    else:
        conn.execute("UPDATE students SET plan = ? WHERE id = ?", (plan, student_id))
    conn.commit()
    conn.close()


def count_recent_signups_from_ip(ip, days=7):
    """Count signups from an IP in the last N days."""
    from datetime import timedelta
    conn = get_db()
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    row = conn.execute(
        "SELECT COUNT(*) as c FROM students WHERE signup_ip = ? AND created_at > ?",
        (ip, cutoff)
    ).fetchone()
    conn.close()
    return row["c"] if row else 0


def set_batch_status(batch_id, student_id, status, error_message=None):
    """Create or update batch processing status."""
    conn = get_db()
    conn.execute(
        """INSERT INTO batch_status (batch_id, student_id, status, error_message, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(batch_id) DO UPDATE SET status=?, error_message=?, updated_at=?""",
        (batch_id, student_id, status, error_message,
         datetime.now().isoformat(), datetime.now().isoformat(),
         status, error_message, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def get_batch_status(batch_id):
    """Get status of a batch."""
    conn = get_db()
    row = conn.execute("SELECT * FROM batch_status WHERE batch_id = ?", (batch_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def log_event(student_id, event, metadata=None):
    """Log a lightweight analytics event."""
    conn = get_db()
    conn.execute(
        "INSERT INTO events (student_id, event, metadata, created_at) VALUES (?, ?, ?, ?)",
        (student_id, event, json.dumps(metadata) if metadata else None,
         datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()
