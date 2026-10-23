#!/bin/bash
# Обновление: ассистент в личке, автоответы, свои темы в чатах
# curl -s https://raw.githubusercontent.com/fortexglobal/fortex-uae-site/main/tools/radar/install12.sh | bash
set -e
R=https://raw.githubusercontent.com/fortexglobal/fortex-uae-site/main/tools/radar
for f in igdm.py autoreply.py starters.py content.py kb.md; do curl -fsSL "$R/$f?$(date +%s)" -o /opt/radar/$f; done
for f in fix13.py fix14.py fix15.py; do curl -fsSL "$R/$f?$(date +%s)" -o /tmp/$f; done
cp /opt/radar/radar.py /opt/radar/radar.bak12
python3 /tmp/fix13.py && python3 /tmp/fix14.py && python3 /tmp/fix15.py
chown radar:radar /opt/radar/igdm.py /opt/radar/autoreply.py /opt/radar/starters.py /opt/radar/content.py /opt/radar/kb.md
/opt/radar/venv/bin/python -m py_compile /opt/radar/radar.py /opt/radar/igdm.py /opt/radar/autoreply.py /opt/radar/starters.py /opt/radar/content.py
systemctl restart radar && sleep 5 && systemctl is-active radar && echo CMD13_OK
