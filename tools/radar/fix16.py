"""Подключает newsfeed.py (новости из каналов для рилсов) к радару."""
import sys
p = sys.argv[1] if len(sys.argv) > 1 else '/opt/radar/radar.py'
s = open(p, encoding='utf-8').read()
if 'import newsfeed' not in s:
    s = s.replace('\nimport starters\n', '\nimport starters\nimport newsfeed\n', 1)
    assert 'import newsfeed' in s, 'import anchor'
a = '    asyncio.get_event_loop().create_task(starters.loop())\n'
if 'newsfeed.setup' not in s:
    assert a in s, 'loop anchor'
    s = s.replace(a, a + '''    newsfeed.setup(user=user, notify=notify)
    asyncio.get_event_loop().create_task(newsfeed.loop())
''', 1)
c = '''async def main():'''
if 'pattern=r"^/news"' not in s:
    s = s.replace(c, '''@bot.on(events.NewMessage(pattern=r"^/news"))
async def cmd_news(ev):
    if is_owner(await ev.get_sender()):
        await newsfeed.command(ev)


''' + c, 1)
open(p, 'w', encoding='utf-8').write(s)
print('OK16')
