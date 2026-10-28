"""Свои темы в чатах: аккаунт радара 5 раз в неделю (будни) начинает обсуждение в одном из чатов.

Как работает:
- пн–пт в случайное время 11:00–18:00 по Дубаю выбираем чат: в нём давно не начинали тем (не чаще раза в 30 дней),
  тематика отличается от двух прошлых (Европа, Азия, ВЭД, крипта, Россия, ОАЭ, релокация...), чат живой;
- читаем последние сообщения (о чём говорят, как длинно пишут) и свежие новости по теме чата (поиск через OpenRouter :online);
- нейросеть пишет вопрос, который интересен участникам и касается наших тем (счета, визы, компании, налоги, переезд, платежи);
- по умолчанию черновик приходит Александру в бот: ✅ Отправить / 🔄 Другой вариант / ❌ Пропустить.
  Режим /starters auto on: отправляем сами;
- ответы людей на наш вопрос ведёт autoreply (до 3 наших сообщений, без продаж, вскользь «мы этим занимаемся», если уместно).
Состояние: /opt/radar/starters.json.
"""
import asyncio, json, logging, os, random, re, time, uuid
from datetime import datetime, timedelta, timezone

import httpx

log = logging.getLogger("starters")
BASE = os.path.dirname(os.path.abspath(__file__))
STATE_F = os.path.join(BASE, "starters.json")
DUBAI = timezone(timedelta(hours=4))
DAYS = (0, 1, 2, 3, 4)      # будни, 5 раз в неделю (в один чат не чаще раза в 30 дней)
HOURS = (11, 18)
CHAT_COOLDOWN = 30 * 86400
CATS = ["Европа", "Азия и Китай", "ВЭД и платежи", "Крипта", "Россия и бизнес", "ОАЭ и Дубай", "Релокация и визы", "Другое"]
MODELS = ["anthropic/claude-sonnet-4.5:online", "openai/gpt-4.1:online", "anthropic/claude-sonnet-4.5"]

CTX = {}   # user, notify, openrouter_key, bot_token, owner_id
S = {}


def setup(**kw):
    CTX.update(kw)


def load():
    global S
    try:
        S = json.load(open(STATE_F))
    except Exception:
        S = {}
    S.setdefault("on", True)
    S.setdefault("auto", False)
    S.setdefault("used", {})
    S.setdefault("cats", {})
    S.setdefault("history", [])
    S.setdefault("pending", {})
    S.setdefault("next", 0)


def save():
    tmp = STATE_F + ".tmp"
    json.dump(S, open(tmp, "w"), ensure_ascii=False, indent=1)
    os.replace(tmp, STATE_F)


def next_slot(after=None):
    t = datetime.fromtimestamp(after or time.time(), DUBAI)
    for d in range(0, 8):
        day = (t + timedelta(days=d)).date()
        if day.weekday() not in DAYS:
            continue
        slot = datetime(day.year, day.month, day.day, random.randint(HOURS[0], HOURS[1] - 1), random.randint(0, 59), tzinfo=DUBAI)
        if slot.timestamp() > (after or time.time()) + 600:
            return slot.timestamp()
    return time.time() + 2 * 86400


async def llm(messages, models=MODELS, max_tokens=900, json_mode=True):
    async with httpx.AsyncClient(timeout=180) as c:
        for m in models:
            try:
                body = {"model": m, "messages": messages, "temperature": 0.7, "max_tokens": max_tokens}
                r = await c.post("https://openrouter.ai/api/v1/chat/completions",
                                 headers={"Authorization": f"Bearer {CTX['openrouter_key']}", "Content-Type": "application/json",
                                          "HTTP-Referer": "https://fortex-uae.com", "X-Title": "Fortex Starters"}, json=body)
                if r.status_code != 200:
                    log.warning("llm %s -> %s %s", m, r.status_code, r.text[:200]); continue
                out = r.json()["choices"][0]["message"]["content"]
                if not json_mode:
                    return out
                mm = re.search(r"\{.*\}", out, re.S)
                if mm:
                    return json.loads(mm.group(0))
            except Exception as e:
                log.warning("llm %s: %s", m, e)
    return None


async def tg(method, data):
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post(f"https://api.telegram.org/bot{CTX['bot_token']}/{method}", data=data)
        return r.json()


