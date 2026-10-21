#!/bin/bash
# Установка модуля контента в радар: curl -s https://raw.githubusercontent.com/fortexglobal/fortex-uae-site/main/tools/radar/install.sh | bash
set -e
R=https://raw.githubusercontent.com/fortexglobal/fortex-uae-site/main/tools/radar
if [ ! -s /opt/radar/github_token ]; then
  echo "Вставь токен GitHub (начинается с github_pat_) и нажми Enter:"
  read -r T < /dev/tty
  echo "$T" > /opt/radar/github_token && chmod 600 /opt/radar/github_token
fi
curl -fsSL "$R/content.py?$(date +%s)" -o /opt/radar/content.py
curl -fsSL "$R/fix7.py?$(date +%s)" -o /tmp/fix7.py
cp /opt/radar/radar.py /opt/radar/radar.bak7
python3 /tmp/fix7.py
/opt/radar/venv/bin/python -m py_compile /opt/radar/radar.py /opt/radar/content.py
code=$(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $(cat /opt/radar/github_token)" https://api.github.com/repos/fortexglobal/fortex-uae-site/contents/posts)
echo "GitHub: $code"
systemctl restart radar && sleep 4 && systemctl is-active radar && echo CMD8_OK
