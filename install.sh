#!/usr/bin/env bash
# One-time setup on a fresh Ubuntu/Debian server. Run as your normal user (it uses sudo).
set -euo pipefail
cd "$(dirname "$0")"

if [ "$(id -u)" -eq 0 ]; then
  cat <<'MSG'
Please don't run this as root. The shop's web service should not have full
control of your server. Make a normal user once, then run it as that user:

  adduser shop                 # pick a password, press Enter for the rest
  usermod -aG sudo shop
  su - shop
  git clone https://github.com/samalgrow/digital-product-kit.git
  cd digital-product-kit && ./install.sh
MSG
  exit 1
fi
DIR="$(pwd)"

echo "Installing nginx, certbot and Python..."
sudo apt-get update -qq >/dev/null
sudo DEBIAN_FRONTEND=noninteractive NEEDRESTART_SUSPEND=1 apt-get install -y -qq nginx certbot python3-venv sqlite3 >/dev/null 2>&1

echo "Installing the web service..."
python3 -m venv .venv
.venv/bin/pip install -q -r requirements.txt

if [ ! -f .env ]; then
  read -r -p "Email for customer replies (a real inbox you check): " SUPPORT_EMAIL
  sed "s|^SUPPORT_EMAIL=.*|SUPPORT_EMAIL=$SUPPORT_EMAIL|" .env.example > .env
  chmod 600 .env
fi
mkdir -p -m 700 data
PORT="$(grep -E '^PORT=' .env | cut -d= -f2 || true)"
PORT="${PORT:-8750}"

sudo tee /etc/systemd/system/digital-product-kit.service >/dev/null <<UNIT
[Unit]
Description=Digital Product Kit (order emails + downloads)
After=network.target

[Service]
User=$USER
WorkingDirectory=$DIR
ExecStart=$DIR/.venv/bin/gunicorn -w 2 -b 127.0.0.1:$PORT kit.server:app
Restart=always
NoNewPrivileges=true
PrivateTmp=true
PrivateDevices=true
ProtectSystem=full
ProtectHome=read-only
ReadWritePaths=$DIR/data
ProtectKernelTunables=true
ProtectControlGroups=true
RestrictSUIDSGID=true
LockPersonality=true

[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload
sudo systemctl enable --now digital-product-kit >/dev/null 2>&1
sudo systemctl restart digital-product-kit

sleep 1
curl -fsS "http://127.0.0.1:$PORT/health" >/dev/null && echo "Service running on port $PORT."
echo "Next: ./new_product.py --help (it asks for your keys and never saves them)"
