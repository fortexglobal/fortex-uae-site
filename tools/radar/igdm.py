"""Директ Instagram @fortex__uae: ассистент отвечает по базе знаний, задаёт вопросы владельцу и передаёт готовых лидов.

Работает внутри радара (опрос API раз в ~45 секунд, вебхуки не нужны).
Токен: /opt/radar/ig_token (Instagram API with Instagram Login, права instagram_business_manage_messages).
База знаний: /opt/radar/kb.md. Состояние: /opt/radar/igdm.json.

Режимы: test (отвечает только аккаунтам из списка) и live (всем). Команды в боте: /igdm.
Если владелец сам написал в диалог в Instagram, ассистент в этом диалоге замолкает.
Вопрос, на который нет ответа в базе: клиенту «уточню и вернусь», владельцу вопрос в бот.
Владелец отвечает реплаем на это сообщение (голосом или текстом), ассистент пересылает ответ клиенту своими словами.
"""
import asyncio, html, json, logging, os, random, re, time
from datetime import datetime

import httpx

log = logging.getLogger("igdm")
BASE = os.path.dirname(os.path.abspath(__file__))
API = "https://graph.instagram.com/v21.0"
STATE_F = os.path.join(BASE, "igdm.json")
KB_F = os.path.join(BASE, "kb.md")
POLL = 45
DELAY = (60, 170)          # первая реплика после паузы, сек
FAST = (7, 15)             # клиент в активной переписке, сек
ACTIVE_WIN = 10 * 60       # переписка «активна», если мы писали меньше 10 минут назад
WINDOW = 23.5 * 3600       # Instagram разрешает писать только 24 часа после сообщения клиента
QUIET = (23, 9)            # ночью по Дубаю догоняющие не шлём
HISTORY = 30
MODELS = ["anthropic/claude-sonnet-4.5", "openai/gpt-4.1", "google/gemini-2.5-pro"]

CTX = {}   # openrouter_key, notify, transcribe
S = {}


def setup(**kw):
    CTX.update(kw)
    if kw.get("user"):
        from telethon import events
        kw["user"].add_event_handler(tg_inbound, events.NewMessage(incoming=True, func=lambda e: e.is_private))
        kw["user"].add_event_handler(tg_outgoing, events.NewMessage(outgoing=True, func=lambda e: e.is_private))


def token():
    try:
        return open(os.path.join(BASE, "ig_token")).read().strip()
    except Exception:
        return ""


def load():
    global S
    try:
        S = json.load(open(STATE_F))
    except Exception:
        S = {}
    S.setdefault("enabled", True)
    S.setdefault("mode", "test")
    S.setdefault("test_users", [])
    S.setdefault("convs", {})
    S.setdefault("ask", {})
    S.setdefault("sent", [])
    S.setdefault("seen_other", [])


def save():
    S["sent"] = S["sent"][-500:]
    tmp = STATE_F + ".tmp"
    json.dump(S, open(tmp, "w"), ensure_ascii=False, indent=1)
    os.replace(tmp, STATE_F)


async def api(method, path, params=None, body=None):
    params = dict(params or {})
    params["access_token"] = token()
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.request(method, f"{API}/{path}", params=params, json=body)
    try:
        j = r.json()
    except Exception:
        j = {"error": r.text[:300]}
    if r.status_code != 200:
        log.warning("IG %s %s -> %s %s", method, path, r.status_code, str(j)[:300])
    return j


def secret(name):
    try:
        return open(os.path.join(BASE, name)).read().strip()
    except Exception:
        return ""


async def send(uid, text):
    if str(uid).startswith("mc:"):
        return await mc_send(uid[3:], text)
    if str(uid).startswith("tg:"):
        return await tg_send(int(uid[3:]), text)
    r = await api("POST", "me/messages", body={"recipient": {"id": uid}, "message": {"text": text}})
    mid = r.get("message_id")
    if mid:
        S["sent"].append(mid)
    return mid


def kb():
    try:
        return open(KB_F, encoding="utf-8").read()
    except Exception:
        return ""


