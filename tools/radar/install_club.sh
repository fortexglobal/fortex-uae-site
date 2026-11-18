#!/bin/bash
# Бот клуба. Токен и название передаются аргументами и хранятся только на сервере.
# curl -s https://raw.githubusercontent.com/fortexglobal/fortex-uae-site/main/tools/radar/install_club.sh | bash -s <ТОКЕН_БОТА> "<Название клуба>"
set -e
T="$1"; N="${2:-DXB Club}"
[ -n "$T" ] || { echo "Нужен токен бота: ... | bash -s <ТОКЕН> \"Название\""; exit 1; }
R=https://raw.githubusercontent.com/fortexglobal/fortex-uae-site/main/tools/radar
curl -fsSL "$R/club.py?$(date +%s)" -o /opt/radar/club.py
umask 077; printf 'CLUB_TOKEN=%s\nCLUB_NAME=%s\n' "$T" "$N" > /opt/radar/club.env
chown radar:radar /opt/radar/club.py /opt/radar/club.env
/opt/radar/venv/bin/python -m py_compile /opt/radar/club.py
cat > /etc/systemd/system/club.service <<UNIT
[Unit]
Description=Club bot
After=network-online.target
[Service]
User=radar
WorkingDirectory=/opt/radar
ExecStart=/opt/radar/venv/bin/python /opt/radar/club.py
Restart=always
RestartSec=5
[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload && systemctl enable --now club && sleep 4 && systemctl is-active club && echo CLUB_OK
curl -s "https://api.telegram.org/bot$T/getMe" | python3 -c "import sys,json;print('Бот: @'+json.load(sys.stdin)['result']['username'])"
