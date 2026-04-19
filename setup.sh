#!/bin/bash
# MathTutor — One-time setup for Linux PC
# Run: bash setup.sh

set -e

echo "═══════════════════════════════════════"
echo "  MathTutor Setup"
echo "═══════════════════════════════════════"

# Install Python dependencies
echo "[1/4] Installing Python packages..."
pip3 install -r requirements.txt

# Create .env from template if not exists
if [ ! -f .env ]; then
    cp .env.example .env
    echo "[2/4] Created .env — EDIT THIS FILE to add your API keys!"
    echo "       At minimum, add GEMINI_API_KEY (free from aistudio.google.com)"
else
    echo "[2/4] .env already exists — skipping"
fi

# Configure git credentials so backup pushes work
if [ -f .env ]; then
    GITHUB_TOKEN=$(grep '^GITHUB_TOKEN=' .env | cut -d= -f2 | tr -d '"' | tr -d "'")
    if [ -n "$GITHUB_TOKEN" ]; then
        git remote set-url origin "https://${GITHUB_TOKEN}@github.com/sripada-sys/collegeadvisor.git"
        echo "[2b] Git backup credentials configured"
    else
        echo "[2b] WARNING: GITHUB_TOKEN not set in .env — progress backups will not push to GitHub"
    fi
fi

# Create data directory for backups
mkdir -p data uploads
echo "[3/4] Directories ready"

# Set up systemd service for auto-start on boot
echo "[4/4] Setting up auto-start..."

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

sudo tee /etc/systemd/system/mathtutor.service > /dev/null << EOF
[Unit]
Description=MathTutor AI Tutor
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$SCRIPT_DIR
EnvironmentFile=$SCRIPT_DIR/.env
ExecStart=/usr/bin/python3 $SCRIPT_DIR/app.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable mathtutor
sudo systemctl start mathtutor

echo ""
echo "═══════════════════════════════════════"
echo "  Done! MathTutor is running."
echo ""
echo "  IMPORTANT: Edit .env to add API keys"
echo "    nano .env"
echo ""
echo "  Then restart:"
echo "    sudo systemctl restart mathtutor"
echo ""
echo "  Logs:"
echo "    journalctl -u mathtutor -f"
echo "═══════════════════════════════════════"
