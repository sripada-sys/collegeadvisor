#!/bin/bash
# Local staging — run GradesGenie on localhost:5000
# Usage: bash run_local.sh
cd "$(dirname "$0")"
export PORT=5000
export SECRET_KEY="local-dev-secret-$(whoami)"
echo "GradesGenie local staging: http://localhost:5000"
echo "Auth is active — you'll need GOOGLE_CLIENT_ID in .env"
echo "Ctrl+C to stop"
echo ""
python3 app.py
