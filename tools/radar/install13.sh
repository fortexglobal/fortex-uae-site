#!/bin/bash
# Обновление: всё из install12 + реакции ресурсным людям вне нашей темы
# curl -s https://raw.githubusercontent.com/fortexglobal/fortex-uae-site/main/tools/radar/install13.sh | bash
set -e
R=https://raw.githubusercontent.com/fortexglobal/fortex-uae-site/main/tools/radar
for f in igdm.py autoreply.py starters.py newsfeed.py content.py reactions.py kb.md; do curl -fsSL "$R/$f?$(date +%s)" -o /opt/radar/$f; done
for f in fix13.py fix14.py fix15.py fix16.py fix17.py; do curl -fsSL "$R/$f?$(date +%s)" -o /tmp/$f; done
cp /opt/radar/radar.py /opt/radar/radar.bak13
for f in fix13 fix14 fix15 fix16 fix17; do python3 /tmp/$f.py; done
chown radar:radar /opt/radar/*.py /opt/radar/kb.md
/opt/radar/venv/bin/python -m py_compile /opt/radar/radar.py /opt/radar/igdm.py /opt/radar/autoreply.py /opt/radar/starters.py /opt/radar/newsfeed.py /opt/radar/content.py /opt/radar/reactions.py
systemctl restart radar && sleep 5 && systemctl is-active radar && echo CMD14_OK
