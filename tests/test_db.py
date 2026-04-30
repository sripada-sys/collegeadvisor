"""Tests for db.py — all database operations."""

import json
from datetime import datetime, timedelta


class TestInitAndMigrations:
    def test_init_creates_tables(self, db_module):
        conn = db_module.get_db()
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]
        conn.close()
        assert "evaluations" in tables
        assert "practice_problems" in tables
        assert "wow_notes" in tables
        assert "debate_logs" in tables
        assert "students" in tables
        assert "batch_status" in tables
        assert "events" in tables

    def test_student_id_column_added(self, db_module):
        conn = db_module.get_db()
        cols = [r[1] for r in conn.execute("PRAGMA table_info(evaluations)").fetchall()]
        conn.close()
        assert "student_id" in cols

    def test_migrations_idempotent(self, db_module):
        """Running migrations twice doesn't crash."""
        db_module.run_migrations()
        db_module.run_migrations()


class TestEvaluations:
    def test_save_and_get_evaluation(self, db_module):
        result = {
            "problem_number": "1",
            "question_summary": "Find x",
            "question_text": "$x^2 = 4$",
            "correct_answer": "$x = \\pm 2$",
            "source": "NCERT",
            "topic": "quadratics",
            "subtopic": "roots",
            "correctness": 4,
            "is_complete": True,
            "what_went_right": "Correct approach",
            "where_it_broke": "nowhere",
            "mistakes": ["minor sign error"],
            "missing_concept": "none",
            "hint_not_answer": "Think about both roots",
            "next_practice": "more quadratics",
            "encouragement": "Solid work!",
        }
        db_module.save_evaluation(
            batch_id="abc123",
            subject="maths",
            exam="jee_main",
            result=result,
            question_images=["q1.jpg"],
            answer_images=["a1.jpg"],
            raw_response="raw text here",
        )
        batch = db_module.get_batch("abc123")
        assert len(batch) == 1
        assert batch[0]["topic"] == "quadratics"
        assert batch[0]["correctness"] == 4

    def test_get_latest_batch(self, db_module):
        for i in range(3):
            db_module.save_evaluation(
                batch_id=f"batch_{i}",
                subject="maths",
                exam="general",
                result={"problem_number": str(i), "correctness": i},
            )
        latest = db_module.get_latest_batch()
        assert latest[0]["batch_id"] == "batch_2"

    def test_get_latest_batch_empty(self, db_module):
        result = db_module.get_latest_batch()
        assert result is None

    def test_get_batch_nonexistent(self, db_module):
        result = db_module.get_batch("nonexistent")
        assert result == []


class TestProgress:
    def test_empty_progress(self, db_module):
        stats = db_module.get_progress()
        assert stats["total"] == 0

    def test_progress_with_data(self, db_module):
        for i in range(5):
            db_module.save_evaluation(
                batch_id=f"b{i}",
                subject="maths" if i < 3 else "physics",
                exam="jee_main",
                result={
                    "problem_number": str(i),
                    "topic": "algebra" if i < 3 else "mechanics",
                    "correctness": i,
                    "mistakes": ["error1"] if i < 2 else [],
                },
            )
        stats = db_module.get_progress()
        assert stats["total"] == 5
        assert len(stats["by_subject"]) == 2
        assert "weak_topics" in stats
        assert "daily_trend" in stats
        assert stats["avg_score"] > 0


class TestHistory:
    def test_get_history(self, db_module):
        for i in range(5):
            db_module.save_evaluation(
                batch_id=f"h{i}", subject="maths", exam="general",
                result={"problem_number": str(i), "correctness": 3},
            )
        history = db_module.get_history(limit=3)
        assert len(history) == 3
        # Most recent first
        assert history[0]["batch_id"] == "h4"

    def test_history_limit_capped(self, db_module):
        history = db_module.get_history(limit=500)
        assert isinstance(history, list)


class TestWowNotes:
    def test_save_and_get_wow(self, db_module):
        db_module.save_wow_note("Integration by parts key insight", "maths", "integration", "debate")
        notes = db_module.get_wow_notes()
        assert len(notes) == 1
        assert "Integration by parts" in notes[0]["note"]
        assert notes[0]["source"] == "debate"

    def test_wow_notes_limit(self, db_module):
        for i in range(150):
            db_module.save_wow_note(f"Note {i}", "maths", "topic")
        notes = db_module.get_wow_notes(limit=10)
        assert len(notes) == 10


class TestDebateLogs:
    def test_save_debate_log(self, db_module):
        db_module.save_debate_log("maths", "algebra", "x+1=2", "I got x=1", "Correct!")
        conn = db_module.get_db()
        rows = conn.execute("SELECT * FROM debate_logs").fetchall()
        conn.close()
        assert len(rows) == 1
        assert rows[0]["mentor_reply"] == "Correct!"


