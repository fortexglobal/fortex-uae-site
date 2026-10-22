#!/bin/bash
# Директ Instagram: curl -s https://raw.githubusercontent.com/fortexglobal/fortex-uae-site/main/tools/radar/install9.sh | bash
set -e
R=https://raw.githubusercontent.com/fortexglobal/fortex-uae-site/main/tools/radar
if [ ! -s /opt/radar/ig_token ]; then
  read -rsp "Вставь токен Instagram и нажми Enter: " T < /dev/tty; echo
  printf '%s' "$T" > /opt/radar/ig_token
fi
curl -fsSL "$R/igdm.py?$(date +%s)" -o /opt/radar/igdm.py
curl -fsSL "$R/kb.md?$(date +%s)" -o /opt/radar/kb.md
curl -fsSL "$R/content.py?$(date +%s)" -o /opt/radar/content.py
curl -fsSL "$R/fix12.py?$(date +%s)" -o /tmp/fix12.py
cp /opt/radar/radar.py /opt/radar/radar.bak9
python3 /tmp/fix12.py
chown radar:radar /opt/radar/igdm.py /opt/radar/kb.md /opt/radar/content.py /opt/radar/ig_token
chmod 600 /opt/radar/ig_token
/opt/radar/venv/bin/python -m py_compile /opt/radar/radar.py /opt/radar/igdm.py /opt/radar/content.py
echo "Токен: $(curl -s "https://graph.instagram.com/v21.0/me?fields=username&access_token=$(cat /opt/radar/ig_token)")"
systemctl restart radar && sleep 4 && systemctl is-active radar && echo CMD10_OK
