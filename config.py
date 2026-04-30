"""
GradesGenie — Configuration.

Loads .env, exposes all settings as module-level constants.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# Load .env file
_env_path = BASE_DIR / ".env"
if _env_path.exists():
    with open(_env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))

# ─── App ───

PORT = int(os.environ.get("PORT", 5000))
SECRET_KEY = os.environ.get("SECRET_KEY", "change-me-in-production")
MAX_CONTENT_MB = 50
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "tutor.db"
LOG_FILE = DATA_DIR / "app.log"

# ─── Auth ───

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
FIREBASE_API_KEY = os.environ.get("FIREBASE_API_KEY", "")

# Session cookie duration (days)
SESSION_DURATION_DAYS = 30

# Trial duration (days)
TRIAL_DURATION_DAYS = 14

# Max new signups per IP per week (anti-abuse)
MAX_SIGNUPS_PER_IP = 2

# ─── Rate Limits ───

MAX_EVALS_PER_DAY = 20  # Per student
MAX_BATCH_IMAGES = 10

# ─── Feature Flags ───

# (voice removed — zero usage, not launching)