class TestVoiceContext:
    def test_voice_context_empty(self, db_module):
        ctx = db_module.get_voice_context()
        assert "No evaluation history" in ctx

    def test_voice_context_with_data(self, db_module):
        db_module.save_evaluation(
            batch_id="voice1", subject="maths", exam="jee_main",
            result={
                "problem_number": "1", "topic": "calculus",
                "correctness": 2, "where_it_broke": "Chain rule",
                "missing_concept": "differentiation",
                "what_went_right": "good setup",
                "mistakes": ["sign error"],
            },
        )
        db_module.save_wow_note("Remember chain rule", "maths", "calculus")
        ctx = db_module.get_voice_context()
        assert "STUDENT DOSSIER" in ctx
        assert "calculus" in ctx.lower()


class TestStudents:
    def test_create_student(self, db_module):
        sid = db_module.create_student(
            google_id="g123", email="a@b.com", name="Alice",
            avatar_url="http://pic.jpg", phone="+911234567890", signup_ip="1.2.3.4",
        )
        assert len(sid) == 16

    def test_get_student(self, db_module):
        sid = db_module.create_student("g1", "x@y.com", "Bob", "", "+910000000001")
        student = db_module.get_student(sid)
        assert student["name"] == "Bob"
        assert student["plan"] == "free_trial"
        assert student["google_id"] == "g1"

    def test_get_student_nonexistent(self, db_module):
        assert db_module.get_student("fakeid") is None

    def test_get_student_by_google_id(self, db_module):
        db_module.create_student("goog99", "z@w.com", "Zara", "", "+910000000002")
        student = db_module.get_student_by_google_id("goog99")
        assert student["email"] == "z@w.com"

    def test_get_student_by_google_id_missing(self, db_module):
        assert db_module.get_student_by_google_id("nonexistent") is None

    def test_get_student_by_phone(self, db_module):
        db_module.create_student("g5", "p@q.com", "Phil", "", "+919999999999")
        student = db_module.get_student_by_phone("+919999999999")
        assert student["name"] == "Phil"

    def test_get_student_by_phone_missing(self, db_module):
        assert db_module.get_student_by_phone("+910000000000") is None

    def test_update_student_plan(self, db_module):
        sid = db_module.create_student("g6", "u@v.com", "Uma", "", "+918888888888")
        db_module.update_student_plan(sid, "paid", "2027-01-01")
        student = db_module.get_student(sid)
        assert student["plan"] == "paid"
        assert student["paid_until"] == "2027-01-01"

    def test_update_plan_without_paid_until(self, db_module):
        sid = db_module.create_student("g7", "w@x.com", "Wendy", "", "+917777777777")
        db_module.update_student_plan(sid, "expired")
        student = db_module.get_student(sid)
        assert student["plan"] == "expired"

    def test_count_recent_signups_from_ip(self, db_module):
        db_module.create_student("g8", "a1@b.com", "A1", "", "+916666666661", signup_ip="5.5.5.5")
        db_module.create_student("g9", "a2@b.com", "A2", "", "+916666666662", signup_ip="5.5.5.5")
        db_module.create_student("g10", "a3@b.com", "A3", "", "+916666666663", signup_ip="9.9.9.9")
        count = db_module.count_recent_signups_from_ip("5.5.5.5", days=7)
        assert count == 2

    def test_count_signups_zero(self, db_module):
        count = db_module.count_recent_signups_from_ip("1.1.1.1")
        assert count == 0


class TestBatchStatus:
    def test_set_and_get_batch_status(self, db_module):
        db_module.set_batch_status("batch_x", "student_1", "processing")
        status = db_module.get_batch_status("batch_x")
        assert status["status"] == "processing"
        assert status["student_id"] == "student_1"

    def test_update_batch_status(self, db_module):
        db_module.set_batch_status("batch_y", "student_2", "processing")
        db_module.set_batch_status("batch_y", "student_2", "done")
        status = db_module.get_batch_status("batch_y")
        assert status["status"] == "done"

    def test_batch_status_with_error(self, db_module):
        db_module.set_batch_status("batch_z", "student_3", "failed", "API timeout")
        status = db_module.get_batch_status("batch_z")
        assert status["status"] == "failed"
        assert status["error_message"] == "API timeout"

    def test_get_batch_status_nonexistent(self, db_module):
        assert db_module.get_batch_status("nope") is None


class TestEvents:
    def test_log_event(self, db_module):
        db_module.log_event("stu1", "upload", {"images": 3})
        conn = db_module.get_db()
        rows = conn.execute("SELECT * FROM events").fetchall()
        conn.close()
        assert len(rows) == 1
        assert rows[0]["event"] == "upload"
        meta = json.loads(rows[0]["metadata"])
        assert meta["images"] == 3

    def test_log_event_no_metadata(self, db_module):
        db_module.log_event("stu2", "login")
        conn = db_module.get_db()
        rows = conn.execute("SELECT * FROM events WHERE student_id='stu2'").fetchall()
        conn.close()
        assert rows[0]["metadata"] is None


class TestExport:
    def test_export_for_backup(self, db_module):
        db_module.save_evaluation(
            batch_id="exp1", subject="physics", exam="general",
            result={"problem_number": "1", "correctness": 5},
        )
        db_module.save_wow_note("test insight", "physics", "optics")
        export = db_module.export_for_backup()
        assert "exported_at" in export
        assert len(export["evaluations"]) == 1
        assert len(export["wow_notes"]) == 1
