#!/bin/bash
# Логика радара: прямое попадание (счета, банки, ВНЖ, визы, Emirates ID, компании в ОАЭ) -> ответ + 👍 любому человеку;
# косвенное (платёжные агенты, переводы, карты, Китай, ВЭД, люди с деньгами) -> только реакция; остальное -> ничего.
# Смайлики в ответах редко (1 из 10, только в шутку).
# curl -s https://raw.githubusercontent.com/fortexglobal/fortex-uae-site/main/tools/radar/update16.sh | bash
set -e
R=https://raw.githubusercontent.com/fortexglobal/fortex-uae-site/main/tools/radar
for f in autoreply.py starters.py; do curl -fsSL "$R/$f?$(date +%s)" -o /opt/radar/$f; done
for f in fix18 fix19 fix20; do curl -fsSL "$R/$f.py?$(date +%s)" -o /tmp/$f.py && python3 /tmp/$f.py; done
chown radar:radar /opt/radar/autoreply.py /opt/radar/starters.py /opt/radar/radar.py
/opt/radar/venv/bin/python -m py_compile /opt/radar/radar.py /opt/radar/autoreply.py /opt/radar/starters.py
systemctl restart radar && sleep 5 && systemctl is-active radar && echo RADAR_UPDATED