SYSTEM = """Ты сотрудник отдела работы с клиентами Fortex UAE (Дубай). Отвечаешь в директе Instagram @fortex__uae от лица команды («мы»).
Цель: понять задачу человека, предложить подходящую услугу и довести до передачи менеджеру с контактом.
Продавай с пользой: если клиенту реально нужно несколько вещей (компания + виза + счёт + карта), предложи комплекс. Делай упор на корпоративные счета, рабочую визу с Emirates ID и карту Emirates NBD Skywards Infinite. Virtual Work предлагай, если нужен просто статус резидента.

Стиль:
- как живой человек в мессенджере: 1–3 коротких предложения, на «вы», по имени, если оно известно;
- один вопрос за раз, без списков (если человек сам не просит перечислить);
- без канцелярита, без длинных тире (— и –), без слова «профиль», без выражения «по опыту», эмодзи очень редко;
- первое сообщение: короткое приветствие и вопрос, чем помочь, или сразу ответ на вопрос.

Факты, цены и кейсы бери ТОЛЬКО из базы знаний ниже. Цены пиши «от X». Никаких «100% откроем».
Помогаем честно подготовить документы. Никогда не помогаем скрыть источник средств или обойти проверку: такие запросы и людей в санкционных списках вежливо отклоняй.
Не придумывай имена сотрудников и факты о компании.

Квалификация (выясняй постепенно, по ходу разговора): паспорт какой страны; есть ли компания в ОАЭ и чем занимается; есть ли Emirates ID; были ли отказы или закрытия счетов; какой банк нужен и зачем.

Когда звать владельца (action "ask_owner"): ответа нет в базе знаний, вопрос нестандартный (конкретный банк под необычную деятельность, юридические тонкости, скидки, точный срок по сложному кейсу). Тогда в reply коротко: что уточнишь у коллег и вернёшься (каждый раз своими словами), а в owner_question сам вопрос клиента с контекстом.

Когда передавать (action "handoff"): человек готов двигаться (спрашивает, как начать, просит точную цену под себя, хочет созвониться, соглашается) или просит живого человека. Сначала попроси Telegram или телефон. Как только контакт есть, action "handoff", а в reply: что менеджер свяжется в ближайшее время.

Если спрашивают, бот ли ты или живой ли человек, отвечай честно: ты ассистент команды Fortex, отвечаешь быстро и можешь подключить менеджера.

Ответь строго JSON без пояснений:
{"reply": "<текст клиенту>", "action": "none|ask_owner|handoff", "owner_question": "<если ask_owner>", "contact": "<Telegram или телефон, если клиент дал>", "name": "<имя клиента, если известно>", "summary": "<кратко: кто, задача, что предложили>", "services": "<какие услуги интересны>"}

БАЗА ЗНАНИЙ:
"""


