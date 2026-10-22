import sys, re
p = sys.argv[1] if len(sys.argv) > 1 else '/opt/radar/radar.py'
s = open(p, encoding='utf-8').read()

if 'import autoreply' not in s:
    s = s.replace('\nimport reactions\n', '\nimport reactions\nimport autoreply\n', 1)

# 1. новые правила ответа
a = s.index('Правила ответа (reply):')
b = s.index('"""', a)
new_rules = '''Правила ответа (reply): пиши как живой человек в чате, который в теме, но без пафоса («я не главный эксперт, просто кое-что знаю»). Короткие предложения по 3–6 слов, каждое заканчивается точкой (или вопросом). Всего 1–3 предложения. Ответ НИКОГДА не длиннее сообщения, на которое отвечаем; иногда одно предложение и «:)». Можно многоточие. Иногда одно вопросительное предложение, чтобы втянуть в диалог. Иногда лёгкая ирония, в том числе про скамеров и мутных посредников в таких чатах (мы на стороне добра). Никогда не пиши «по опыту». Без канцелярита, без эмодзи-картинок (только «:)»), без длинных тире, без ссылок, без контактов, без «пишите в личку» и без цен (в крайнем случае «от X» по ориентирам выше). Можно спокойно и уверенно говорить, что в ОАЭ это решаемо: счета с российским паспортом, с Emirates ID и без, компании, криптосчета, сложные виды деятельности. Не обещай 100% и конкретный банк. Не советуй ничего скрывать от банка, только законные пути (компания и счёт в ОАЭ, зарплата себе через рабочую визу). Никогда не спорь, всегда на позитиве. Не упоминай Fortex. Примеры: «С русским паспортом открывают. Но не везде. Компания уже есть?» / «В Дубае с этим проще. Главное источник средств :)»'''
s = s[:a] + new_rules + s[b:]

# 2. ответы на наши сообщения: реакция за согласие + продолжение ветки
old = '''        if ev.is_reply and AGREE_RE.search(text):
            try:
                rm = await ev.get_reply_message()
                if rm and rm.out:
                    asyncio.get_event_loop().create_task(reactions.maybe_react(user, ev.chat_id, ev.id, ev.sender_id, text, "👍"))
            except Exception as e:
                log.warning("agree check: %s", e)'''
new = '''        if ev.is_reply:
            try:
                rm = await ev.get_reply_message()
                if rm and rm.out:
                    if AGREE_RE.search(text):
                        asyncio.get_event_loop().create_task(reactions.maybe_react(user, ev.chat_id, ev.id, ev.sender_id, text, "👍"))
                    asyncio.get_event_loop().create_task(autoreply.on_reply_to_us(user, ev, rm, text))
                    return
            except Exception as e:
                log.warning("reply check: %s", e)'''
if 'autoreply.on_reply_to_us' not in s:
    assert old in s, 'reply anchor'
    s = s.replace(old, new, 1)

# 3. автоответ на новый лид
c = '''            [Button.inline("❌ Пропустить", f"skip:{lid}".encode())],
        ])
'''
if 'autoreply.maybe_auto_reply' not in s:
    assert c in s, 'card anchor'
    s = s.replace(c, c + '''        asyncio.get_event_loop().create_task(autoreply.maybe_auto_reply(user, ev, sender, text, res, lid, db))
''', 1)

# 4. кнопка «Удалить» под уведомлением об автоответе
d = '''    if ev.data.startswith(b"c"):
        return await content.on_button(ev)
'''
if b'adel:' not in s.encode():
    assert d in s, 'button anchor'
    s = s.replace(d, d + '''    if ev.data.startswith(b"adel:"):
        _, ch, mid = ev.data.decode().split(":")
        res = await autoreply.delete_message(user, int(ch), int(mid))
        return await ev.answer(res)
''', 1)

# 5. команда /auto
e = '''@bot.on(events.NewMessage(pattern=r"^/reactions"))'''
if '"^/auto"' not in s:
    assert e in s, 'cmd anchor'
    s = s.replace(e, '''@bot.on(events.NewMessage(pattern=r"^/auto"))
async def cmd_auto(ev):
    if not is_owner(await ev.get_sender()):
        return
    arg = (ev.raw_text.split() + [""])[1].lower()
    if arg in ("on", "вкл"):
        autoreply.set_on(True)
    elif arg in ("off", "выкл"):
        autoreply.set_on(False)
    await ev.reply(autoreply.status() + "\\nВключить: /auto on, выключить: /auto off")


''' + e, 1)
    s = s.replace('/reactions — автореакции (on/off)")', '/reactions — автореакции (on/off)\\n/auto — автоответы в чатах (on/off)")', 1)

# 6. настройка модуля
f = '''    content.setup(bot_token=BOT_TOKEN'''
if 'autoreply.setup' not in s:
    assert f in s, 'setup anchor'
    s = s.replace(f, '''    autoreply.setup(openrouter_key=OPENROUTER_KEY, notify=notify,
                    buttons=lambda c, m: [[Button.inline("🗑 Удалить", f"adel:{c}:{m}".encode())]])
''' + f, 1)
open(p, 'w', encoding='utf-8').write(s)
print('OK11')
