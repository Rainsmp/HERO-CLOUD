#!/usr/bin/env bash
set -Eeuo pipefail
if [[ $EUID -ne 0 ]]; then echo 'Run as root'; exit 1; fi
SRC="$(cd "$(dirname "$0")/.." && pwd)"
DEST=/opt/hero-cloud
apt-get update
apt-get install -y python3 python3-venv python3-pip snapd curl ca-certificates
[[ -x /snap/bin/lxc ]] || snap install lxd
mkdir -p "$DEST"
cp -a "$SRC/." "$DEST/"
cd "$DEST"
[[ -f .env ]] || cp .env.example .env
python3 -m venv venv
venv/bin/pip install --upgrade pip
venv/bin/pip install -r requirements.txt
chmod 600 .env
cat >/etc/systemd/system/hero-cloud.service <<'UNIT'
[Unit]
Description=HERO CLOUD Discord VPS Bot
After=network-online.target snap.lxd.daemon.service
Wants=network-online.target
[Service]
Type=simple
User=root
WorkingDirectory=/opt/hero-cloud
EnvironmentFile=/opt/hero-cloud/.env
ExecStart=/opt/hero-cloud/venv/bin/python -m bot.bot
Restart=always
RestartSec=5
[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
echo "Installed in $DEST. Configure $DEST/.env, then enable the service."
