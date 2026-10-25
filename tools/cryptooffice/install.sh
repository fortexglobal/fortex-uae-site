#!/bin/bash
# Ассистент Криптоофиса на отдельном сервере Ubuntu (своя папка, аккаунт и служба).
# curl -fsSL https://raw.githubusercontent.com/fortexglobal/fortex-uae-site/refs/heads/claude/cryptooffice-assistant/tools/cryptooffice/install.sh | bash
set -e
R=${CO_SRC:-https://raw.githubusercontent.com/fortexglobal/fortex-uae-site/refs/heads/claude/cryptooffice-assistant/tools/cryptooffice}
D=/opt/cryptooffice
U=$(id -u radar >/dev/null 2>&1 && echo radar || echo root)
mkdir -p $D
for f in assistant.py kb.md; do curl -fsSL "$R/$f?$(date +%s)" -o $D/$f; done

if [ ! -s $D/co.env ]; then
  echo "Вставь api_id (только цифры) и нажми Enter:"; read -r AID < /dev/tty
  echo "Вставь api_hash (длинная строка) и нажми Enter:"; read -r AH < /dev/tty
  echo "Вставь ключ OpenRouter (начинается с sk-or-) и нажми Enter:"; read -r KEY < /dev/tty
  umask 077
  printf 'API_ID=%s\nAPI_HASH=%s\nOPENROUTER_KEY=%s\n' "$AID" "$AH" "$KEY" > $D/co.env
fi

if [ ! -x $D/venv/bin/python ]; then
  python3 -m venv $D/venv 2>/dev/null || { apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq python3-venv && python3 -m venv $D/venv; }
fi
$D/venv/bin/pip install -q --upgrade telethon httpx qrcode
$D/venv/bin/python -m py_compile $D/assistant.py

systemctl stop cryptooffice 2>/dev/null || true
if ! (cd $D && $D/venv/bin/python -c "
import asyncio, assistant
async def ok():
    await assistant.client.connect()
    r = await assistant.client.is_user_authorized()
    await assistant.client.disconnect()
    return r
raise SystemExit(0 if asyncio.get_event_loop().run_until_complete(ok()) else 1)" 2>/dev/null); then
  rm -f $D/co.session
  echo
  echo "Сейчас вход в Telegram по QR-коду. Если на аккаунте стоит облачный пароль, программа спросит и его."
  cd $D && $D/venv/bin/python assistant.py --qr < /dev/tty
fi
chown -R $U:$U $D

cat > /etc/systemd/system/cryptooffice.service <<UNIT
[Unit]
Description=Cryptooffice Telegram assistant
After=network-online.target
[Service]
User=$U
WorkingDirectory=$D
ExecStart=$D/venv/bin/python $D/assistant.py
Restart=always
RestartSec=10
[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload && systemctl enable --now cryptooffice && systemctl restart cryptooffice && sleep 5 && systemctl is-active cryptooffice && echo CRYPTOOFFICE_OK
