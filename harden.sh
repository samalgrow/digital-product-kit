#!/usr/bin/env bash
# Locks down a fresh Ubuntu/Debian server. Run once, before install.sh:  sudo ./harden.sh
#
#   - installs security updates and turns on automatic ones
#   - firewall: only SSH, HTTP and HTTPS in, everything else blocked
#   - fail2ban: bans an IP for an hour after 5 failed logins
#   - SSH: no root login, no passwords (keys only)
#
# Only for a server you use for this shop. It changes system-wide settings.
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Run it with sudo:  sudo ./harden.sh"
  exit 1
fi
USER_NAME="${SUDO_USER:-}"
if [ -z "$USER_NAME" ] || [ "$USER_NAME" = root ]; then
  echo "Run it as your normal user with sudo (not as root), so it knows who you are."
  exit 1
fi

KEYS="/home/$USER_NAME/.ssh/authorized_keys"
if [ ! -s "$KEYS" ]; then
  cat <<MSG

After this, logging in over SSH with a password stops working.
You don't have an SSH key set up for $USER_NAME, so you'll log in through your
server provider's web console instead (DigitalOcean: open the Droplet and click
Console, then log in as $USER_NAME). That's the safest setup if you're not sure what
an SSH key is.

MSG
  read -r -p "Continue? [y/N] " answer
  case "$answer" in y|Y|yes) ;; *) echo "Stopped. Nothing was changed."; exit 1 ;; esac
fi

echo "Installing security updates (can take a few minutes)..."
export DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=a
apt-get update -qq >/dev/null
apt-get -y -qq upgrade >/dev/null 2>&1
apt-get -y -qq install ufw fail2ban unattended-upgrades >/dev/null 2>&1

echo "Turning on automatic security updates..."
cat > /etc/apt/apt.conf.d/20auto-upgrades <<'CONF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
CONF

echo "Firewall: allowing only SSH, HTTP and HTTPS..."
ufw default deny incoming >/dev/null
ufw default allow outgoing >/dev/null
ufw allow OpenSSH >/dev/null
ufw allow 80/tcp >/dev/null
ufw allow 443/tcp >/dev/null
ufw --force enable >/dev/null

echo "fail2ban: banning IPs that keep guessing logins..."
cat > /etc/fail2ban/jail.d/digital-product-kit.conf <<'CONF'
[sshd]
enabled = true
maxretry = 5
findtime = 10m
bantime = 1h
CONF
systemctl enable --now fail2ban >/dev/null 2>&1
systemctl restart fail2ban

echo "SSH: no root login, no passwords..."
# 00- so it wins over the cloud image's own files, which often turn passwords on.
cat > /etc/ssh/sshd_config.d/00-digital-product-kit.conf <<'CONF'
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
MaxAuthTries 3
X11Forwarding no
CONF
sshd -t
systemctl reload ssh 2>/dev/null || systemctl reload sshd

echo
echo "Done. Firewall on, fail2ban on, automatic updates on, SSH locked to keys only."
echo "Next: ./install.sh"
