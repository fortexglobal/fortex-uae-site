#!/bin/bash
# Смотритель Fortex: публикации минута в минуту, ответы в Threads каждые 5 минут, балансы, работоспособность.
# curl -s https://raw.githubusercontent.com/fortexglobal/fortex-uae-site/main/tools/radar/keeper.sh | bash
set -e
R=https://raw.githubusercontent.com/fortexglobal/fortex-uae-site/main/tools/radar
mkdir -p /opt/keeper && chmod 700 /opt/keeper
curl -fsSL "$R/keeper.py?$(date +%s)" -o /opt/keeper/keeper.py
command -v git >/dev/null || apt-get install -y -q git >/dev/null

# Ключи берём с этого же сервера: из файлов радара или из окружения работающего радара
python3 - <<'PY'
import os, re, glob, subprocess
found = {}
def take(name, val):
    if val and name not in found:
        found[name] = val.strip().strip('"\'')
texts = []
for f in ["/opt/radar/radar.py"] + glob.glob("/opt/radar/*.env") + ["/etc/systemd/system/radar.service"]:
    try: texts.append(open(f).read())
    except Exception: pass
try:
    pid = subprocess.run(["systemctl", "show", "-p", "MainPID", "--value", "radar"], capture_output=True, text=True).stdout.strip()
    texts.append(open(f"/proc/{pid}/environ").read().replace("\0", "\n"))
except Exception: pass
blob = "\n".join(texts)
for m in re.finditer(r"\b\d{8,11}:[A-Za-z0-9_-]{30,}\b", blob):
    ctx = blob[max(0, m.start() - 60):m.start()]
    if "LEAD" not in ctx:
        take("BOT_TOKEN", m.group(0)); break
m = re.search(r"sk-or-v1-[A-Za-z0-9]{20,}", blob)
take("OPENROUTER_KEY", m.group(0) if m else "")
old = {}
if os.path.exists("/opt/keeper/keeper.env"):
    for l in open("/opt/keeper/keeper.env"):
        if "=" in l: k, v = l.strip().split("=", 1); old[k] = v
old.update({k: v for k, v in found.items() if k not in old})
old.setdefault("OWNER_ID", "5887750248"); old.setdefault("LOW_BALANCE", "5")
os.umask(0o077)
open("/opt/keeper/keeper.env", "w").write("".join(f"{k}={v}\n" for k, v in old.items()))
print("Ключ бота:", "найден" if old.get("BOT_TOKEN") else "НЕ найден", "| OpenRouter:", "найден" if old.get("OPENROUTER_KEY") else "НЕ найден")
PY

if ! grep -q '^BOT_TOKEN=' /opt/keeper/keeper.env; then
  echo "Вставь токен бота, который пишет тебе уведомления радара, и нажми Enter:"; read -r T < /dev/tty
  echo "BOT_TOKEN=$T" >> /opt/keeper/keeper.env
fi
if ! grep -q '^APIFY_TOKEN=' /opt/keeper/keeper.env; then
  echo "Токен Apify для контроля баланса (console.apify.com → Settings → API & Integrations). Можно пропустить: просто Enter."
  read -r A < /dev/tty || true
  [ -n "$A" ] && echo "APIFY_TOKEN=$A" >> /opt/keeper/keeper.env
fi

# Проверка: умеет ли токен GitHub запускать публикации
code=$(curl -s -o /dev/null -w '%{http_code}' -X POST -H "Authorization: Bearer $(cat /opt/radar/github_token)" \
  -H "Accept: application/vnd.github+json" https://api.github.com/repos/fortexglobal/fortex-uae-site/actions/workflows/threads-fast.yml/dispatches -d '{"ref":"main"}')
if [ "$code" != "204" ]; then
  echo "GitHub: токен не может запускать публикации (код $code)."
  echo "Открой github.com/settings/personal-access-tokens, выбери токен сервера, в Repository permissions поставь Actions: Read and write, сохрани."
  echo "Или вставь сюда новый токен (github_pat_...) с правами Contents и Actions: Read and write. Enter, чтобы оставить старый:"
  read -r G < /dev/tty || true
  [ -n "$G" ] && { echo "$G" > /opt/radar/github_token; chown radar:radar /opt/radar/github_token; chmod 600 /opt/radar/github_token; }
else
  echo "GitHub: запуск публикаций работает"
fi

python3 -m py_compile /opt/keeper/keeper.py
cat > /etc/systemd/system/keeper.service <<UNIT
[Unit]
Description=Fortex keeper (publications, Threads replies, balances, health)
After=network-online.target
[Service]
WorkingDirectory=/opt/keeper
ExecStart=/usr/bin/python3 -u /opt/keeper/keeper.py
Restart=always
RestartSec=20
[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload && systemctl enable -q keeper && systemctl restart keeper && sleep 8
systemctl is-active keeper && echo KEEPER_OK
journalctl -u keeper -n 5 --no-pager
