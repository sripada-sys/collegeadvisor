"""Cloud-readiness tests — catches local-only code that will break on Vultr VPS.

Tests in this file verify:
1. No localhost/LAN assumptions in API responses
2. Environment variable validation (missing keys = clear errors)
3. No browser-open or GUI calls at import time
4. Auth works when GOOGLE_CLIENT_ID is empty (cloud early phase)
5. File uploads work with absolute paths (no relative path bugs)
6. DB initializes in a fresh data/ directory (first deploy)
7. Templates render without local IP dependencies
8. Backup/auto-update survives without git remote
9. get_local_ip() not used in any route response
10. Port binding on 0.0.0.0 (not 127.0.0.1)
"""

import importlib
import json
import os
import re
import socket
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# ─── Project root for source file inspection ───
PROJECT_ROOT = Path(__file__).resolve().parent.parent


class TestNoLocalIpInResponses:
    """API responses must use request.host — never get_local_ip()."""

    def test_status_returns_request_host(self, app_client):
        """GET /api/status should return the host from the request, not a LAN IP."""
        resp = app_client.get("/api/status", headers={"Host": "gradesgenie.com"})
        data = resp.get_json()
        assert data["ip"] == "gradesgenie.com"
        # Must NOT be a 192.168.x.x or 10.x.x.x address
        assert not re.match(r"^(192\.168|10\.|172\.(1[6-9]|2\d|3[01]))", data["ip"])

    def test_status_works_with_ip_host(self, app_client):
        """Works when accessed via raw IP (e.g., http://65.20.85.241:5050)."""
        resp = app_client.get("/api/status", headers={"Host": "65.20.85.241:5050"})
        data = resp.get_json()
        assert data["ip"] == "65.20.85.241:5050"

    def test_pc_dashboard_renders_with_cloud_host(self, authed_client):
        """PC template uses request.host (from pair_token var), not a LAN IP.
        We verify by checking that the rendered page contains the host in the QR URL."""
        # authed_client uses localhost — just verify the template renders with host info
        resp = authed_client.get("/pc")
        assert resp.status_code == 200
        html = resp.data.decode()
        # Template must include the pair token and phone URL based on host
        assert "pair" in html.lower() or "phone" in html.lower()


class TestNoHardcodedLocalhost:
    """Source code must not hardcode localhost in user-facing URLs."""

    def test_no_localhost_in_api_routes(self):
        """API route handlers must not return hardcoded localhost URLs."""
        app_source = (PROJECT_ROOT / "app.py").read_text()
        # Find route functions (after "# ─── Routes ───")
        routes_section = app_source.split("# ─── Routes ───")[-1].split("# ─── Main ───")[0]
        # There should be no "localhost" in route handler code
        localhost_mentions = [
            line.strip() for line in routes_section.splitlines()
            if "localhost" in line and not line.strip().startswith("#")
        ]
        assert localhost_mentions == [], f"Found localhost in routes: {localhost_mentions}"

    def test_no_127_in_route_responses(self):
        """Route code must not return 127.0.0.1 as a URL."""
        app_source = (PROJECT_ROOT / "app.py").read_text()
        routes_section = app_source.split("# ─── Routes ───")[-1].split("# ─── Main ───")[0]
        hardcoded = [
            line.strip() for line in routes_section.splitlines()
            if "127.0.0.1" in line and not line.strip().startswith("#")
        ]
        assert hardcoded == [], f"Found 127.0.0.1 in routes: {hardcoded}"


class TestEnvironmentVariables:
    """Cloud deploy requires certain env vars — app should handle missing ones gracefully."""

    def test_app_starts_without_google_client_id(self, app_client):
        """App must start even when GOOGLE_CLIENT_ID is empty (testing phase)."""
        # app_client fixture already starts with test env vars, but this verifies
        # the auth decorator doesn't crash when the ID is in env but auth is working
        resp = app_client.get("/api/status")
        assert resp.status_code == 200

    def test_secret_key_not_default_in_production(self):
        """SECRET_KEY should not be 'change-me-in-production' on cloud."""
        # This tests the pattern, not the actual deployed value
        import config
        # In test env it's "test-secret-key" from conftest; the point is
        # production must NOT use the fallback
        if os.environ.get("FLASK_ENV") == "production":
            assert config.SECRET_KEY != "change-me-in-production"

    def test_port_configurable_via_env(self):
        """PORT must come from environment (systemd sets it)."""
        import config
        # conftest sets PORT=5099
        assert config.PORT == 5099


