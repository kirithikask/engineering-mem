#!/usr/bin/env bash
# =============================================================================
# Engineering Memory — Oracle Cloud Always Free provisioning script
#
# Target: Ubuntu 22.04/24.04 on Ampere A1 (ARM, 4 OCPU / 24 GB — Always Free)
# Run as: sudo bash oracle_setup.sh   (from the extracted bundle root)
#
# What it does:
#   1. Installs system packages and Ollama (ARM64 build)
#   2. Pulls the qwen3:4b model (~2.5 GB, one-time, needs internet)
#   3. Creates /opt/engineering-memory with the bundled app
#   4. Installs Python deps into a venv (frontend/dist ships pre-built — no Node)
#   5. Installs a systemd service (auto-start on boot, auto-restart on crash)
#   6. Opens port 8000 in the VM's iptables (Oracle Security List is done in console)
#   7. Health-checks the deployment and prints the public URL
# =============================================================================
set -euo pipefail

APP_DIR="/opt/engineering-memory"
SERVICE_NAME="engineering-memory"
PORT=8000
BUNDLE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ $EUID -ne 0 ]]; then echo "ERROR: run as root: sudo bash $0"; exit 1; fi
echo "=== Engineering Memory: provisioning started $(date) ==="

# --- 1. System packages ------------------------------------------------------
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip curl iptables-persistent > /dev/null

# --- 2. Ollama + model -------------------------------------------------------
if ! command -v ollama >/dev/null 2>&1; then
    echo "--- installing Ollama (ARM64) ..."
    curl -fsSL https://ollama.com/install.sh | sh
fi
systemctl enable --now ollama >/dev/null 2>&1 || true
sleep 3
if ! curl -s -m 5 http://127.0.0.1:11434/api/tags >/dev/null; then
    echo "ERROR: Ollama did not start"; exit 1
fi
if ! curl -s http://127.0.0.1:11434/api/tags | grep -q "qwen3:4b"; then
    echo "--- pulling qwen3:4b (~2.5 GB, one-time, 5-15 min) ..."
    ollama pull qwen3:4b
fi
echo "--- Ollama OK with qwen3:4b"

# --- 3. Application files ----------------------------------------------------
mkdir -p "$APP_DIR"
rsync -a --exclude venv --exclude node_modules --exclude .git "$BUNDLE_DIR"/ "$APP_DIR"/
cd "$APP_DIR"
[[ -f frontend/dist/index.html ]] || { echo "ERROR: frontend/dist missing from bundle"; exit 1; }

# Secrets: generate a strong JWT secret if not already present
if [[ ! -f .env ]]; then
    JWT=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    cat > .env <<EOF
JWT_SECRET=$JWT
OLLAMA_URL=http://localhost:11434/api/generate
OLLAMA_KEEP_ALIVE=-1
EOF
    chmod 600 .env
fi

# --- 4. Python environment ---------------------------------------------------
echo "--- installing Python dependencies (torch et al., 3-8 min) ..."
python3 -m venv venv
venv/bin/pip install --quiet --upgrade pip
venv/bin/pip install --quiet -r backend/requirements.txt

# BGE embedder: pre-download now so the first diagnosis isn't slow (~100 MB)
venv/bin/python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-small-en-v1.5')" \
    && echo "--- BGE model cached" || echo "WARN: BGE pre-download failed (will retry at first boot)"

# --- 5. systemd service -------------------------------------------------------
cat > /etc/systemd/system/${SERVICE_NAME}.service <<EOF
[Unit]
Description=Engineering Memory (FastAPI + UI, single process)
After=network-online.target ollama.service
Wants=ollama.service

[Service]
Type=simple
WorkingDirectory=${APP_DIR}
EnvironmentFile=${APP_DIR}/.env
ExecStart=${APP_DIR}/venv/bin/python -m uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT}
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now ${SERVICE_NAME}

# --- 6. Firewall (VM level; Security List is in the Oracle console) ----------
iptables -I INPUT -p tcp --dport ${PORT} -j ACCEPT || true
netfilter-persistent save >/dev/null 2>&1 || true

# --- 7. Health check ----------------------------------------------------------
PUBLIC_IP=$(curl -s -m 10 https://api.ipify.org || hostname -I | awk '{print $1}')
echo "--- waiting for backend to load models (up to 120 s) ..."
for i in $(seq 1 24); do
    sleep 5
    if curl -s -m 5 http://127.0.0.1:8000/api/health | grep -q '"status"'; then
        echo ""
        echo "============================================================"
        echo "  DEPLOYMENT SUCCESSFUL"
        echo "  App      : http://${PUBLIC_IP}:8000"
        echo "  Health   : http://${PUBLIC_IP}:8000/api/health"
        echo "  Service  : systemctl status ${SERVICE_NAME}"
        echo "  Logs     : journalctl -u ${SERVICE_NAME} -f"
        echo ""
        echo "  If http://${PUBLIC_IP}:8000 is unreachable from your"
        echo "  browser, open port ${PORT} in the instance's Security List"
        echo "  (Oracle Console > Instance > Subnet > Security Lists)."
        echo "============================================================"
        exit 0
    fi
done
echo "ERROR: service did not become healthy — check: journalctl -u ${SERVICE_NAME} -n 50"
exit 1
