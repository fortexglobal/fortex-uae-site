"""Подключает starters.py (свои темы в чатах) к радару."""
import sys
p = sys.argv[1] if len(sys.argv) > 1 else '/opt/radar/radar.py'
s = open(p, encoding='utf-8').read()
if 'import starters' not in s:
    s = s.replace('\nimport igdm\n', '\nimport igdm\nimport starters\n', 1)
    assert 'import starters' in s, 'import anchor'
a = '    asyncio.get_event_loop().create_task(igdm.loop())\n'
if 'starters.setup' not in s:
    assert a in s, 'loop anchor'
    s = s.replace(a, a + '''    starters.setup(user=user, notify=notify, openrouter_key=OPENROUTER_KEY, bot_token=BOT_TOKEN, owner_id=owner_id)
    asyncio.get_event_loop().create_task(starters.loop())
''', 1)
c = '''async def main():'''
if 'pattern=r"^/starters"' not in s:
    assert c in s, 'main anchor'
    s = s.replace(c, '''@bot.on(events.NewMessage(pattern=r"^/starters"))
async def cmd_starters(ev):
    if is_owner(await ev.get_sender()):
        await starters.command(ev)


''' + c, 1)
open(p, 'w', encoding='utf-8').write(s)
print('OK15')
