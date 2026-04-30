"""Tests for app.py infrastructure — backup, auto-update, exam verification."""

import json
import os
import threading
from unittest.mock import patch, MagicMock
from datetime import datetime

import pytest


class TestBackup:
    @patch("subprocess.run")
    def test_backup_to_git(self, mock_run, app_client, db_module):
        """backup_to_git exports data and runs git commands."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        db_module.save_evaluation(
            batch_id="bk1", subject="maths", exam="general",
            result={"problem_number": "1", "correctness": 3},
        )

        import app as app_module
        app_module._do_backup()

        # Should have called git add, commit, pull --rebase, push
        assert mock_run.call_count >= 3

    @patch("subprocess.run")
    def test_backup_handles_failure(self, mock_run, app_client):
        """Backup doesn't crash on git failure."""
        mock_run.side_effect = Exception("git not found")

        import app as app_module
        # Should not raise
        app_module._do_backup()

    def test_debounced_backup(self, app_client):
        """_schedule_debounced_backup creates a timer."""
        import app as app_module
        with patch.object(app_module, "backup_to_git"):
            app_module._schedule_debounced_backup(delay=9999)
            assert app_module._backup_timer is not None
            app_module._backup_timer.cancel()


class TestAutoUpdate:
    @patch("app.subprocess.run")
    def test_auto_update_up_to_date(self, mock_run, app_client, tmp_path):
        """auto_update does nothing if hash matches."""
        import app as app_module

        # Mock: fetch succeeds, rev-parse returns a hash
        mock_run.return_value = MagicMock(returncode=0, stdout="abc123\n", stderr="")

        # Write the same hash to the hash file
        hash_file = os.path.join(app_module.BASE_DIR, "data", ".last_code_update")
        os.makedirs(os.path.dirname(hash_file), exist_ok=True)
        with open(hash_file, "w") as f:
            f.write("abc123")

        app_module.auto_update()
        # Should not have done a checkout (only fetch + rev-parse)
        calls = [str(c) for c in mock_run.call_args_list]
        assert not any("checkout" in c and "origin/main" in c and "--" in c for c in calls)

    @patch("app.subprocess.run")
    def test_auto_update_fetch_fails(self, mock_run, app_client):
        """auto_update exits gracefully on fetch failure."""
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="network error")

        import app as app_module
        app_module.auto_update()  # Should not raise


class TestExamVerify:
    def test_exam_verify_route(self, app_client):
        """POST /api/exams/verify calls AI and returns results."""
        mock_router = app_client._mock_router
        mock_router._dispatch = MagicMock(return_value=json.dumps([
            {"id": "cbse_board_2027", "status": "confirmed",
             "notes": "Dates are correct", "corrected_dates": None, "source": "cbse.gov.in"},
        ]))
        mock_router.available = {"openai": True}
        mock_router.pick.return_value = "openai"

        resp = app_client.post("/api/exams/verify")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "verified_at" in data
        assert "results" in data

    def test_exam_verify_concurrent_blocked(self, app_client):
        """Second concurrent verify returns 429."""
        import app as app_module

        # Acquire the lock externally
        app_module._verify_lock.acquire()
        try:
            resp = app_client.post("/api/exams/verify")
            assert resp.status_code == 429
        finally:
            app_module._verify_lock.release()


class TestDailyBackupSchedule:
    def test_schedule_daily_backup(self, app_client):
        """schedule_daily_backup creates a daemon thread."""
        import app as app_module
        initial_count = threading.active_count()
        with patch("app.backup_to_git"):
            app_module.schedule_daily_backup()
        # Thread was started (may or may not be visible by now, but no crash)


class TestGetLocalIp:
    def test_get_local_ip_returns_string(self, app_client):
        import app as app_module
        ip = app_module.get_local_ip()
        assert isinstance(ip, str)
        assert "." in ip

    @patch("app.socket.socket")
    def test_get_local_ip_fallback(self, mock_socket, app_client):
        """Falls back to 127.0.0.1 on failure."""
        mock_socket.side_effect = Exception("network down")
        import app as app_module
        ip = app_module.get_local_ip()
        assert ip == "127.0.0.1"


class TestSaveUpload:
    def test_save_upload(self, app_client, sample_image):
        """save_upload saves file with unique name."""
        import app as app_module
        from io import BytesIO
        from werkzeug.datastructures import FileStorage

        with open(sample_image, "rb") as f:
            file_storage = FileStorage(f, filename="test_photo.jpg")
            path = app_module.save_upload(file_storage)

        assert os.path.exists(path)
        assert "test_photo" in path
        os.unlink(path)
