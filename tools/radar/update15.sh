#!/bin/bash
# Обновление бота-проверки и базы знаний (kb.md) без смены токена
# curl -s https://raw.githubusercontent.com/fortexglobal/fortex-uae-site/main/tools/radar/update15.sh | bash
set -e
curl -fsSL "https://raw.githubusercontent.com/fortexglobal/fortex-uae-site/main/tools/radar/leadbot.py?$(date +%s)" -o /opt/radar/leadbot.py
curl -fsSL "https://raw.githubusercontent.com/fortexglobal/fortex-uae-site/main/tools/radar/kb.md?$(date +%s)" -o /opt/radar/kb.md
chown radar:radar /opt/radar/leadbot.py /opt/radar/kb.md
/opt/radar/venv/bin/python -m py_compile /opt/radar/leadbot.py
systemctl restart leadbot && sleep 3 && systemctl is-active leadbot && echo LEADBOT_UPDATED