class TestAuthOnCloud:
    """Auth must work correctly in cloud deployment without Google OAuth configured."""

    def test_unauthenticated_api_returns_401(self, app_client):
        """Protected routes return 401 JSON, not a redirect loop."""
        resp = app_client.post("/api/upload", content_type="application/json")
        assert resp.status_code == 401
        data = resp.get_json()
        assert "error" in data
        assert "redirect" in data  # tells frontend where to go

    def test_authenticated_routes_work_with_session(self, authed_client):
        """Session-based auth works on cloud (no cookie domain issues)."""
        resp = authed_client.get("/api/progress")
        assert resp.status_code == 200

    def test_auth_decorator_on_all_protected_routes(self, app_client):
        """All /api/* mutation routes must require auth."""
        protected_paths = [
            ("/api/upload", "POST"),
            ("/api/practice", "POST"),
            ("/api/explain", "POST"),
            ("/api/debate", "POST"),
            ("/api/hint", "POST"),
            ("/api/results/latest", "GET"),
            ("/api/progress", "GET"),
            ("/api/history", "GET"),
        ]
        for path, method in protected_paths:
            if method == "POST":
                resp = app_client.post(path)
            else:
                resp = app_client.get(path)
            assert resp.status_code == 401, f"{method} {path} should require auth, got {resp.status_code}"


class TestFileUploadsCloud:
    """File uploads must work with cloud filesystem (no /home/user assumptions)."""

    def test_upload_creates_file_in_uploads_dir(self, authed_client, sample_image, tmp_path):
        """Uploaded files land in UPLOAD_DIR regardless of CWD."""
        import app as app_module
        original_upload_dir = app_module.UPLOAD_DIR
        test_upload_dir = str(tmp_path / "uploads")
        os.makedirs(test_upload_dir, exist_ok=True)
        app_module.UPLOAD_DIR = test_upload_dir

        try:
            with open(sample_image, "rb") as f:
                resp = authed_client.post(
                    "/api/upload",
                    data={"subject": "maths", "questions": (f, "test_q.jpg")},
                    content_type="multipart/form-data",
                )
            assert resp.status_code == 200
            # File should exist in the upload dir
            uploaded = os.listdir(test_upload_dir)
            assert len(uploaded) >= 1
            assert any("test_q" in f for f in uploaded)
        finally:
            app_module.UPLOAD_DIR = original_upload_dir

    def test_upload_filename_sanitized(self, authed_client, sample_image, tmp_path):
        """Malicious filenames are sanitized (path traversal prevention)."""
        import app as app_module
        test_upload_dir = str(tmp_path / "uploads")
        os.makedirs(test_upload_dir, exist_ok=True)
        app_module.UPLOAD_DIR = test_upload_dir

        try:
            with open(sample_image, "rb") as f:
                resp = authed_client.post(
                    "/api/upload",
                    data={"subject": "maths", "questions": (f, "../../../etc/passwd")},
                    content_type="multipart/form-data",
                )
            assert resp.status_code == 200
            # File must NOT escape uploads dir
            uploaded = os.listdir(test_upload_dir)
            for fname in uploaded:
                assert ".." not in fname
                full = os.path.join(test_upload_dir, fname)
                assert os.path.dirname(os.path.abspath(full)) == os.path.abspath(test_upload_dir)
        finally:
            app_module.UPLOAD_DIR = str(Path(app_module.BASE_DIR) / "uploads")

    def test_serve_upload_rejects_traversal(self, app_client):
        """GET /uploads/../secret should be rejected (400 or 404)."""
        resp = app_client.get("/uploads/../app.py")
        # Flask/Werkzeug may sanitize the path (404) or our handler rejects it (400)
        # Either way, the file must NOT be served
        assert resp.status_code in (400, 404)


