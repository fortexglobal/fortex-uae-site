"""Подключает igdm.py (директ Instagram) к радару."""
import sys
p = sys.argv[1] if len(sys.argv) > 1 else '/opt/radar/radar.py'
s = open(p, encoding='utf-8').read()
if 'import igdm' not in s:
    s = s.replace('\nimport content\n', '\nimport content\nimport igdm\n', 1)
    assert 'import igdm' in s, 'import anchor'
a = '''    if await content.maybe_handle(ev, text):'''
if 'igdm.maybe_handle' not in s:
    assert a in s, 'text anchor'
    s = s.replace(a, '''    if await igdm.maybe_handle(ev, text):
        return
''' + a, 1)
b = '''    content.setup(bot_token=BOT_TOKEN'''
if 'igdm.setup' not in s:
    assert b in s, 'setup anchor'
    s = s.replace(b, '''    igdm.setup(openrouter_key=OPENROUTER_KEY, notify=notify, transcribe=transcribe)
    asyncio.get_event_loop().create_task(igdm.loop())
''' + b, 1)
c = '''async def main():'''
if 'pattern=r"^/igdm"' not in s:
    assert c in s, 'main anchor'
    s = s.replace(c, '''@bot.on(events.NewMessage(pattern=r"^/igdm"))
async def cmd_igdm(ev):
    if is_owner(await ev.get_sender()):
        await igdm.command(ev)


''' + c, 1)
open(p, 'w', encoding='utf-8').write(s)
print('OK12')
