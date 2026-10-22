#!/bin/bash
# Автореакции радара: curl -s https://raw.githubusercontent.com/fortexglobal/fortex-uae-site/main/tools/radar/install8.sh | bash
set -e
R=https://raw.githubusercontent.com/fortexglobal/fortex-uae-site/main/tools/radar
curl -fsSL "$R/reactions.py?$(date +%s)" -o /opt/radar/reactions.py
curl -fsSL "$R/fix8.py?$(date +%s)" -o /tmp/fix8.py
curl -fsSL "$R/fix9.py?$(date +%s)" -o /tmp/fix9.py
curl -fsSL "$R/fix10.py?$(date +%s)" -o /tmp/fix10.py
curl -fsSL "$R/fix11.py?$(date +%s)" -o /tmp/fix11.py
curl -fsSL "$R/autoreply.py?$(date +%s)" -o /opt/radar/autoreply.py
cp /opt/radar/radar.py /opt/radar/radar.bak8
python3 /tmp/fix8.py
python3 /tmp/fix9.py
python3 /tmp/fix10.py
python3 /tmp/fix11.py
chown radar:radar /opt/radar/reactions.py /opt/radar/autoreply.py
/opt/radar/venv/bin/python -m py_compile /opt/radar/radar.py /opt/radar/reactions.py /opt/radar/autoreply.py
systemctl restart radar && sleep 4 && systemctl is-active radar && echo CMD9_OK
