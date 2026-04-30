"""Tests for config.py — settings loading."""

import os


def test_config_loads_defaults():
    """Config provides sane defaults without .env."""
    import config
    assert config.PORT == 5099  # from test env
    assert config.SECRET_KEY == "test-secret-key"
    assert config.SESSION_DURATION_DAYS == 30
    assert config.TRIAL_DURATION_DAYS == 14
    assert config.MAX_SIGNUPS_PER_IP == 2
    assert config.MAX_EVALS_PER_DAY == 20


def test_config_google_auth_vars():
    """Google OAuth vars loaded from env."""
    import config
    assert config.GOOGLE_CLIENT_ID == "test-google-client-id.apps.googleusercontent.com"
    assert config.GOOGLE_CLIENT_SECRET == "test-google-secret"


def test_config_paths_exist():
    """Config path objects are valid."""
    import config
    assert config.BASE_DIR.exists()
    assert config.UPLOAD_DIR.exists()
    assert config.DATA_DIR.exists()
