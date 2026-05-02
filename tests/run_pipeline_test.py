"""
Run the GradesGenie evaluation pipeline on generated test images.
Uses Flask test client with REAL AI keys for local testing (no server needed).

Usage:
  python tests/run_pipeline_test.py [--subject SUBJ] [--id ID]

Requires .env with real GEMINI_API_KEY and OPENAI_API_KEY.
"""

import argparse
import json
import os
import sys
import time
from io import BytesIO
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TEST_DIR = Path(__file__).parent / "test_images"
MANIFEST = TEST_DIR / "manifest.json"
RESULTS_FILE = TEST_DIR / "test_results.json"


def create_test_app():
    """Create Flask test client with REAL AI models and a test student."""
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")

    import db
    import tempfile
    tmp = tempfile.mkdtemp()
    db_path = os.path.join(tmp, "pipeline_test.db")
    db.DB_PATH = db_path
    db.init_db()
    db.run_migrations()

    # Create test student
    student_id = db.create_student(
        google_id="pipeline-test",
        email="test@pipeline.local",
        name="Pipeline Test",
        avatar_url="",
        phone="",
        signup_ip="127.0.0.1",
    )

    # Import app AFTER setting env vars — uses real ModelRouter
    from unittest.mock import patch
    with patch("app.auto_update"), \
         patch("app.schedule_daily_backup"), \
         patch("app.backup_to_git"):
        import app as app_module

    app_module.app.config["TESTING"] = True
    app_module.app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "test-secret")
    client = app_module.app.test_client()
    client._student_id = student_id
    client._app_module = app_module

    # Set session
    with client.session_transaction() as sess:
        sess["student_id"] = student_id

    return client


def upload_and_wait(client, question_file, answer_file, subject, timeout=90):
    """Upload via Flask test client, wait for background thread to finish."""
    q_path = TEST_DIR / question_file
    a_path = TEST_DIR / answer_file

    data = {
        "subject": subject,
        "exam": "jee_main",
        "questions": (BytesIO(q_path.read_bytes()), question_file, "image/jpeg"),
        "answers": (BytesIO(a_path.read_bytes()), answer_file, "image/jpeg"),
    }

    resp = client.post(
        "/api/upload",
        data=data,
        content_type="multipart/form-data",
    )
    if resp.status_code != 200:
        return {"error": f"Upload failed: HTTP {resp.status_code}", "raw": resp.get_data(as_text=True)[:200]}

    upload_data = resp.get_json()
    batch_id = upload_data.get("batch_id")
    if not batch_id:
        return {"error": "No batch_id returned", "raw": str(upload_data)}

    # Poll for results (background thread is evaluating)
    start = time.time()
    while time.time() - start < timeout:
        time.sleep(2)
        resp = client.get(f"/api/results/{batch_id}")
        if resp.status_code == 200:
            rdata = resp.get_json()
            results = rdata.get("results", [])
            if results:
                return {"batch_id": batch_id, "results": results}

    return {"error": f"Timeout after {timeout}s", "batch_id": batch_id}


def evaluate_result(test_case, pipeline_result):
    """Compare pipeline output against expected values."""
    issues = []
    result = pipeline_result["results"][0] if pipeline_result.get("results") else None

    if not result:
        return {"pass": False, "issues": ["No result returned"], "score": None}

    score = result.get("correctness", 0)
    expected_min = test_case.get("expected_score_min", 0)
    expected_max = test_case.get("expected_score_max", 5)

    # Check score in expected range
    if score < expected_min:
        issues.append(f"Score {score} below expected minimum {expected_min}")
    if score > expected_max:
        issues.append(f"Score {score} above expected maximum {expected_max}")

    # For wrong answers: check that the pipeline detected errors
    if not test_case["is_correct"]:
        if score >= 4:
            issues.append(f"WRONG answer scored {score}/5 — pipeline missed the error")
        if not result.get("where_it_broke") or result["where_it_broke"].lower() == "nowhere":
            issues.append("Pipeline didn't identify where the mistake was")

    # For correct answers: check pipeline didn't penalize
    if test_case["is_correct"] and score < 4:
        issues.append(f"CORRECT answer only scored {score}/5 — false negative")

    # Check key fields are populated
    for field in ["question_text", "what_went_right"]:
        if not result.get(field):
            issues.append(f"Missing field: {field}")

    return {
        "pass": len(issues) == 0,
        "issues": issues,
        "score": score,
        "where_it_broke": result.get("where_it_broke", ""),
        "question_detected": result.get("question_text", "")[:100],
    }


