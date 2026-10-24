import sys
p = sys.argv[1] if len(sys.argv) > 1 else '/opt/radar/radar.py'
s = open(p, encoding='utf-8').read()

# 1. проверка «ресурсности» на каждое сообщение в группах (сама отсеивает дёшево)
a = '''        if len(text) < 20:'''
if 'reactions.wealth_scan' not in s:
    assert a in s, 'len anchor'
    s = s.replace(a, '''        asyncio.get_event_loop().create_task(reactions.wealth_scan(user, ev, text))
''' + a, 1)

# 2. ключ нейросети для модуля реакций
b = '''    autoreply.setup(openrouter_key=OPENROUTER_KEY'''
if 'reactions.setup' not in s:
    assert b in s, 'setup anchor'
    s = s.replace(b, '''    reactions.setup(openrouter_key=OPENROUTER_KEY)
''' + b, 1)
open(p, 'w', encoding='utf-8').write(s)
print('OK17')
