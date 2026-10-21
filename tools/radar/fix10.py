import sys
p = sys.argv[1] if len(sys.argv) > 1 else '/opt/radar/radar.py'
s = open(p, encoding='utf-8').read()

# 1. поле reaction в ответе нейросети
a = '"tier": "бизнес|состоятельный частный|мелкий|непонятно", '
if '"reaction":' not in s:
    assert a in s, 'tier field anchor'
    s = s.replace(a, a + '"reaction": "👍|🔥|💯|😁 или пусто", ', 1)
    rules = '''РЕАКЦИЯ (поле reaction): ставим только людям с деньгами и бизнесом (tier бизнес или состоятельный частный) в разговоре по нашим темам, прямо или косвенно. Иначе пусто.
💯 или 🔥 — человек высказал мысль или факт, который совпадает с нашим опытом и с которым мы согласны и уверены (например: «банки ОАЭ смотрят прежде всего на источник средств», «с рабочей визой счёт открыть проще», «держать всё на одной бирже рискованно»). 💯 для точного экспертного утверждения, 🔥 для сильного кейса, результата или удачного решения.
😁 — человек из нашей аудитории в обсуждении по нашей теме удачно пошутил.
👍 — человек сказал что-то по нашей теме (прямо или косвенно), что мы можем подтвердить, поделился полезным опытом или задал толковый вопрос.
Не ставим реакцию на рекламу, жалобы на мошенников, политику, мелкие личные задачи (дешёвые карты, мелкие переводы) и спорные или неверные утверждения.

Оцени сообщение и ответь строго JSON без пояснений:'''
    s = s.replace('Оцени сообщение и ответь строго JSON без пояснений:', rules, 1)

# 2. реакция по решению нейросети, даже если это не лид
old_r = '''        if res.get("tier") in ("бизнес", "состоятельный частный") and int(res.get("score", 0)) >= 3:
            asyncio.get_event_loop().create_task(reactions.maybe_react(user, ev.chat_id, ev.id, sender.id, text))
'''
if old_r in s:
    s = s.replace(old_r, '', 1)
b = '''        res = await ask_llm(title, text)
'''
if 'res.get("reaction")' not in s:
    assert b in s, 'llm anchor'
    s = s.replace(b, b + '''        if res and res.get("reaction") in reactions.ALLOWED and res.get("tier") in ("бизнес", "состоятельный частный"):
            asyncio.get_event_loop().create_task(reactions.maybe_react(user, ev.chat_id, ev.id, sender.id, text, res["reaction"]))
''', 1)

# 3. 👍 тому, кто согласился с ответом нашего аккаунта
c = '''        text = ev.raw_text or ""
        if len(text) < 20:'''
if 'AGREE_RE' not in s:
    assert c in s, 'text anchor'
    s = s.replace(c, '''        text = ev.raw_text or ""
        if ev.is_reply and AGREE_RE.search(text):
            try:
                rm = await ev.get_reply_message()
                if rm and rm.out:
                    asyncio.get_event_loop().create_task(reactions.maybe_react(user, ev.chat_id, ev.id, ev.sender_id, text, "👍"))
            except Exception as e:
                log.warning("agree check: %s", e)
        if len(text) < 20:''', 1)
    s = s.replace('\nSYSTEM_PROMPT = ', '\nAGREE_RE = re.compile(r"соглас|верно|точно|так и есть|плюсую|поддерживаю|полностью|спасибо|благодар|дельн|по делу|в точку|\\+\\s*1|👍|💯", re.I)\n\nSYSTEM_PROMPT = ', 1)
open(p, 'w', encoding='utf-8').write(s)
print('OK10')
