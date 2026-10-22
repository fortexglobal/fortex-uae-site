#!/bin/bash
# ManyChat для директа Instagram: curl -s https://raw.githubusercontent.com/fortexglobal/fortex-uae-site/main/tools/radar/install10.sh | bash
set -e
R=https://raw.githubusercontent.com/fortexglobal/fortex-uae-site/main/tools/radar
HOST=$(curl -s https://api.ipify.org | tr . -).sslip.io
# 1. код ассистента
curl -fsSL "$R/igdm.py?$(date +%s)" -o /opt/radar/igdm.py
curl -fsSL "$R/kb.md?$(date +%s)" -o /opt/radar/kb.md
# 2. секрет адреса и ключ ManyChat
[ -s /opt/radar/mc_secret ] || openssl rand -hex 16 > /opt/radar/mc_secret
if [ ! -s /opt/radar/manychat_key ]; then
  read -rp "Вставь API-ключ ManyChat (Enter, чтобы пропустить): " K < /dev/tty
  [ -n "$K" ] && printf '%s' "$K" | tr -d ' \r\n' > /opt/radar/manychat_key
  clear
fi
chown radar:radar /opt/radar/igdm.py /opt/radar/kb.md /opt/radar/mc_secret /opt/radar/manychat_key 2>/dev/null || true
chmod 600 /opt/radar/mc_secret /opt/radar/manychat_key 2>/dev/null || true
# 3. HTTPS через Caddy (сертификат выпускается сам)
if ! command -v caddy >/dev/null; then
  apt-get update -qq && (apt-get install -y -qq caddy || {
    apt-get install -y -qq debian-keyring debian-archive-keyring apt-transport-https gnupg
    curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/gpg.key | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
    curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt > /etc/apt/sources.list.d/caddy-stable.list
    apt-get update -qq && apt-get install -y -qq caddy; })
fi
printf '%s {\n  reverse_proxy 127.0.0.1:8088\n}\n' "$HOST" > /etc/caddy/Caddyfile
command -v ufw >/dev/null && ufw status | grep -q active && ufw allow 80,443/tcp >/dev/null || true
systemctl enable --now caddy >/dev/null 2>&1; systemctl reload caddy || systemctl restart caddy
/opt/radar/venv/bin/python -m py_compile /opt/radar/igdm.py
systemctl restart radar && sleep 6
echo "Проверка: $(curl -s --max-time 20 https://$HOST/health)"
echo
echo "Адрес для ManyChat (External Request, POST):"
echo "https://$HOST/mc/$(cat /opt/radar/mc_secret)"
echo CMD11_OK