def run_tests(subject_filter=None, id_filter=None):
    """Run all pipeline tests."""
    with open(MANIFEST) as f:
        manifest = json.load(f)

    if subject_filter:
        manifest = [m for m in manifest if m["subject"] == subject_filter]
    if id_filter:
        manifest = [m for m in manifest if m["id"] == id_filter]

    print(f"\n{'='*60}")
    print(f"  GradesGenie Pipeline Test — {len(manifest)} problems")
    print(f"  Mode: Flask test client with real AI models")
    print(f"{'='*60}\n")

    print("Initializing app and AI models...", flush=True)
    client = create_test_app()
    print("Ready.\n")

    all_results = []
    passed = 0
    failed = 0

    for i, tc in enumerate(manifest):
        tag = f"[{i+1}/{len(manifest)}]"
        label = f"{tc['id']} ({tc['subject']}/{tc['topic']}/{tc['difficulty']})"
        is_wrong = " [WRONG ANSWER]" if not tc["is_correct"] else ""
        print(f"{tag} Testing {label}{is_wrong}...", end=" ", flush=True)

        result = upload_and_wait(
            client,
            tc["question_file"], tc["answer_file"],
            tc["subject"],
        )

        if "error" in result:
            print(f"ERROR: {result['error']}")
            eval_result = {"pass": False, "issues": [result["error"]], "score": None}
        else:
            eval_result = evaluate_result(tc, result)
            status = "PASS ✓" if eval_result["pass"] else "FAIL ✗"
            score_str = f"{eval_result['score']}/5"
            print(f"{score_str} — {status}")
            if eval_result["issues"]:
                for issue in eval_result["issues"]:
                    print(f"         ⚠ {issue}")

        if eval_result["pass"]:
            passed += 1
        else:
            failed += 1

        all_results.append({
            "test_case": tc,
            "pipeline_output": result,
            "evaluation": eval_result,
        })

        # Small delay between requests
        time.sleep(1)

    # Save results
    with open(RESULTS_FILE, "w") as f:
        json.dump(all_results, f, indent=2, default=str)

    # Summary
    print(f"\n{'='*60}")
    print(f"  RESULTS: {passed} passed, {failed} failed out of {len(manifest)}")
    print(f"  Pass rate: {passed/len(manifest)*100:.0f}%")
    print(f"{'='*60}")

    # Per-subject breakdown
    for subj in ["maths", "physics", "chemistry"]:
        subj_results = [r for r in all_results if r["test_case"]["subject"] == subj]
        if not subj_results:
            continue
        s_pass = sum(1 for r in subj_results if r["evaluation"]["pass"])
        s_scores = [r["evaluation"]["score"] for r in subj_results if r["evaluation"]["score"] is not None]
        avg = sum(s_scores) / len(s_scores) if s_scores else 0
        print(f"  {subj:12s}: {s_pass}/{len(subj_results)} passed, avg score {avg:.1f}/5")

    # Error detection accuracy
    wrong_cases = [r for r in all_results if not r["test_case"]["is_correct"]]
    if wrong_cases:
        detected = sum(1 for r in wrong_cases
                       if r["evaluation"]["score"] is not None and r["evaluation"]["score"] < 4)
        print(f"\n  Error detection: {detected}/{len(wrong_cases)} wrong answers correctly flagged")

    print(f"\n  Full results: {RESULTS_FILE}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GradesGenie Pipeline Test")
    parser.add_argument("--subject", choices=["maths", "physics", "chemistry"])
    parser.add_argument("--id", help="Run single test by ID (e.g. m09)")
    args = parser.parse_args()

    if not MANIFEST.exists():
        print("No test images found. Run generate_test_images.py first.")
        sys.exit(1)

    run_tests(args.subject, args.id)
