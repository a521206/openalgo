#!/bin/bash
###############################################################################
# deploy-scheduler.sh — Safely add the standalone scheduler to an existing
# OpenAlgo production installation.
#
# Usage:
#   sudo bash deploy-scheduler.sh
#
# Safe to re-run: checks existing state before making changes.
###############################################################################
set -euo pipefail

# ── Configuration (auto-detect where possible) ──────────────────────────────
OPENALGO_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="${OPENALGO_DIR}/.venv"
LOG_DIR="${OPENALGO_DIR}/log"

# Detect deployment name from existing service
EXISTING_SERVICE=$(systemctl list-units --type=service --no-legend | grep -oP 'openalgo-[a-z0-9-]+(?=\.service)' | head -1)
if [ -z "$EXISTING_SERVICE" ]; then
    echo "ERROR: No existing openalgo-*.service found. Run install.sh first."
    exit 1
fi

# Extract deployment name (strip 'openalgo-' prefix)
DEPLOY_NAME="${EXISTING_SERVICE#openalgo-}"
SCHEDULER_SERVICE="openalgo-scheduler-${DEPLOY_NAME}"

echo "============================================"
echo "OpenAlgo Scheduler Deployment"
echo "============================================"
echo "OpenAlgo dir:   ${OPENALGO_DIR}"
echo "Existing service: ${EXISTING_SERVICE}"
echo "Scheduler service: ${SCHEDULER_SERVICE}"
echo "============================================"

# ── Pre-flight checks ───────────────────────────────────────────────────────
echo ""
echo "[1/6] Running pre-flight checks..."

