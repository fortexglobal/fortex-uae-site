#!/bin/bash
# Бот-лид-магнит «Проверка шансов на счёт в ОАЭ». Токен нового бота передаётся аргументом и сохраняется только на сервере.
# curl -s https://raw.githubusercontent.com/fortexglobal/fortex-uae-site/main/tools/radar/install15.sh | bash -s <ТОКЕН_БОТА>
set -e
T="$1"
[ -n "$T" ] || { echo "Нужен токен бота: ... | bash -s <ТОКЕН>"; exit 1; }
R=https://raw.githubusercontent.com/fortexglobal/fortex-uae-site/main/tools/radar
curl -fsSL "$R/leadbot.py?$(date +%s)" -o /opt/radar/leadbot.py
umask 077; echo "LEAD_TOKEN=$T" > /opt/radar/leadbot.env
chown radar:radar /opt/radar/leadbot.py /opt/radar/leadbot.env
/opt/radar/venv/bin/python -m py_compile /opt/radar/leadbot.py
cat > /etc/systemd/system/leadbot.service <<UNIT
[Unit]
Description=Fortex lead magnet bot
After=network-online.target
[Service]
User=radar
WorkingDirectory=/opt/radar
ExecStart=/opt/radar/venv/bin/python /opt/radar/leadbot.py
Restart=always
RestartSec=5
[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload && systemctl enable --now leadbot && sleep 4 && systemctl is-active leadbot && echo LEADBOT_OK
curl -s "https://api.telegram.org/bot$T/getMe" | python3 -c "import sys,json;print('Бот: @'+json.load(sys.stdin)['result']['username'])"
