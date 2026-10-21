import sys
p = sys.argv[1] if len(sys.argv) > 1 else '/opt/radar/radar.py'
s = open(p, encoding='utf-8').read()
if 'import reactions' not in s:
    s = s.replace('\nimport content\n', '\nimport content\nimport reactions\n', 1)
a = '''        lid = cur.lastrowid
'''
if 'reactions.maybe_react' not in s:
    assert a in s, 'lead anchor'
    s = s.replace(a, a + '''        asyncio.get_event_loop().create_task(reactions.maybe_react(user, ev.chat_id, ev.id, sender.id, text))
''', 1)
b = '''@bot.on(events.NewMessage(pattern=r"^/stats"))'''
if '/reactions' not in s:
    assert b in s, 'cmd anchor'
    s = s.replace(b, '''@bot.on(events.NewMessage(pattern=r"^/reactions"))
async def cmd_reactions(ev):
    if not is_owner(await ev.get_sender()):
        return
    arg = (ev.raw_text.split() + [""])[1].lower()
    if arg in ("on", "вкл"):
        reactions.set_on(True)
    elif arg in ("off", "выкл"):
        reactions.set_on(False)
    await ev.reply(reactions.status() + "\\nВключить: /reactions on, выключить: /reactions off")


''' + b, 1)
    s = s.replace('/stats — статистика")', '/stats — статистика\\n/reactions — автореакции (on/off)")', 1)
open(p, 'w', encoding='utf-8').write(s)
print('OK8')
