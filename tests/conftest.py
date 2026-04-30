"""Shared test fixtures."""

import os
import sys
import tempfile

import pytest

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set test env vars BEFORE any imports
os.environ["GEMINI_API_KEY"] = "test-gemini-key"
os.environ["OPENAI_API_KEY"] = "test-openai-key"
os.environ["GOOGLE_CLIENT_ID"] = "test-google-client-id.apps.googleusercontent.com"
os.environ["GOOGLE_CLIENT_SECRET"] = "test-google-secret"
os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["PORT"] = "5099"


@pytest.fixture
def tmp_db(monkeypatch, tmp_path):
    """Create a fresh temp DB for each test."""
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr("db.DB_PATH", db_path)
    import db
    db.init_db()
    db.run_migrations()
    return db_path


@pytest.fixture
def db_module(tmp_db):
    """Return db module with a fresh temp DB."""
    import db
    return db


@pytest.fixture
def app_client(monkeypatch, tmp_path):
    """Create a Flask test client with mocked AI router and temp DB."""
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr("db.DB_PATH", db_path)

    # Mock ModelRouter to avoid real API calls
    from unittest.mock import MagicMock, patch

    mock_router = MagicMock()
    mock_router.status.return_value = {
        "available": ["openai"],
        "health": {"openai": {"status": "ok", "message": "Working"}},
        "assignments": {"extract": "openai", "evaluate": "openai", "practice": "openai",
                        "explain": "openai", "debate": "openai", "read_image": "openai"},
    }
    mock_router.call.return_value = '[]'
    mock_router.available = {"openai": True}

    with patch("app.ModelRouter", return_value=mock_router):
        with patch("app.auto_update"):
            with patch("app.schedule_daily_backup"):
                with patch("app.backup_to_git"):
                    with patch("app.webbrowser.open"):
                        import importlib
                        import db
                        db.init_db()
                        db.run_migrations()

                        import app as app_module
                        app_module.router = mock_router
                        app_module.app.config["TESTING"] = True
                        app_module.app.config["SECRET_KEY"] = "test-secret"

                        client = app_module.app.test_client()
                        client._mock_router = mock_router
                        client._app_module = app_module
                        yield client


@pytest.fixture
def authed_client(app_client, db_module):
    """Test client with an authenticated session (student logged in)."""
    # Create a test student
    student_id = db_module.create_student(
        google_id="google-123",
        email="test@example.com",
        name="Test Student",
        avatar_url="",
        phone="+919876543210",
        signup_ip="127.0.0.1",
    )
    # Set session
    with app_client.session_transaction() as sess:
        sess["student_id"] = student_id
    app_client._student_id = student_id
    return app_client


@pytest.fixture
def sample_image(tmp_path):
    """Create a minimal JPEG file for upload tests."""
    # Minimal valid JPEG (1x1 pixel, white)
    jpeg_bytes = (
        b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00'
        b'\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t'
        b'\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a'
        b'\x1f\x1e\x1d\x1a\x1c\x1c $.\' ",#\x1c\x1c(7),01444\x1f\'9=8'
        b'3<.telerik34\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00'
        b'\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00'
        b'\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b'
        b'\xff\xc4\x00\xb5\x10\x00\x02\x01\x03\x03\x02\x04\x03\x05\x05\x04'
        b'\x04\x00\x00\x01}\x01\x02\x03\x00\x04\x11\x05\x12!1A\x06\x13Qa'
        b'\x07"q\x142\x81\x91\xa1\x08#B\xb1\xc1\x15R\xd1\xf0$3br\x82\t\n'
        b'\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xfb\xd2\x8a(\x03\xff\xd9'
    )
    img_path = tmp_path / "test_question.jpg"
    img_path.write_bytes(jpeg_bytes)
    return str(img_path)
