"""Передаёт ассистенту директа Telegram-клиент аккаунта радара (ответы в личке)."""
import sys
p = sys.argv[1] if len(sys.argv) > 1 else '/opt/radar/radar.py'
s = open(p, encoding='utf-8').read()
a = 'igdm.setup(openrouter_key=OPENROUTER_KEY, notify=notify, transcribe=transcribe)'
if 'user=user)' not in s.split('igdm.setup', 1)[-1][:200]:
    assert a in s, 'setup anchor'
    s = s.replace(a, 'igdm.setup(openrouter_key=OPENROUTER_KEY, notify=notify, transcribe=transcribe, user=user)', 1)
open(p, 'w', encoding='utf-8').write(s)
print('OK13')
