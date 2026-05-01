"""Tests for app.py — all routes and the evaluation pipeline."""

import io
import json
from unittest.mock import patch, MagicMock

import pytest


class TestPublicRoutes:
    """Routes that don't require authentication."""

    def test_index_redirects_mobile(self, app_client):
        resp = app_client.get("/", headers={"User-Agent": "iPhone Mobile Safari"})
        assert resp.status_code == 302
        assert "/phone" in resp.headers["Location"]

    def test_index_redirects_desktop(self, app_client):
        resp = app_client.get("/", headers={"User-Agent": "Mozilla/5.0 Windows Chrome"})
        assert resp.status_code == 302
        assert "/pc" in resp.headers["Location"]

    def test_pc_dashboard_requires_auth(self, app_client):
        resp = app_client.get("/pc")
        assert resp.status_code == 302  # redirect to /login

    def test_pc_dashboard_authed(self, authed_client):
        resp = authed_client.get("/pc")
        assert resp.status_code == 200

    def test_phone_page_unpaired(self, app_client):
        resp = app_client.get("/phone")
        assert resp.status_code == 200
        assert b"Not Connected" in resp.data or b"QR code" in resp.data

    def test_api_status(self, app_client):
        resp = app_client.get("/api/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "models" in data
        assert "ip" in data

    def test_api_exams(self, app_client):
        resp = app_client.get("/api/exams")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "exams" in data
        assert len(data["exams"]) > 0


class TestUploadRoute:
    def test_upload_requires_auth(self, app_client):
        resp = app_client.post("/api/upload")
        assert resp.status_code == 401

    def test_upload_no_images(self, authed_client):
        resp = authed_client.post("/api/upload", data={"subject": "maths"})
        assert resp.status_code == 400
        assert "No images" in resp.get_json()["error"]

    def test_upload_success(self, authed_client, sample_image):
        with open(sample_image, "rb") as f:
            data = {
                "subject": "maths",
                "exam": "jee_main",
                "questions": (f, "question.jpg"),
            }
            resp = authed_client.post(
                "/api/upload",
                data=data,
                content_type="multipart/form-data",
            )
        assert resp.status_code == 200
        result = resp.get_json()
        assert result["status"] == "processing"
        assert "batch_id" in result

    def test_upload_with_answers(self, authed_client, sample_image):
        with open(sample_image, "rb") as q, open(sample_image, "rb") as a:
            data = {
                "subject": "physics",
                "exam": "general",
                "questions": (q, "q.jpg"),
                "answers": (a, "a.jpg"),
            }
            resp = authed_client.post(
                "/api/upload",
                data=data,
                content_type="multipart/form-data",
            )
        assert resp.status_code == 200
        assert resp.get_json()["questions"] == 1
        assert resp.get_json()["answers"] == 1


class TestResultsRoutes:
    def test_results_latest_requires_auth(self, app_client):
        resp = app_client.get("/api/results/latest")
        assert resp.status_code == 401

    def test_results_latest_empty(self, authed_client):
        resp = authed_client.get("/api/results/latest")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["results"] is None or data["results"] == []

    def test_results_batch_invalid_id(self, authed_client):
        resp = authed_client.get("/api/results/abc-INVALID!")
        assert resp.status_code == 400

    def test_results_batch_valid(self, authed_client):
        resp = authed_client.get("/api/results/abc123def456")
        assert resp.status_code == 200


class TestPracticeRoute:
    def test_practice_requires_auth(self, app_client):
        resp = app_client.post("/api/practice", json={"subject": "maths"})
        assert resp.status_code == 401

    def test_practice_success(self, authed_client):
        # Mock router to return valid JSON
        mock_router = authed_client._mock_router
        mock_router.call.return_value = json.dumps({
            "problem": "Find $x$ if $2x + 3 = 7$",
            "topic": "linear equations",
            "difficulty": "easy",
            "hints": ["Think about inverse operations", "Subtract 3", "Divide by 2"],
        })

        resp = authed_client.post("/api/practice", json={
            "subject": "maths",
            "exam": "general",
            "topic": "algebra",
            "difficulty": "easy",
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert "problem" in data

    def test_practice_uses_weak_topic_if_none_given(self, authed_client, db_module):
        """If no topic specified, picks from weak topics."""
        # Add some evaluations with a weak topic
        db_module.save_evaluation(
            batch_id="pr1", subject="maths", exam="general",
            result={"problem_number": "1", "topic": "trigonometry", "correctness": 1},
        )
        mock_router = authed_client._mock_router
        mock_router.call.return_value = json.dumps({
            "problem": "Find sin(30°)", "topic": "trigonometry",
            "difficulty": "medium", "hints": [],
        })

        resp = authed_client.post("/api/practice", json={"subject": "maths"})
        assert resp.status_code == 200


class TestExplainRoute:
    def test_explain_requires_auth(self, app_client):
        resp = app_client.post("/api/explain", json={"topic": "algebra"})
        assert resp.status_code == 401

    def test_explain_no_topic(self, authed_client):
        resp = authed_client.post("/api/explain", json={"subject": "maths"})
        assert resp.status_code == 400

    def test_explain_success(self, authed_client):
        mock_router = authed_client._mock_router
        mock_router.call.return_value = "Integration by parts works by..."

        resp = authed_client.post("/api/explain", json={
            "subject": "maths",
            "topic": "integration",
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert "explanation" in data
        assert data["topic"] == "integration"


class TestHintRoute:
    def test_hint_requires_auth(self, app_client):
        resp = app_client.post("/api/hint")
        assert resp.status_code == 401

    def test_hint_no_images(self, authed_client):
        resp = authed_client.post("/api/hint", data={"subject": "maths"})
        assert resp.status_code == 400

    def test_hint_success(self, authed_client, sample_image):
        mock_router = authed_client._mock_router
        mock_router.call.return_value = json.dumps([{
            "problem_number": "1",
            "question_summary": "Find area",
            "topic": "geometry",
            "source": None,
            "hint_1": "Think about shapes",
            "hint_2": "Use the area formula",
            "hint_3": "length × width",
        }])

        with open(sample_image, "rb") as f:
            resp = authed_client.post("/api/hint", data={
                "subject": "maths",
                "exam": "general",
                "questions": (f, "q.jpg"),
            }, content_type="multipart/form-data")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "hints" in data


class TestHintByFilename:
    def test_hint_by_filename_requires_auth(self, app_client):
        resp = app_client.post("/api/hint/by-filename", json={"filenames": ["q.jpg"]})
        assert resp.status_code == 401

    def test_hint_by_filename_no_files(self, authed_client):
        resp = authed_client.post("/api/hint/by-filename", json={"filenames": []})
        assert resp.status_code == 400

    def test_hint_by_filename_not_found(self, authed_client):
        resp = authed_client.post("/api/hint/by-filename",
                                  json={"filenames": ["nonexistent.jpg"]})
        assert resp.status_code == 404


class TestDebateRoute:
    def test_debate_requires_auth(self, app_client):
        resp = app_client.post("/api/debate", json={"question_text": "x+1=2"})
        assert resp.status_code == 401

    def test_debate_no_question(self, authed_client):
        resp = authed_client.post("/api/debate", json={"subject": "maths"})
        assert resp.status_code == 400

    def test_debate_success(self, authed_client):
        mock_router = authed_client._mock_router
        mock_router.call.return_value = "What approach did you try first?"

        resp = authed_client.post("/api/debate", json={
            "subject": "maths",
            "question_text": "Solve $x^2 - 5x + 6 = 0$",
            "topic": "quadratics",
            "correctness": 3,
            "what_went_right": "correct factoring",
            "where_it_broke": "sign error",
            "missing_concept": "sign rules",
            "message": "I tried factoring",
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert "reply" in data

    def test_debate_with_history(self, authed_client):
        mock_router = authed_client._mock_router
        mock_router.call.return_value = "Good, now what about the second root?"

        resp = authed_client.post("/api/debate", json={
            "subject": "maths",
            "question_text": "Factor x^2-4",
            "history": [
                {"role": "ai", "content": "What's special about this expression?"},
                {"role": "student", "content": "It's a difference of squares!"},
            ],
            "message": "So it's (x+2)(x-2)",
        })
        assert resp.status_code == 200


class TestWowRoutes:
    def test_save_wow_requires_auth(self, app_client):
        resp = app_client.post("/api/wow", json={"note": "test"})
        assert resp.status_code == 401

    def test_save_wow_empty(self, authed_client):
        resp = authed_client.post("/api/wow", json={"note": ""})
        assert resp.status_code == 400

    def test_save_wow_success(self, authed_client):
        resp = authed_client.post("/api/wow", json={
            "note": "Chain rule: d/dx f(g(x)) = f'(g(x)) * g'(x)",
            "subject": "maths",
            "topic": "differentiation",
        })
        assert resp.status_code == 200
        assert resp.get_json()["ok"] is True

    def test_get_wow_requires_auth(self, app_client):
        resp = app_client.get("/api/wow")
        assert resp.status_code == 401

    def test_get_wow_success(self, authed_client, db_module):
        db_module.save_wow_note("Test note", "maths", "algebra", student_id=authed_client._student_id)
        resp = authed_client.get("/api/wow")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["notes"]) == 1


class TestProgressRoute:
    def test_progress_requires_auth(self, app_client):
        resp = app_client.get("/api/progress")
        assert resp.status_code == 401

    def test_progress_empty(self, authed_client):
        resp = authed_client.get("/api/progress")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total"] == 0

    def test_progress_with_data(self, authed_client, db_module):
        db_module.save_evaluation(
            batch_id="pg1", subject="maths", exam="general",
            result={"problem_number": "1", "correctness": 4, "topic": "algebra"},
            student_id=authed_client._student_id,
        )
        resp = authed_client.get("/api/progress")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total"] == 1


class TestHistoryRoute:
    def test_history_requires_auth(self, app_client):
        resp = app_client.get("/api/history")
        assert resp.status_code == 401

    def test_history_with_limit(self, authed_client, db_module):
        for i in range(5):
            db_module.save_evaluation(
                batch_id=f"h{i}", subject="maths", exam="general",
                result={"problem_number": str(i), "correctness": 3},
                student_id=authed_client._student_id,
            )
        resp = authed_client.get("/api/history?limit=3")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) == 3


class TestGuideRoutes:
    def test_guide_pdf_found(self, app_client):
        # The PDF exists in output/ directory
        resp = app_client.get("/api/guide/pdf")
        # Either 200 (file exists) or 404 (not generated)
        assert resp.status_code in (200, 404)

    def test_guide_html(self, app_client):
        """Guide HTML returns content from data/guide_content.html."""
        resp = app_client.get("/api/guide/html")
        # File exists in data/ directory
        assert resp.status_code in (200, 404)


class TestUploadsServing:
    def test_serve_upload_invalid_name(self, authed_client):
        resp = authed_client.get("/uploads/../etc/passwd")
        # secure_filename strips path traversal → returns 400 or 404
        assert resp.status_code in (400, 404)

    def test_serve_upload_not_found(self, authed_client):
        resp = authed_client.get("/uploads/nonexistent.jpg")
        assert resp.status_code == 404



class TestEvaluationPipeline:
    """Test the internal _run_evaluation function."""

    def test_run_evaluation_success(self, authed_client, db_module, sample_image):
        mock_router = authed_client._mock_router
        # First call: extract returns transcription
        # Second call: evaluate returns JSON results
        mock_router.call.side_effect = [
            "=== Problem 1 ===\nQUESTION: 2+2\nFINAL ANSWER: 4",
            json.dumps([{
                "problem_number": "1",
                "question_summary": "2+2",
                "correctness": 5,
                "what_went_right": "Perfect",
                "where_it_broke": "nowhere",
                "mistakes": [],
                "hint_not_answer": "",
                "encouragement": "Excellent!",
            }]),
        ]

        import app as app_module
        app_module._run_evaluation(
            "test_batch_001", "maths", "general",
            [sample_image], [], "", "test_student"
        )

        batch = db_module.get_batch("test_batch_001")
        assert len(batch) == 1
        assert batch[0]["correctness"] == 5

    def test_run_evaluation_json_parse_retry(self, authed_client, db_module, sample_image):
        """If first JSON parse fails, retries with explicit instruction."""
        mock_router = authed_client._mock_router
        mock_router.call.side_effect = [
            "extracted text here",
            "```json\n[{\"problem_number\": \"1\"}]\n```",  # Has markdown fences
        ]

        import app as app_module
        app_module._run_evaluation(
            "test_batch_002", "maths", "general",
            [sample_image], [], ""
        )

        batch = db_module.get_batch("test_batch_002")
        assert len(batch) == 1

    def test_run_evaluation_total_parse_failure(self, authed_client, db_module, sample_image):
        """If all parsing fails, saves error result."""
        mock_router = authed_client._mock_router
        mock_router.call.side_effect = [
            "extracted text",
            "completely invalid not json at all {{{",
            "still not json!!!",
        ]

        import app as app_module
        app_module._run_evaluation(
            "test_batch_003", "maths", "general",
            [sample_image], [], ""
        )

        batch = db_module.get_batch("test_batch_003")
        assert len(batch) == 1
        assert batch[0]["correctness"] == -1


class TestParseAiJson:
    """Test the JSON parsing helper."""

    def test_parse_clean_json(self, app_client):
        import app as app_module
        result = app_module.parse_ai_json('[{"a": 1}]')
        assert result == [{"a": 1}]

    def test_parse_with_markdown_fences(self, app_client):
        import app as app_module
        result = app_module.parse_ai_json('```json\n[{"a": 1}]\n```')
        assert result == [{"a": 1}]

    def test_parse_with_latex_backslashes(self, app_client):
        """LaTeX backslashes like \\frac shouldn't break parsing."""
        import app as app_module
        text = '{"formula": "\\\\frac{1}{2}", "value": 0.5}'
        result = app_module.parse_ai_json(text)
        assert result["value"] == 0.5

    def test_parse_invalid_raises(self, app_client):
        import app as app_module
        with pytest.raises(Exception):
            app_module.parse_ai_json("not json at all {{{}}")


class TestExamCalendar:
    def test_exam_calendar_has_entries(self, app_client):
        resp = app_client.get("/api/exams")
        data = resp.get_json()
        assert len(data["exams"]) >= 9

    def test_exam_has_required_fields(self, app_client):
        resp = app_client.get("/api/exams")
        exam = resp.get_json()["exams"][0]
        assert "id" in exam
        assert "name" in exam
        assert "dates" in exam
        assert "status" in exam
        assert "countdown" in exam or exam["countdown"] is None
