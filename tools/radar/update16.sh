#!/bin/bash
# Смайлики в ответах в чатах: редко (примерно 1 из 10) и только в шутку
# curl -s https://raw.githubusercontent.com/fortexglobal/fortex-uae-site/main/tools/radar/update16.sh | bash
set -e
R=https://raw.githubusercontent.com/fortexglobal/fortex-uae-site/main/tools/radar
for f in autoreply.py starters.py; do curl -fsSL "$R/$f?$(date +%s)" -o /opt/radar/$f; done
curl -fsSL "$R/fix18.py?$(date +%s)" -o /tmp/fix18.py && python3 /tmp/fix18.py
chown radar:radar /opt/radar/autoreply.py /opt/radar/starters.py /opt/radar/radar.py
/opt/radar/venv/bin/python -m py_compile /opt/radar/radar.py /opt/radar/autoreply.py /opt/radar/starters.py
systemctl restart radar && sleep 5 && systemctl is-active radar && echo RADAR_UPDATED
