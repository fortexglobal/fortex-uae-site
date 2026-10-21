import sys
p = sys.argv[1] if len(sys.argv) > 1 else '/opt/radar/radar.py'
s = open(p, encoding='utf-8').read()
if 'import content' not in s:
    s = s.replace('\nBASE = ', '\nimport content\nBASE = ', 1)
a = '''    action, lid = ev.data.decode().split(":")'''
if 'content.on_button' not in s:
    assert a in s, 'button anchor'
    s = s.replace(a, '''    if ev.data.startswith(b"c"):
        return await content.on_button(ev)
''' + a, 1)
b = '''    # edited reply
    lid = state["edit"].pop(s.id, None)'''
if 'content.maybe_handle' not in s:
    assert b in s, 'text anchor'
    s = s.replace(b, '''    if await content.maybe_handle(ev, text):
        return
''' + b, 1)
c = '''    await bot.start(bot_token=BOT_TOKEN)
'''
if 'content.setup' not in s:
    assert c in s, 'main anchor'
    s = s.replace(c, c + '''    content.setup(bot_token=BOT_TOKEN, openrouter_key=OPENROUTER_KEY, owner_id=owner_id,
                  kv_get=kv_get, kv_set=kv_set, transcribe=transcribe)
    asyncio.get_event_loop().create_task(content.scheduler())
''', 1)
open(p, 'w', encoding='utf-8').write(s)
print('OK7')