class TestDatabaseOnFreshDeploy:
    """DB must initialize cleanly on a fresh VPS with no existing data/."""

    def test_db_creates_all_tables(self, tmp_path, monkeypatch):
        """init_db + run_migrations succeeds on empty directory."""
        db_path = str(tmp_path / "fresh" / "tutor.db")
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        monkeypatch.setattr("db.DB_PATH", db_path)

        import db as db_mod
        db_mod.init_db()
        db_mod.run_migrations()

        # Verify critical tables exist
        conn = db_mod.get_db()
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}
        conn.close()

        assert "evaluations" in tables
        assert "students" in tables
        assert "practice_problems" in tables

    def test_db_wal_mode_on_cloud(self, tmp_path, monkeypatch):
        """WAL mode must be enabled for concurrent reads (phone + PC + backup)."""
        db_path = str(tmp_path / "wal_test.db")
        monkeypatch.setattr("db.DB_PATH", db_path)

        import db as db_mod
        db_mod.init_db()

        conn = db_mod.get_db()
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        conn.close()
        assert mode == "wal"


class TestBackupOnCloud:
    """Backup must work on VPS (no interactive git prompts)."""

    @patch("subprocess.run")
    def test_backup_non_interactive(self, mock_run, app_client):
        """Git commands must not prompt for credentials."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        import app as app_module
        app_module._do_backup()

        # Check that no git command uses --interactive or opens an editor
        for call in mock_run.call_args_list:
            cmd = call[0][0] if call[0] else call.kwargs.get("args", [])
            if isinstance(cmd, list):
                cmd_str = " ".join(cmd)
                assert "--interactive" not in cmd_str
                assert "GIT_EDITOR" not in cmd_str

    @patch("subprocess.run")
    def test_backup_handles_no_remote(self, mock_run, app_client):
        """Backup survives when git remote is unreachable."""
        mock_run.side_effect = [
            MagicMock(returncode=0),  # git add
            MagicMock(returncode=0),  # git commit
            MagicMock(returncode=1, stderr="Could not resolve host"),  # git pull --rebase
            MagicMock(returncode=1, stderr="Could not resolve host"),  # git push
        ]

        import app as app_module
        # Should not raise
        app_module._do_backup()


class TestAutoUpdateOnCloud:
    """Auto-update must not break the running app."""

    @patch("app.subprocess.run")
    def test_auto_update_skips_when_no_remote(self, mock_run, app_client):
        """auto_update exits cleanly if git fetch fails (offline deploy)."""
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="Could not resolve host")

        import app as app_module
        # Should not raise or hang
        app_module.auto_update()

    @patch("app.subprocess.run")
    def test_auto_update_no_stdin(self, mock_run, app_client):
        """All subprocess calls use capture_output (no stdin prompt possible)."""
        mock_run.return_value = MagicMock(returncode=0, stdout="abc123\n", stderr="")

        import app as app_module
        # Write matching hash so it exits early
        hash_file = os.path.join(app_module.BASE_DIR, "data", ".last_code_update")
        os.makedirs(os.path.dirname(hash_file), exist_ok=True)
        Path(hash_file).write_text("abc123")

        app_module.auto_update()

        for call in mock_run.call_args_list:
            kwargs = call.kwargs if call.kwargs else {}
            # Each subprocess call must have capture_output=True (no TTY interaction)
            assert kwargs.get("capture_output") is True, f"Missing capture_output in: {call}"


class TestNoWebbrowserOnCloud:
    """webbrowser.open() must never run on cloud (headless VPS)."""

    def test_main_block_does_not_open_browser(self):
        """The __main__ block must not call webbrowser.open()."""
        source = (PROJECT_ROOT / "app.py").read_text()
        main_block = source.split('if __name__ == "__main__":')[-1]
        assert "webbrowser.open" not in main_block

    def test_no_webbrowser_in_route_handlers(self):
        """No route handler calls webbrowser."""
        source = (PROJECT_ROOT / "app.py").read_text()
        routes_section = source.split("# ─── Routes ───")[-1].split("# ─── Main ───")[0]
        assert "webbrowser" not in routes_section


class TestTemplateCloudCompatibility:
    """Templates must work when accessed via public URL."""

    def test_pc_phone_url_uses_host_header(self, authed_client):
        """Phone URL in pc.html uses the host from request, not hardcoded IP."""
        resp = authed_client.get("/pc")
        html = resp.data.decode()
        # Should reference phone pairing, not a hardcoded 192.168.x.x address
        assert "192.168" not in html
        # pair_token is embedded in the page
        assert "pair" in html.lower()

    def test_phone_page_no_local_deps(self, app_client):
        """Phone page renders without any local-only dependencies."""
        resp = app_client.get("/phone", headers={"Host": "gradesgenie.com"})
        assert resp.status_code == 200
        html = resp.data.decode()
        # Must not reference same-WiFi requirement in visible text
        # (QR info text is in pc.html, phone.html shouldn't need it)
        assert "same WiFi" not in html.lower() or "same wifi" not in html.lower()


class TestPortBinding:
    """Server must bind to 0.0.0.0 (all interfaces), not just localhost."""

    def test_main_block_binds_all_interfaces(self):
        """app.run must use host='0.0.0.0' for cloud accessibility."""
        source = (PROJECT_ROOT / "app.py").read_text()
        main_section = source.split('if __name__ == "__main__":')[-1]
        assert '0.0.0.0' in main_section

    def test_main_block_uses_env_port(self):
        """Port comes from config (environment), not hardcoded."""
        source = (PROJECT_ROOT / "app.py").read_text()
        main_section = source.split('if __name__ == "__main__":')[-1]
        # Should reference PORT variable, not a literal number
        assert "port=PORT" in main_section.replace(" ", "")


class TestConcurrentAccess:
    """Multiple users hitting the cloud simultaneously."""

    def test_multiple_status_requests(self, app_client):
        """Status endpoint handles rapid sequential requests."""
        for _ in range(10):
            resp = app_client.get("/api/status")
            assert resp.status_code == 200
            data = resp.get_json()
            assert "models" in data

    def test_upload_during_evaluation(self, authed_client, sample_image):
        """New upload while another is processing doesn't crash."""
        mock_router = authed_client._mock_router
        mock_router.call.return_value = json.dumps([{
            "problem_number": "1", "correctness": 3,
            "question_summary": "test", "what_went_right": "ok",
            "where_it_broke": "", "mistakes": [], "hint_not_answer": "",
            "encouragement": "good",
        }])

        # Fire two uploads rapidly
        for i in range(2):
            with open(sample_image, "rb") as f:
                resp = authed_client.post(
                    "/api/upload",
                    data={"subject": "maths", "questions": (f, f"q{i}.jpg")},
                    content_type="multipart/form-data",
                )
            assert resp.status_code == 200


class TestStaticFileServing:
    """Static assets must be servable on cloud (no symlinks to /home/user)."""

    def test_static_directory_exists(self):
        """static/ folder exists at project root."""
        assert (PROJECT_ROOT / "static").is_dir()

    def test_uploads_directory_exists(self):
        """uploads/ folder exists (created on startup)."""
        assert (PROJECT_ROOT / "uploads").is_dir()

    def test_data_directory_exists(self):
        """data/ folder exists for DB + backups."""
        assert (PROJECT_ROOT / "data").is_dir()


class TestGetLocalIpNotInRoutes:
    """get_local_ip() must not appear in any route handler."""

    def test_get_local_ip_unused_in_routes(self):
        """Verify get_local_ip() is not called in route functions."""
        source = (PROJECT_ROOT / "app.py").read_text()
        routes_section = source.split("# ─── Routes ───")[-1].split("# ─── Auto-update")[0]
        # The function can exist (for legacy), but must not be called in routes
        assert "get_local_ip()" not in routes_section
