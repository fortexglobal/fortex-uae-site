#!/bin/bash
# Бот «Хабиби» (ранний доступ). Токен передаётся аргументом и хранится только на сервере.
# curl -s https://raw.githubusercontent.com/fortexglobal/fortex-uae-site/main/tools/radar/install_habibi.sh | bash -s <ТОКЕН_БОТА>
set -e
T="$1"
[ -n "$T" ] || { echo "Нужен токен бота: ... | bash -s <ТОКЕН>"; exit 1; }
R=https://raw.githubusercontent.com/fortexglobal/fortex-uae-site/main/tools/radar
curl -fsSL "$R/habibi.py?$(date +%s)" -o /opt/radar/habibi.py
umask 077; echo "HABIBI_TOKEN=$T" > /opt/radar/habibi.env
chown radar:radar /opt/radar/habibi.py /opt/radar/habibi.env
/opt/radar/venv/bin/python -m py_compile /opt/radar/habibi.py
cat > /etc/systemd/system/habibi.service <<UNIT
[Unit]
Description=Habibi early access bot
After=network-online.target
[Service]
User=radar
WorkingDirectory=/opt/radar
ExecStart=/opt/radar/venv/bin/python /opt/radar/habibi.py
Restart=always
RestartSec=5
[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload && systemctl enable --now habibi && sleep 4 && systemctl is-active habibi && echo HABIBI_OK
curl -s "https://api.telegram.org/bot$T/getMe" | python3 -c "import sys,json;print('Бот: @'+json.load(sys.stdin)['result']['username'])"