async def categorize(groups):
    """Тематика чатов по названию (кэшируется)."""
    todo = [g for g in groups if str(g.id) not in S["cats"]]
    for i in range(0, len(todo), 60):
        part = todo[i:i + 60]
        res = await llm([{"role": "user", "content":
                          "Определи тематику каждого Telegram-чата по названию. Категории: " + ", ".join(CATS) +
                          ". Ответь JSON {\"<id>\": \"<категория>\", ...}.\n\n" +
                          "\n".join(f"{g.id}: {g.name}" for g in part)}], models=["anthropic/claude-haiku-4.5", "openai/gpt-4.1-mini"], max_tokens=1500)
        for g in part:
            S["cats"][str(g.id)] = (res or {}).get(str(g.id), "Другое")
    save()


async def pick_chat(exclude=()):
    u = CTX["user"]
    groups = [d for d in await u.get_dialogs(limit=300) if d.is_group and not getattr(d.entity, "left", False)]
    await categorize(groups)
    recent_cats = [h.get("cat") for h in S["history"][-2:]]
    now = time.time()
    cands = []
    for g in groups:
        if str(g.id) in exclude or now - S["used"].get(str(g.id), 0) < CHAT_COOLDOWN:
            continue
        cat = S["cats"].get(str(g.id), "Другое")
        if cat in recent_cats:
            continue
        cands.append((g, cat))
    random.shuffle(cands)
    for g, cat in cands[:12]:
        try:
            msgs = [m async for m in u.iter_messages(g.id, limit=50)]
        except Exception:
            continue
        fresh = [m for m in msgs if m.date and m.date.timestamp() > now - 3 * 86400 and m.raw_text]
        if len(fresh) < 8:
            continue  # чат неживой
        perms = getattr(g.entity, "default_banned_rights", None)
        if perms and getattr(perms, "send_messages", False):
            continue  # писать нельзя
        return g, cat, msgs
    return None, None, None


GEN = """Ты участник русскоязычного Telegram-чата. Аккаунт: Fortex_Dubai (по нику видно, что человек связан с Дубаем, это нормально). Нужно начать живое обсуждение одним сообщением.

Цель: задать вопрос или мысль, которые интересны участникам этого чата и при этом касаются тем, в которых мы сильны:
счета в банках ОАЭ (в том числе с российским паспортом, удалённо, после отказов), рабочая виза с Emirates ID и официальной зарплатой, Virtual Work,
компании в ОАЭ, налоги при доходе в ОАЭ и ВНЖ или паспорте другой страны, переводы и платежи через ОАЭ (Китай, юани, Alipay), карты ОАЭ,
переезд из Европы или России, куда едут люди и рассматривают ли Дубай.

Как выбрать тему:
- привяжись к тому, что обсуждают в чате прямо сейчас, или к свежей новости по теме чата (страна, сфера). Ищи новости за последние 7 дней через поиск;
- примеры: в чате Германии или Испании: как облагается налогом официальная зарплата в ОАЭ, если у человека ВНЖ или паспорт этой страны; в европейском чате на фоне новостей: уезжают ли люди и куда, рассматривают ли Дубай; в чате ВЭД или Китая: как удобнее платить в юанях с карты или счёта ОАЭ; в российском бизнес-чате после ухода какой-то юрисдикции или сервиса: куда переходят, смотрят ли на ОАЭ.

ГЛАВНОЕ: МЫ ПРАКТИКИ, КОТОРЫЕ ИЗУЧАЮТ БОЛЬ ЭТОЙ АУДИТОРИИ. У нас много клиентов и кейсов (счета, переводы через ОАЭ, визы, компании), мы знаем, как это решается. Нам не хватает мнения людей именно из этого чата: какие у них конкретные проблемы по теме чата. Поэтому мы спрашиваем у них опыт, как профессионалы, которые собирают картину, а не как новички.
Как строить сообщение:
- Вопрос строго про боль ЭТОЙ аудитории и ЭТОГО чата (клиенты конкретного банка: блокировки, комиссии на переводы, лимиты, закрытие карт; ВЭД: платежи поставщикам, курс, сроки; релоканты: доступ к деньгам). Не уводи в чужую тему: в чате клиентов банка не спрашивай про корпоративные счета, если там частные лица.
- Голос практика: короткое наблюдение «видим, что…» / «у многих сейчас…» (общими словами, без выдуманных цифр и историй) + вопрос, какая проблема у них конкретно и сколько это стоит им сейчас.
- ОАЭ только ВСКОЛЬЗЬ: максимум несколько слов в одном предложении, не главная мысль сообщения. Главное в сообщении: их проблема и вопрос к ним. Намёк без рекламы: «через ОАЭ это можно настроить на постоянной основе», «через счёт в Дубае такие переводы идут спокойно».
КОРОТКО: 3–4 коротких предложения, всего до 40 слов. Никаких портянок.
ФАКТЫ ТОЛЬКО АКТУАЛЬНЫЕ: многие сервисы для россиян давно закрылись или не работают (переводы Western Union, Золотая Корона и Unistream за границу, Wise, Revolut, PayPal, карты Visa и Mastercard российских банков за рубежом и т.п.). Не называй конкретные банки, сервисы, приложения и способы перевода, если не проверил поиском, что они работают СЕЙЧАС (новости за последние 3 месяца). Сомневаешься: пиши общими словами, без названий.
Пример для чата клиентов банка: «Ребят, сколько сейчас теряете на переводах за границу? Видим, многие платят под 5%. Через ОАЭ это решается спокойнее.»
НЕЛЬЗЯ: дилетантские вопросы («кто-нибудь пробовал открыть счёт в ОАЭ?»), реклама, ссылки, название компании, цены, «пишите в личку».

Правила:
- обращение к людям, которые в теме, на «вы» к чату, живо и по-человечески, без канцелярита;
- длина: 3–4 коротких предложения, до 40 слов (в чатах, где пишут одной строкой, ещё короче: {style});
- не придумывай личных историй («я переезжаю», «мой друг»); факты только из нашей базы знаний, без выдуманных цифр;
- без рекламы, без ссылок, без названия компании, без цен, без «пишите в личку»;
- не предлагай ничего скрывать от налоговой или банка, вопросы про налоги задавай честно («как это работает», «нужно ли декларировать»);
- без длинных тире, без слова «профиль», без выражения «по опыту», эмодзи нет, «:)» только в шутку и редко (примерно 1 раз из 10);
- вопрос не должен повторять наши прошлые темы: {past}.
- ТОЛЬКО прямые темы: счета и банки в ОАЭ, ВНЖ и рабочая виза ОАЭ, Emirates ID, компании в ОАЭ. В тексте должно прямо звучать ОАЭ или Дубай. Налоги других стран, Европа, крипта, новости без связи с ОАЭ не подходят.
Если в чате ничего подходящего и тема будет выглядеть притянутой, верни skip true.

Ответь JSON: {{"skip": false, "text": "<сообщение в чат>", "why": "<одной фразой: к чему привязано (новость или обсуждение) и какую нашу тему затрагивает>"}}"""


