#!/bin/bash
# Обновление ассистента и автоответов: curl -s https://raw.githubusercontent.com/fortexglobal/fortex-uae-site/main/tools/radar/install12.sh | bash
set -e
R=https://raw.githubusercontent.com/fortexglobal/fortex-uae-site/main/tools/radar
for f in igdm.py autoreply.py kb.md; do curl -fsSL "$R/$f?$(date +%s)" -o /opt/radar/$f; done
curl -fsSL "$R/fix14.py?$(date +%s)" -o /tmp/fix14.py && python3 /tmp/fix14.py
chown radar:radar /opt/radar/igdm.py /opt/radar/autoreply.py /opt/radar/kb.md
/opt/radar/venv/bin/python -m py_compile /opt/radar/radar.py /opt/radar/igdm.py /opt/radar/autoreply.py
systemctl restart radar && sleep 4 && systemctl is-active radar && echo CMD13_OK
