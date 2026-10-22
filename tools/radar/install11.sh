#!/bin/bash
# Ассистент в личке аккаунта радара: curl -s https://raw.githubusercontent.com/fortexglobal/fortex-uae-site/main/tools/radar/install11.sh | bash
set -e
R=https://raw.githubusercontent.com/fortexglobal/fortex-uae-site/main/tools/radar
curl -fsSL "$R/igdm.py?$(date +%s)" -o /opt/radar/igdm.py
curl -fsSL "$R/kb.md?$(date +%s)" -o /opt/radar/kb.md
curl -fsSL "$R/fix13.py?$(date +%s)" -o /tmp/fix13.py
cp /opt/radar/radar.py /opt/radar/radar.bak11
python3 /tmp/fix13.py
chown radar:radar /opt/radar/igdm.py /opt/radar/kb.md
/opt/radar/venv/bin/python -m py_compile /opt/radar/radar.py /opt/radar/igdm.py
systemctl restart radar && sleep 4 && systemctl is-active radar && echo CMD12_OK