# Check we're on the right branch
BRANCH=$(git -C "${OPENALGO_DIR}" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
echo "  Git branch: ${BRANCH}"

# Check required files exist
for f in scheduler.py gunicorn.conf.py; do
    if [ ! -f "${OPENALGO_DIR}/${f}" ]; then
        echo "  ERROR: ${f} not found. Run 'git pull' first."
        exit 1
    fi
    echo "  ✓ ${f} exists"
done

# Check virtual environment
if [ ! -f "${VENV_DIR}/bin/python" ]; then
    echo "  WARNING: .venv not found at ${VENV_DIR}, trying system python"
    VENV_DIR="/usr"
fi
PYTHON="${VENV_DIR}/bin/python"
echo "  ✓ Python: ${PYTHON}"

# Check required Python packages
if ! "${PYTHON}" -c "import apscheduler, psutil, pytz" 2>/dev/null; then
    echo "  ERROR: Missing Python packages. Run:"
    echo "    ${VENV_DIR}/bin/pip install apscheduler psutil pytz"
    exit 1
fi
echo "  ✓ Required packages installed"

# Check existing Flask service
if ! systemctl is-active --quiet "${EXISTING_SERVICE}"; then
    echo "  WARNING: ${EXISTING_SERVICE} is not running"
else
    echo "  ✓ ${EXISTING_SERVICE} is running"
fi

# ── Create required directories ─────────────────────────────────────────────
echo ""
echo "[2/6] Creating directories..."

mkdir -p "${LOG_DIR}/strategies"
mkdir -p "${OPENALGO_DIR}/strategies/scripts"
mkdir -p "${OPENALGO_DIR}/strategies/examples"

# Fix ownership if running as root
if [ "$(id -u)" -eq 0 ]; then
    WEB_USER=$(systemctl show --property=User --value "${EXISTING_SERVICE}" 2>/dev/null || echo "www-data")
    WEB_GROUP=$(systemctl show --property=Group --value "${EXISTING_SERVICE}" 2>/dev/null || echo "${WEB_USER}")
    chown -R "${WEB_USER}:${WEB_GROUP}" "${LOG_DIR}" "${OPENALGO_DIR}/strategies" 2>/dev/null || true
    echo "  Ownership set to ${WEB_USER}:${WEB_GROUP}"
fi

echo "  ✓ Directories ready"

# ── Create scheduler systemd service ────────────────────────────────────────
echo ""
echo "[3/6] Creating scheduler service..."

SERVICE_FILE="/etc/systemd/system/${SCHEDULER_SERVICE}.service"

if [ -f "${SERVICE_FILE}" ]; then
    echo "  Service already exists, backing up..."
    cp "${SERVICE_FILE}" "${SERVICE_FILE}.bak.$(date +%Y%m%d%H%M%S)"
fi

sudo tee "${SERVICE_FILE}" > /dev/null << EOF
[Unit]
Description=OpenAlgo Strategy Scheduler (${DEPLOY_NAME})
After=network.target ${EXISTING_SERVICE}
Wants=${EXISTING_SERVICE}

[Service]
Type=simple
User=$(systemctl show --property=User --value "${EXISTING_SERVICE}" 2>/dev/null || echo "www-data")
Group=$(systemctl show --property=Group --value "${EXISTING_SERVICE}" 2>/dev/null || echo "www-data")
WorkingDirectory=${OPENALGO_DIR}
ExecStart=${PYTHON} ${OPENALGO_DIR}/scheduler.py
Restart=always
RestartSec=10
StandardOutput=append:${LOG_DIR}/scheduler.log
StandardError=append:${LOG_DIR}/scheduler.log
Environment=TZ=Asia/Kolkata

[Install]
WantedBy=multi-user.target
EOF

echo "  ✓ Created ${SERVICE_FILE}"

# ── Update Flask service to use gthread worker ──────────────────────────────
echo ""
echo "[4/6] Updating Flask service to use gthread worker..."

FLASK_SERVICE_FILE="/etc/systemd/system/${EXISTING_SERVICE}.service"

# Check if already using gthread
if grep -q "gthread" "${FLASK_SERVICE_FILE}" 2>/dev/null; then
    echo "  Already using gthread worker, skipping"
else
    # Backup original
    cp "${FLASK_SERVICE_FILE}" "${FLASK_SERVICE_FILE}.bak.$(date +%Y%m%d%H%M%S)"

    # Replace eventlet with gthread and add config
    sudo sed -i \
        -e 's/--worker-class eventlet/--worker-class gthread --threads 2/g' \
        -e 's/app:app$/--config ${OPENALGO_DIR}\/gunicorn.conf.py app:app/g' \
        "${FLASK_SERVICE_FILE}"

    echo "  ✓ Updated ${FLASK_SERVICE_FILE}"
    echo "    - Changed worker class to gthread"
    echo "    - Added gunicorn.conf.py"
fi

# ── Reload systemd and start services ───────────────────────────────────────
echo ""
echo "[5/6] Reloading systemd and starting services..."

sudo systemctl daemon-reload

# Enable and start scheduler
sudo systemctl enable "${SCHEDULER_SERVICE}"
sudo systemctl start "${SCHEDULER_SERVICE}"
echo "  ✓ ${SCHEDULER_SERVICE} started"

# Restart Flask to pick up gthread + config changes
sudo systemctl restart "${EXISTING_SERVICE}"
echo "  ✓ ${EXISTING_SERVICE} restarted"

# Wait for services to stabilize
sleep 3

# ── Verify ──────────────────────────────────────────────────────────────────
echo ""
echo "[6/6] Verifying deployment..."

SCHEDULER_OK=false
FLASK_OK=false

if systemctl is-active --quiet "${SCHEDULER_SERVICE}"; then
    echo "  ✓ ${SCHEDULER_SERVICE} is active"
    SCHEDULER_OK=true
else
    echo "  ✗ ${SCHEDULER_SERVICE} failed to start"
    echo "    Check logs: sudo journalctl -u ${SCHEDULER_SERVICE} --since '1 min ago'"
fi

if systemctl is-active --quiet "${EXISTING_SERVICE}"; then
    echo "  ✓ ${EXISTING_SERVICE} is active"
    FLASK_OK=true
else
    echo "  ✗ ${EXISTING_SERVICE} failed to start"
    echo "    Check logs: sudo journalctl -u ${EXISTING_SERVICE} --since '1 min ago'"
fi

# Check scheduler log for successful init
if [ -f "${LOG_DIR}/scheduler.log" ]; then
    if grep -q "Scheduler starting" "${LOG_DIR}/scheduler.log" 2>/dev/null; then
        echo "  ✓ Scheduler initialized successfully"
    fi
fi

# ── Summary ─────────────────────────────────────────────────────────────────
echo ""
echo "============================================"
if [ "${SCHEDULER_OK}" = true ] && [ "${FLASK_OK}" = true ]; then
    echo "DEPLOYMENT SUCCESSFUL"
else
    echo "DEPLOYMENT COMPLETED WITH WARNINGS — check logs above"
fi
echo "============================================"
echo ""
echo "Useful commands:"
echo "  Scheduler status:  sudo systemctl status ${SCHEDULER_SERVICE}"
echo "  Scheduler logs:    sudo journalctl -u ${SCHEDULER_SERVICE} -f"
echo "  Flask status:      sudo systemctl status ${EXISTING_SERVICE}"
echo "  Strategy status:   curl -s http://localhost:5000/python/status | python -m json.tool"
echo ""