async def llm(system, user):
    async with httpx.AsyncClient(timeout=180) as c:
        for m in MODELS:
            try:
                r = await c.post("https://openrouter.ai/api/v1/chat/completions",
                                 headers={"Authorization": f"Bearer {CTX['openrouter_key']}", "Content-Type": "application/json",
                                          "HTTP-Referer": "https://fortex-uae.com", "X-Title": "Fortex IG"},
                                 json={"model": m, "temperature": 0.4, "max_tokens": 1200,
                                       "response_format": {"type": "json_object"},
                                       "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]})
                if r.status_code != 200:
                    log.warning("llm %s -> %s", m, r.status_code); continue
                mm = re.search(r"\{.*\}", r.json()["choices"][0]["message"]["content"], re.S)
                if mm:
                    return json.loads(mm.group(0))
            except Exception as e:
                log.warning("llm %s: %s", m, e)
    return None


def clean(t):
    t = (t or "").replace(" — ", ", ").replace(" – ", ", ").replace("—", ",").replace("–", "-")
    t = re.sub(r"(?i)по опыту,?\s*", "", t)
    return t.strip()


def transcript(cv, n=HISTORY):
    who = {"user": "Клиент", "bot": "Мы", "owner": "Мы (владелец вручную)", "note": "Заметка"}
    return "\n".join(f"{who.get(h['role'], h['role'])}: {h['text']}" for h in cv["history"][-n:])


def transcript_html(cv, n=14, limit=3000):
    """Переписка для владельца: подписи жирным, реплики разделены пустой строкой."""
    who = {"user": "👤 <b>Клиент:</b>", "bot": "🤖 <b>Мы:</b>", "owner": "🧑‍💼 <b>Ты:</b>"}
    out = []
    for h in cv["history"][-n:]:
        out.append(f"{who.get(h['role'], '<b>' + h['role'] + ':</b>')} {html.escape(h['text'])}")
    t = "\n\n".join(out)
    while len(t) > limit and out:
        out.pop(0); t = "\n\n".join(out)
    return t


async def tell(cid, text, is_html=False):
    """Сообщение владельцу про диалог. Реплай на него уйдёт клиенту этого диалога."""
    body = text if is_html else html.escape(text)
    m = await CTX["notify"](body + "\n\n<i>↩️ Ответь реплаем (голосом или текстом), перешлю клиенту.</i>", parse_mode="html")
    if m:
        S["ask"][str(m.id)] = cid
        S["ask"] = dict(list(S["ask"].items())[-300:])
    return m


def last_ts(cv, role):
    return max([h.get("ts", 0) for h in cv["history"] if h["role"] == role] or [0])


def on_user_message(cv):
    """Новое сообщение клиента: отвечаем быстро, если переписка идёт, и через 1–3 минуты, если была пауза."""
    cv["last_user_ts"] = time.time()
    cv["fu"], cv["fu_at"] = 0, 0
    if not cv.get("next_at"):
        active = time.time() - last_ts(cv, "bot") < ACTIVE_WIN
        cv["next_at"] = time.time() + random.randint(*(FAST if active else DELAY))


# догоняющие: через ~15 минут, через 3–4 часа, под конец 24-часового окна Instagram
FU_PLAN = [(12 * 60, 18 * 60), (3 * 3600, 4 * 3600), None]


# в Telegram нет окна 24 часа: через ~15 минут, на следующий день и через 3 дня
FU_PLAN_TG = [(12 * 60, 18 * 60), (20 * 3600, 26 * 3600), (70 * 3600, 76 * 3600)]


def schedule_followup(cv, stage):
    cv["fu"] = stage
    cv["fu_at"] = 0
    tg = str(cv.get("uid", "")).startswith("tg:")
    plan = FU_PLAN_TG if tg else FU_PLAN
    if stage >= len(plan) or cv.get("human") or cv.get("lead_sent"):
        return
    base = cv.get("last_user_ts") or time.time()
    if tg:
        at = time.time() + random.randint(*plan[stage])
    elif FU_PLAN[stage] is None:
        at = base + 22 * 3600 + random.randint(0, 3600)
    else:
        at = time.time() + random.randint(*FU_PLAN[stage])
    h = time.gmtime(at + 4 * 3600).tm_hour  # час в Дубае
    if h >= QUIET[0] or h < QUIET[1]:
        shift = ((QUIET[1] - h) % 24) * 3600 + random.randint(0, 1800)
        at += shift
    if not tg and at - base > WINDOW:
        return  # вышли бы за 24 часа, Instagram не пропустит
    cv["fu_at"] = at


FOLLOWUP = """Ты сотрудник Fortex UAE в личных сообщениях (Instagram или Telegram). Клиент перестал отвечать. Напиши одно короткое ненавязчивое догоняющее сообщение (1–2 предложения, на «вы»), чтобы мягко вернуть его к разговору: напомни, на чём остановились, или задай простой вопрос, который легко ответить. Без давления, без «срочно», без длинных тире, без слова «профиль».
Номер догоняющего: {n} из 3. Первое лёгкое и короткое (через 15 минут), второе с пользой (короткий факт или вопрос по его задаче), третье последнее и спокойное («если вопрос актуален, пишите, будем рады помочь»).
Если по переписке видно, что клиент закончил разговор, отказался, сказал «спасибо, не надо» или ему уже всё ответили и он попрощался, не пиши: верни skip true.
Ответь JSON: {{"skip": false, "reply": "<текст>"}}"""


async def followup(cid):
    cv = S["convs"][cid]
    stage = cv.get("fu", 0)
    cv["fu_at"] = 0
    tg = str(cv.get("uid", "")).startswith("tg:")
    if cv.get("human") or cv.get("lead_sent") or cv.get("pending_q") or (not tg and time.time() - (cv.get("last_user_ts") or 0) > WINDOW):
        save(); return
    res = await llm(FOLLOWUP.format(n=stage + 1) + "\n\nБАЗА ЗНАНИЙ:\n" + kb(), f"Переписка:\n{transcript(cv)}\n\nНапиши догоняющее сообщение.")
    if not res or res.get("skip") or not res.get("reply"):
        save(); return
    text = clean(res["reply"])
    if await send(cv["uid"], text):
        cv["history"].append({"role": "bot", "text": text, "ts": time.time(), "fu": stage + 1})
        schedule_followup(cv, stage + 1)
    save()


# длина ответа чередуется, чтобы сообщения не были одинаковыми
LENGTHS = {"short": "очень коротко, 2–8 слов, одна фраза (например «Да, откроем.» или «А паспорт какой?»)",
           "medium": "одно-два коротких предложения, до 140 знаков",
           "long": "два-три предложения, до 260 знаков, только если правда нужно объяснить"}


def pick_length(cv):
    prev = cv.get("last_len")
    opts = [k for k in ("short", "medium", "long") if k != prev] if prev in ("short", "long") else ["short", "medium", "long"]
    weights = {"short": 4, "medium": 4, "long": 2}
    size = random.choices(opts, [weights[k] for k in opts])[0]
    cv["last_len"] = size
    return size


async def reply_to(cid):
    cv = S["convs"][cid]
    cv["next_at"] = 0
    extra = ""
    if cv.get("pending_q"):
        extra = f"\n\nСейчас мы ждём ответ коллег на вопрос: «{cv['pending_q']}». Не обещай ответ ещё раз, но можешь продолжать разговор по другим темам."
    size = pick_length(cv)
    if str(cv.get("uid", "")).startswith("tg:"):
        uname = cv.get("username")
        extra += ("\n\nКанал: Telegram (личные сообщения)." + (f" Контакт клиента уже есть: @{uname}. Контакт НЕ проси: когда клиент готов, сразу action handoff." if uname and not uname.isdigit() else ""))
    res = await llm(SYSTEM + kb(), f"Клиент: @{cv.get('username')}\nПереписка:\n{transcript(cv)}{extra}\n\n"
                                   f"Длина этого ответа: {LENGTHS[size]}. Не делай его похожим по длине и построению на наши прошлые сообщения.\n"
                                   f"Напиши следующее сообщение клиенту.")
    if not res or not res.get("reply"):
        return
    text = clean(res["reply"])
    if not await send(cv["uid"], text):
        return
    cv["history"].append({"role": "bot", "text": text, "ts": time.time()})
    schedule_followup(cv, 0)
    for k in ("name", "contact", "summary", "services"):
        if res.get(k):
            cv[k] = res[k]
    act = res.get("action")
    if act == "ask_owner" and res.get("owner_question"):
        cv["pending_q"] = res["owner_question"]
        await tell(cid, f"❓ <b>Вопрос из директа</b> @{html.escape(str(cv.get('username')))}\n\n"
                        f"<b>{html.escape(res['owner_question'])}</b>\n\n"
                        f"<b>━━━ Последние сообщения ━━━</b>\n\n{transcript_html(cv, 6, 1500)}", is_html=True)
    elif act == "handoff" and not cv.get("lead_sent"):
        cv["lead_sent"] = True
        cv["human"] = True
        await tell(cid,
            f"🔥 <b>Лид из Instagram:</b> @{html.escape(str(cv.get('username')))}\n\n"
            f"<b>Имя:</b> {html.escape(str(cv.get('name') or '?'))}\n"
            f"<b>Контакт:</b> {html.escape(str(cv.get('contact') or 'не дал, пиши в директ'))}\n"
            f"<b>Интерес:</b> {html.escape(str(cv.get('services') or '?'))}\n\n"
            f"<b>Кратко:</b> {html.escape(str(cv.get('summary') or ''))}\n\n"
            f"<b>━━━ Переписка ━━━</b>\n\n{transcript_html(cv)}\n\n"
            f"<b>Дальше ведёшь ты.</b> Ассистент в этом диалоге замолчал.", is_html=True)
    save()


async def poll():
    me = await api("GET", "me", {"fields": "user_id,username"})
    my_ids = {str(me.get("user_id", "")), str(me.get("id", ""))} - {""}
    if not my_ids:
        return
    convs = await api("GET", "me/conversations", {"platform": "instagram", "fields": "id,updated_time", "limit": "20"})
    for c in convs.get("data", []):
        cid = c["id"]
        cv = S["convs"].get(cid)
        if cv and cv.get("updated") == c.get("updated_time"):
            continue
        full = await api("GET", cid, {"fields": "messages.limit(15){id,message,from,created_time}"})
        msgs = list(reversed((full.get("messages") or {}).get("data", [])))
        if not msgs:
            continue
        first_time = cv is None
        if first_time:
            cv = S["convs"][cid] = {"history": [], "seen": [], "uid": None, "username": None}
        cv["updated"] = c.get("updated_time")
        new_user_msg = False
        last_user_ts = 0
        for m in msgs:
            if m["id"] in cv["seen"]:
                continue
            cv["seen"].append(m["id"])
            frm = m.get("from") or {}
            text = (m.get("message") or "").strip() or "[вложение]"
            if str(frm.get("id")) in my_ids:
                if m["id"] not in S["sent"] and not first_time:
                    cv["history"].append({"role": "owner", "text": text, "ts": time.time()})
                    if not cv.get("human"):
                        cv["human"] = True
                        await tell(cid, f"Ты ответил вручную в директе @{cv.get('username')}. Ассистент в этом диалоге замолчал.\n"
                                            f"Вернуть его: /igdm resume {cv.get('username')}")
                elif first_time:
                    cv["history"].append({"role": "bot", "text": text, "ts": time.time()})
                continue
            cv["uid"] = frm.get("id")
            cv["username"] = frm.get("username") or cv.get("username")
            cv["history"].append({"role": "user", "text": text, "ts": time.time()})
            new_user_msg = True
            try:
                last_user_ts = datetime.strptime(m["created_time"], "%Y-%m-%dT%H:%M:%S%z").timestamp()
            except Exception:
                last_user_ts = time.time()
        cv["seen"] = cv["seen"][-60:]
        cv["history"] = cv["history"][-60:]
        # при первом запуске старые диалоги только запоминаем; на сообщения старше 2 часов не отвечаем
        if not S.get("booted") or time.time() - last_user_ts > 7200:
            continue
        if new_user_msg and not cv.get("human"):
            allowed = S["mode"] == "live" or (cv.get("username") or "").lower() in [u.lower() for u in S["test_users"]]
            if not allowed:
                if cid not in S["seen_other"]:
                    S["seen_other"].append(cid)
                    await tell(cid, f"Новое сообщение в директе от @{cv.get('username')}. Ассистент в тестовом режиме и не отвечает.\n\n"
                                        f"«{cv['history'][-1]['text'][:300]}»")
                continue
            on_user_message(cv)
    save()


async def loop():
    load()
    asyncio.get_event_loop().create_task(http_server())
    await asyncio.sleep(20)
    while True:
        try:
            if S["enabled"] and (token() or secret("manychat_key")):
                if S.get("transport", "graph") == "graph" and token():
                    await poll()
                now = time.time()
                for cid, cv in list(S["convs"].items()):
                    if cv.get("next_at") and cv["next_at"] <= now and not cv.get("human"):
                        await reply_to(cid)
                    elif cv.get("fu_at") and cv["fu_at"] <= now and not cv.get("next_at"):
                        await followup(cid)
                if not S.get("booted"):
                    S["booted"] = True
                    save()
        except Exception:
            log.exception("igdm loop")
        await asyncio.sleep(POLL)


REWRITE = """Ты сотрудник Fortex UAE в директе Instagram. Коллега (владелец) дал ответ на вопрос клиента, часто это расшифровка голосового.
Перескажи его клиенту коротко и по-человечески, 1–3 предложения, на «вы», без длинных тире, без слова «профиль». Ничего не добавляй от себя, кроме вежливой связки.
Ответь JSON: {"reply": "<текст клиенту>"}"""


async def maybe_handle(ev, text):
    """Реплай владельца на вопрос из директа. True = обработано здесь."""
    rid = getattr(ev, "reply_to_msg_id", None)
    if not rid or not S.get("ask"):
        return False
    cid = S["ask"].get(str(rid))
    if not cid:
        return False
    cv = S["convs"].get(cid)
    if ev.voice or ev.audio:
        await ev.reply("Расшифровываю…")
        text = await CTX["transcribe"](ev)
        if not text:
            await ev.reply("Не расшифровалось, ответь ещё раз реплаем или текстом")
            return True
    log.info("owner reply for %s", cid)
    last_q = cv.get("pending_q") or next((h["text"] for h in reversed(cv["history"]) if h["role"] == "user"), "")
    res = await llm(REWRITE, f"Вопрос клиента: {last_q}\nПереписка:\n{transcript(cv, 10)}\n\nОтвет коллеги: {text}")
    out = clean((res or {}).get("reply") or text)
    if not await send(cv["uid"], out):
        await ev.reply("Instagram не принял сообщение. Возможно, прошло больше 24 часов с последнего сообщения клиента.")
        return True
    cv["history"].append({"role": "bot", "text": out, "ts": time.time()})
    schedule_followup(cv, 0)
    cv["pending_q"] = None
    S["ask"].pop(str(rid), None)
    save()
    await ev.reply(f"Отправил @{cv.get('username')}:\n\n{out}")
    return True


async def command(ev):
    load_if_needed()
    parts = ev.raw_text.split()
    a = parts[1].lower() if len(parts) > 1 else ""
    if a in ("on", "off"):
        S["enabled"] = a == "on"
    elif a == "test":
        S["mode"] = "test"
        if len(parts) > 2:
            S["test_users"] = [p.lstrip("@") for p in parts[2:]]
    elif a == "live":
        S["mode"] = "live"
    elif a == "tg" and len(parts) > 2:
        S["tg_enabled"] = parts[2].lower() == "on"
    elif a == "manychat":
        S["transport"] = "manychat"
    elif a == "graph":
        S["transport"] = "graph"
    elif a == "pause" and len(parts) > 2:
        u = parts[2].lstrip("@").lower()
        for cv in S["convs"].values():
            if (cv.get("username") or "").lower() == u:
                cv["human"] = True
                cv["next_at"] = 0
    elif a == "resume" and len(parts) > 2:
        u = parts[2].lstrip("@").lower()
        for cv in S["convs"].values():
            if (cv.get("username") or "").lower() == u:
                cv["human"] = False
                cv["lead_sent"] = False
    save()
    active = sum(1 for c in S["convs"].values() if not c.get("human"))
    tg_name = ""
    try:
        if CTX.get("user"):
            me = await CTX["user"].get_me()
            tg_name = f" @{me.username}" if me and me.username else ""
    except Exception:
        pass
    await ev.reply(f"Директ Instagram: {'включён' if S['enabled'] else 'выключен'}\n"
                   f"Режим: {'тест, отвечаю только ' + ', '.join('@' + u for u in S['test_users']) if S['mode'] == 'test' else 'все клиенты'}\n"
                   f"Канал: {'ManyChat' if S.get('transport') == 'manychat' else 'Instagram API'}\n"
                   f"Telegram (аккаунт радара{tg_name}): {'включён' if S.get('tg_enabled') else 'выключен'}\n"
                   f"Токен Instagram: {'есть' if token() else 'нет'}, ключ ManyChat: {'есть' if secret('manychat_key') else 'нет'}\n"
                   f"Диалогов: {len(S['convs'])}, ведёт ассистент: {active}\n\n"
                   f"/igdm on | off\n/igdm test @аккаунт (кому отвечать в тесте)\n/igdm live (отвечать всем)\n/igdm pause @аккаунт (ассистент молчит в диалоге)\n/igdm resume @аккаунт (вернуть ассистента)\n/igdm manychat | graph (откуда берём сообщения)\n/igdm tg on | off (отвечать в личке аккаунта радара)")


def load_if_needed():
    if not S:
        load()



# ===== ManyChat: входящие через External Request, исходящие через API =====
# ManyChat -> POST https://<сервер>/mc/<mc_secret> (Body: Add Full Contact Data) -> отвечаем 200 сразу,
# ассистент пишет позже через https://api.manychat.com/fb/sending/sendContent.
MC_PORT = 8088


async def mc_send(sub_id, text):
    body = {"subscriber_id": int(sub_id) if str(sub_id).isdigit() else sub_id,
            "data": {"version": "v2", "content": {"type": "instagram", "messages": [{"type": "text", "text": text}]}}}
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post("https://api.manychat.com/fb/sending/sendContent", json=body,
                         headers={"Authorization": f"Bearer {secret('manychat_key')}"})
    if r.status_code != 200 or '"success"' not in r.text:
        log.warning("manychat send -> %s %s", r.status_code, r.text[:300])
        return None
    return "mc-" + str(time.time())


# первое сообщение в директ после комментария шлёт сам ManyChat; текст должен совпадать с тем, что в ManyChat
OPENER = ("Здравствуйте! Спасибо за комментарий 🙌 Расскажите коротко о задаче: "
          "нужен счёт, виза или компания? И какой у вас паспорт?")


def mc_comment(data):
    """Клиент оставил комментарий, ManyChat уже написал ему OPENER. Запоминаем контекст, сами не отвечаем."""
    sid = str(data.get("id") or data.get("subscriber_id") or "")
    if not sid:
        return
    uname = next((str(v) for k, v in data.items() if "username" in k.lower() and v), "")
    cid = "mc:" + sid
    cv = S["convs"].setdefault(cid, {"history": [], "seen": [], "uid": cid, "username": uname or sid})
    comment = (data.get("last_input_text") or "").strip()
    cv["history"].append({"role": "note", "text": f"Клиент оставил комментарий под постом: «{comment}»", "ts": time.time()})
    cv["history"].append({"role": "bot", "text": OPENER, "ts": time.time()})
    cv["source"] = "comment"
    save()


async def mc_inbound(data):
    sid = str(data.get("id") or data.get("subscriber_id") or "")
    text = (data.get("last_input_text") or data.get("text") or "").strip()
    if not sid or not text:
        return
    uname = next((str(v) for k, v in data.items() if "username" in k.lower() and v), "")
    username = (uname or data.get("name") or sid).lstrip("@")
    S["mc_last_keys"] = sorted(data.keys())[:60]
    cid = "mc:" + sid
    cv = S["convs"].setdefault(cid, {"history": [], "seen": [], "uid": cid, "username": username})
    cv["uid"], cv["username"] = cid, username
    if data.get("first_name") or data.get("name"):
        cv.setdefault("name", data.get("first_name") or data.get("name"))
    cv["history"].append({"role": "user", "text": text, "ts": time.time()})
    cv["history"] = cv["history"][-60:]
    if not S["enabled"] or cv.get("human"):
        save(); return
    allowed = S["mode"] == "live" or bool({username.lower(), sid} & {u.lower() for u in S["test_users"]})
    if not allowed:
        if cid not in S["seen_other"]:
            S["seen_other"].append(cid)
            await tell(cid, f"Новое сообщение в директе от @{username}. Ассистент в тестовом режиме и не отвечает.\n\n«{text[:300]}»\n\nЧтобы тестировать на нём: /igdm test {username}")
        save(); return
    on_user_message(cv)
    save()


async def http_server():
    async def handle(reader, writer):
        status, out = "404 Not Found", b"{}"
        try:
            head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 15)
            lines = head.decode("latin-1").split("\r\n")
            method, path = lines[0].split(" ")[:2]
            hdr = {l.split(":", 1)[0].strip().lower(): l.split(":", 1)[1].strip() for l in lines[1:] if ":" in l}
            body = await asyncio.wait_for(reader.readexactly(int(hdr.get("content-length", "0") or 0)), 15)
            sec = secret("mc_secret")
            if method == "POST" and sec and path.split("?")[0] == f"/mc/{sec}/comment":
                load_if_needed()
                mc_comment(json.loads(body or b"{}"))
                status, out = "200 OK", b'{"version":"v2","content":{"messages":[]}}'
            elif method == "POST" and sec and path.split("?")[0] == f"/mc/{sec}":
                load_if_needed()
                await mc_inbound(json.loads(body or b"{}"))
                status, out = "200 OK", b'{"version":"v2","content":{"messages":[]}}'
            elif method == "GET" and path == "/health":
                status, out = "200 OK", b'{"ok":true}'
        except Exception as e:
            log.warning("http: %s", e)
            status = "400 Bad Request"
        writer.write(f"HTTP/1.1 {status}\r\nContent-Type: application/json\r\nContent-Length: {len(out)}\r\nConnection: close\r\n\r\n".encode() + out)
        try:
            await writer.drain()
        finally:
            writer.close()
    try:
        srv = await asyncio.start_server(handle, "127.0.0.1", MC_PORT)
        async with srv:
            await srv.serve_forever()
    except Exception as e:
        log.warning("http server: %s", e)



# ===== Telegram: аккаунт радара отвечает тем, кто написал ему в личку =====
async def tg_send(peer, text):
    u = CTX.get("user")
    if not u:
        return None
    try:
        await u.send_read_acknowledge(peer)
        async with u.action(peer, "typing"):
            await asyncio.sleep(min(2 + len(text) / 25, 8) + random.uniform(0, 1.5))
        m = await u.send_message(peer, text)
        S["sent"].append(f"tg:{m.id}")
        return m.id
    except Exception as e:
        log.warning("tg send: %s", e)
        return None


async def tg_inbound(ev):
    try:
        load_if_needed()
        if not S.get("tg_enabled"):
            return
        snd = await ev.get_sender()
        if not snd or getattr(snd, "bot", False) or getattr(snd, "id", 0) == 777000:
            return
        text = (ev.raw_text or "").strip()
        if not text:
            text = "[голосовое или вложение]" if ev.media else ""
        if not text:
            return
        cid = f"tg:{snd.id}"
        cv = S["convs"].setdefault(cid, {"history": [], "seen": [], "uid": cid, "username": None})
        cv["username"] = snd.username or str(snd.id)
        cv.setdefault("name", " ".join(x for x in (snd.first_name, snd.last_name) if x) or None)
        cv["history"].append({"role": "user", "text": text, "ts": time.time()})
        cv["history"] = cv["history"][-60:]
        if cv.get("human"):
            save(); return
        allowed = S["mode"] == "live" or bool({(snd.username or "").lower(), str(snd.id)} & {u.lower() for u in S["test_users"]})
        if not allowed:
            if cid not in S["seen_other"]:
                S["seen_other"].append(cid)
                await tell(cid, f"Новое сообщение в Telegram (аккаунт радара) от @{cv['username']}. Ассистент в тестовом режиме и не отвечает.\n\n«{text[:300]}»\n\nЧтобы тестировать на нём: /igdm test {cv['username']}")
            save(); return
        on_user_message(cv)
        save()
    except Exception:
        log.exception("tg inbound")


async def tg_outgoing(ev):
    """Кто-то вручную написал с аккаунта радара: ассистент в этом диалоге замолкает."""
    try:
        load_if_needed()
        if f"tg:{ev.id}" in S["sent"]:
            return
        await asyncio.sleep(2)
        if f"tg:{ev.id}" in S["sent"]:
            return
        cid = f"tg:{ev.chat_id}"
        cv = S["convs"].get(cid)
        if not cv:
            return
        cv["history"].append({"role": "owner", "text": ev.raw_text or "", "ts": time.time()})
        if not cv.get("human"):
            cv["human"], cv["next_at"], cv["fu_at"] = True, 0, 0
            await tell(cid, f"С аккаунта радара вручную ответили @{cv.get('username')}. Ассистент в этом диалоге замолчал.\nВернуть: /igdm resume {cv.get('username')}")
        save()
    except Exception:
        log.exception("tg outgoing")