async def make_draft(exclude=()):
    g, cat, msgs = await pick_chat(exclude)
    if not g:
        return None
    lens = sorted(len(m.raw_text) for m in msgs if m.raw_text and not m.out) or [80]
    med = lens[len(lens) // 2]
    style = ("в этом чате пишут очень коротко, одной строкой, значит и ты одной строкой" if med < 50 else
             "в чате пишут коротко, 1–2 предложения" if med < 130 else "в чате пишут развёрнуто, можно 3–5 предложений")
    sample = "\n".join(f"- {m.raw_text[:300]}" for m in reversed(msgs[:35]) if m.raw_text)
    past = "; ".join(h.get("text", "")[:80] for h in S["history"][-6:]) or "нет"
    try:
        facts = open(os.path.join(BASE, "kb.md"), encoding="utf-8").read()[:9000]
    except Exception:
        facts = ""
    res = await llm([{"role": "system", "content": GEN.format(style=style, past=past) + "\n\nБАЗА ЗНАНИЙ (факты и инсайты брать только отсюда):\n" + facts},
                     {"role": "user", "content": f"Чат: {g.name}\nТематика: {cat}\n\nПоследние сообщения в чате:\n{sample[:6000]}"}])
    if not res or res.get("skip") or not res.get("text"):
        S["used"][str(g.id)] = time.time() - CHAT_COOLDOWN + 3 * 86400  # вернёмся к чату через 3 дня
        save()
        return await make_draft(tuple(exclude) + (str(g.id),)) if len(exclude) < 3 else None
    text = res["text"].strip().replace(" — ", ", ").replace("—", ",").replace("–", "-")
    if len(text.split()) > 42:  # длинно: просим сократить вдвое, смысл тот же
        r2 = await llm([{"role": "user", "content": "Сократи сообщение для чата: 3–4 коротких предложения, всего до 40 слов, смысл и тон те же, ОАЭ только вскользь, "
                         "без длинных тире. Ответь JSON {\"text\": \"...\"}.\n\n" + text}])
        if r2 and r2.get("text") and len(r2["text"].split()) < len(text.split()):
            text = r2["text"].strip().replace(" — ", ", ").replace("—", ",").replace("–", "-")
    return {"id": uuid.uuid4().hex[:8], "chat": g.id, "chat_name": g.name, "cat": cat, "text": text, "why": res.get("why", ""), "ts": time.time()}


async def post(d):
    import autoreply
    u = CTX["user"]
    m = await u.send_message(d["chat"], d["text"])
    s = autoreply._load()
    s["ours"].append([d["chat"], m.id])
    s["threads"][f"{d['chat']}:{m.id}"] = {"depth": 0, "root": d["text"], "author": 0, "history": [d["text"]], "starter": True}
    autoreply._save(s)
    S["used"][str(d["chat"])] = time.time()
    S["history"].append({"ts": time.time(), "chat": d["chat"], "chat_name": d["chat_name"], "cat": d["cat"], "text": d["text"], "msg": m.id})
    S["history"] = S["history"][-60:]
    save()
    return m.id


def kb(pid):
    return json.dumps({"inline_keyboard": [[{"text": "✅ Отправить", "callback_data": f"cstok:{pid}"},
                                            {"text": "🔄 Другой", "callback_data": f"cstre:{pid}"},
                                            {"text": "❌ Пропустить", "callback_data": f"cstno:{pid}"}]]})


async def offer(d):
    if S["auto"]:
        await post(d)
        return await tg("sendMessage", {"chat_id": CTX["owner_id"](), "text": f"💬 Начал тему в чате «{d['chat_name']}»:\n\n{d['text']}\n\nПочему: {d['why']}"})
    S["pending"][d["id"]] = d
    save()
    await tg("sendMessage", {"chat_id": CTX["owner_id"](), "reply_markup": kb(d["id"]),
                             "text": f"💬 Новая тема для чата «{d['chat_name']}» ({d['cat']})\n\n{d['text']}\n\nПочему: {d['why']}\n\n"
                                     f"Если не ответишь за 6 часов, пропущу."})


async def run_once():
    d = await make_draft()
    if d:
        await offer(d)
    else:
        log.info("starters: подходящего чата нет")


async def loop():
    load()
    if not S["next"] or next_slot() < S["next"]:  # расписание стало чаще: не ждём старый слот
        S["next"] = next_slot(); save()
    await asyncio.sleep(60)
    while True:
        try:
            if S["on"] and CTX.get("user") and time.time() >= S["next"]:
                S["next"] = next_slot(time.time() + 3600); save()
                await run_once()
            for pid, d in list(S["pending"].items()):
                if time.time() - d["ts"] > 6 * 3600:
                    S["pending"].pop(pid); save()
        except Exception:
            log.exception("starters loop")
        await asyncio.sleep(60)


async def on_button(ev, action, pid):
    load_if_needed()
    d = S["pending"].pop(pid, None)
    save()
    await tg("editMessageReplyMarkup", {"chat_id": ev.chat_id, "message_id": ev.message_id, "reply_markup": json.dumps({"inline_keyboard": []})})
    if not d:
        return await ev.answer("Уже неактуально")
    if action == "cstok":
        await post(d)
        await ev.answer("Отправлено ✅")
        await ev.respond(f"Отправил в «{d['chat_name']}». Ответы людей буду вести сам, как обычно.")
    elif action == "cstre":
        await ev.answer("Готовлю другой вариант…")
        nd = await make_draft((str(d["chat"]),))
        if nd:
            await offer(nd)
        else:
            await ev.respond("Другой подходящей темы сейчас нет")
    else:
        S["used"][str(d["chat"])] = time.time()
        save()
        await ev.answer("Пропустил")


async def command(ev):
    load_if_needed()
    parts = ev.raw_text.split()
    a = parts[1].lower() if len(parts) > 1 else ""
    if a in ("on", "off"):
        S["on"] = a == "on"
    elif a == "auto" and len(parts) > 2:
        S["auto"] = parts[2].lower() == "on"
    elif a == "now":
        await ev.reply("Подбираю чат и тему, это минута…")
        save()
        return await run_once()
    save()
    last = "\n".join(f"• {datetime.fromtimestamp(h['ts'], DUBAI):%d.%m} «{h['chat_name']}»: {h['text'][:70]}" for h in S["history"][-5:]) or "пока нет"
    await ev.reply(f"Свои темы в чатах: {'включены' if S['on'] else 'выключены'}, "
                   f"{'отправляю сам' if S['auto'] else 'черновик тебе на утверждение'}\n"
                   f"Следующая: {datetime.fromtimestamp(S['next'], DUBAI):%a %d.%m %H:%M}\n\nПоследние:\n{last}\n\n"
                   f"/starters on | off\n/starters auto on | off (без утверждения)\n/starters now (сделать тему сейчас)")


def load_if_needed():
    if not S:
        load()
