#!/usr/bin/env bash
set -euo pipefail

echo "========================================="
echo "        HERO CLOUD INSTALLER"
echo "========================================="

if [ "$(id -u)" -ne 0 ]; then
    echo "Please run as root."
    exit 1
fi

export DEBIAN_FRONTEND=noninteractive

echo "[1/8] Updating packages..."
apt-get update -y

echo "[2/8] Installing dependencies..."
apt-get install -y \
    python3 python3-venv python3-pip \
    curl git sqlite3 ca-certificates

echo "[3/8] Checking LXD..."
if ! command -v /snap/bin/lxc >/dev/null 2>&1; then
    snap install lxd
fi

echo "[4/8] Creating Python virtual environment..."
if [ ! -d venv ]; then
    python3 -m venv venv
fi

echo "[5/8] Installing Python packages..."
source venv/bin/activate
pip install --upgrade pip
if [ -f requirements.txt ]; then
    pip install -r requirements.txt
fi

echo "[6/8] Creating .env..."
if [ -f .env.example ] && [ ! -f .env ]; then
    cp .env.example .env
    echo ".env created from .env.example"
fi

echo "[7/8] Creating systemd service..."
cat >/etc/systemd/system/hero-cloud.service <<'SERVICE'
[Unit]
Description=HERO CLOUD Discord VPS Bot
After=network-online.target snap.lxd.daemon.service
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=$(pwd)
ExecStart=$(pwd)/venv/bin/python -u -m bot.bot
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SERVICE

sed -i "s#\$(pwd)#$(pwd)#g" /etc/systemd/system/hero-cloud.service

echo "[8/8] Enabling service..."
systemctl daemon-reload
systemctl enable hero-cloud

echo
echo "========================================="
echo "      HERO CLOUD INSTALLED"
echo "========================================="
echo "Service: hero-cloud"
echo "Start: systemctl start hero-cloud"
echo "Status: systemctl status hero-cloud"
echo
echo ".env.example was kept."
echo ".env was created only if it did not exist."
