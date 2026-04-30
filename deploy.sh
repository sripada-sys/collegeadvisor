#!/bin/bash
# GradesGenie — Deploy to Vultr VPS
# Usage: bash deploy.sh
#
# Assumes:
#   - SSH key already set up for VPS
#   - CareerPulsar is on port 8000 (nginx :443 → 8000)
#   - GradesGenie runs on port 5050 (nginx :443 /gradesgenie or separate domain)

set -e

VPS_HOST="${VPS_HOST:-root@65.20.85.241}"
REMOTE_DIR="/opt/gradesgenie"
SERVICE_NAME="gradesgenie"

echo "═══ GradesGenie Deploy ═══"
echo "Target: $VPS_HOST:$REMOTE_DIR"
echo "Access: http://65.20.85.241:5050"
echo ""

# ── 0. First-time setup (idempotent) ──
ssh "$VPS_HOST" "
    mkdir -p $REMOTE_DIR/uploads $REMOTE_DIR/data
    # Open port 5050 if ufw is active
    if command -v ufw &>/dev/null && ufw status | grep -q 'active'; then
        ufw allow 5050/tcp 2>/dev/null || true
    fi
"

# ── 1. Sync code (exclude heavy/local-only files) ──
echo "[1/4] Syncing code..."
rsync -avz --delete \
    --exclude='.git' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='.env' \
    --exclude='tutor.db' \
    --exclude='uploads/' \
    --exclude='data/app.log*' \
    --exclude='*.npy' \
    --exclude='venv/' \
    --exclude='.venv/' \
    ./ "$VPS_HOST:$REMOTE_DIR/"

# ── 2. Install deps on remote ──
echo "[2/5] Installing dependencies..."
ssh "$VPS_HOST" "cd $REMOTE_DIR && pip3 install -r requirements.txt -q"

# ── 3. Run migrations ──
echo "[3/5] Running migrations..."
ssh "$VPS_HOST" "cd $REMOTE_DIR && python3 -c 'import db; db.init_db(); db.run_migrations(); print(\"DB OK\")'"

# ── 4. Install systemd service (if not already) ──
echo "[4/5] Setting up service..."
ssh "$VPS_HOST" "
    cp $REMOTE_DIR/deploy/gradesgenie.service /etc/systemd/system/gradesgenie.service
    systemctl daemon-reload
    systemctl enable gradesgenie 2>/dev/null || true
"

# ── 5. Restart service ──
echo "[5/5] Restarting service..."
ssh "$VPS_HOST" "systemctl restart $SERVICE_NAME"

sleep 2
echo ""
echo "═══ Deployed! ═══"
echo "Live at: http://65.20.85.241:5050"
echo ""
# Quick health check
ssh "$VPS_HOST" "curl -s -o /dev/null -w 'Health: HTTP %{http_code}\n' http://127.0.0.1:5050/api/status || echo 'WARNING: service not responding yet'"
