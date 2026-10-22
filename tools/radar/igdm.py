"""Директ Instagram @fortex__uae: ассистент отвечает по базе знаний, задаёт вопросы владельцу и передаёт готовых лидов.

Работает внутри радара (опрос API раз в ~45 секунд, вебхуки не нужны).
Токен: /opt/radar/ig_token (Instagram API with Instagram Login, права instagram_business_manage_messages).
База знаний: /opt/radar/kb.md. Состояние: /opt/radar/igdm.json.

Режимы: test (отвечает только аккаунтам из списка) и live (всем). Команды в боте: /igdm.
Если владелец сам написал в диалог в Instagram, ассистент в этом диалоге замолкает.
Вопрос, на который нет ответа в базе: клиенту «уточню и вернусь», владельцу вопрос в бот.
Владелец отвечает реплаем на это сообщение (голосом или текстом), ассистент пересылает ответ клиенту своими словами.
"""
import asyncio, json, logging, os, random, re, time
from datetime import datetime

import httpx

log = logging.getLogger("igdm")
BASE = os.path.dirname(os.path.abspath(__file__))
API = "https://graph.instagram.com/v21.0"
STATE_F = os.path.join(BASE, "igdm.json")
KB_F = os.path.join(BASE, "kb.md")
POLL = 45
DELAY = (60, 170)          # пауза перед ответом, сек
HISTORY = 30
MODELS = ["anthropic/claude-sonnet-4.5", "openai/gpt-4.1", "google/gemini-2.5-pro"]

CTX = {}   # openrouter_key, notify, transcribe
S = {}


def setup(**kw):
    CTX.update(kw)


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


async def send(uid, text):
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


async def reply_to(cid):
    cv = S["convs"][cid]
    cv["next_at"] = 0
    extra = ""
    if cv.get("pending_q"):
        extra = f"\n\nСейчас мы ждём ответ коллег на вопрос: «{cv['pending_q']}». Не обещай ответ ещё раз, но можешь продолжать разговор по другим темам."
    res = await llm(SYSTEM + kb(), f"Клиент: @{cv.get('username')}\nПереписка:\n{transcript(cv)}{extra}\n\nНапиши следующее сообщение клиенту.")
    if not res or not res.get("reply"):
        return
    text = clean(res["reply"])
    if not await send(cv["uid"], text):
        return
    cv["history"].append({"role": "bot", "text": text, "ts": time.time()})
    for k in ("name", "contact", "summary", "services"):
        if res.get(k):
            cv[k] = res[k]
    act = res.get("action")
    if act == "ask_owner" and res.get("owner_question"):
        cv["pending_q"] = res["owner_question"]
        m = await CTX["notify"](f"❓ Вопрос из директа Instagram (@{cv.get('username')}):\n\n{res['owner_question']}\n\n"
                                f"Ответь реплаем на это сообщение, голосом или текстом. Я перешлю клиенту своими словами.")
        if m:
            S["ask"][str(m.id)] = cid
    elif act == "handoff" and not cv.get("lead_sent"):
        cv["lead_sent"] = True
        cv["human"] = True
        await CTX["notify"](
            f"🔥 Лид из Instagram: @{cv.get('username')}\n"
            f"Имя: {cv.get('name') or '?'}\nКонтакт: {cv.get('contact') or 'не дал, пиши в директ'}\n"
            f"Интерес: {cv.get('services') or '?'}\n\n{cv.get('summary') or ''}\n\n"
            f"Переписка:\n{transcript(cv, 14)[:2500]}\n\nДальше ведёшь ты. Ассистент в этом диалоге замолчал.")
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
                        await CTX["notify"](f"Ты ответил вручную в директе @{cv.get('username')}. Ассистент в этом диалоге замолчал.\n"
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
                    await CTX["notify"](f"Новое сообщение в директе от @{cv.get('username')}. Ассистент в тестовом режиме и не отвечает.\n\n"
                                        f"«{cv['history'][-1]['text'][:300]}»")
                continue
            if not cv.get("next_at"):
                cv["next_at"] = time.time() + random.randint(*DELAY)
    save()


async def loop():
    load()
    await asyncio.sleep(20)
    while True:
        try:
            if S["enabled"] and token():
                await poll()
                now = time.time()
                for cid, cv in list(S["convs"].items()):
                    if cv.get("next_at") and cv["next_at"] <= now and not cv.get("human"):
                        await reply_to(cid)
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
    res = await llm(REWRITE, f"Вопрос клиента: {cv.get('pending_q')}\nПереписка:\n{transcript(cv, 10)}\n\nОтвет коллеги: {text}")
    out = clean((res or {}).get("reply") or text)
    if not await send(cv["uid"], out):
        await ev.reply("Instagram не принял сообщение. Возможно, прошло больше 24 часов с последнего сообщения клиента.")
        return True
    cv["history"].append({"role": "bot", "text": out, "ts": time.time()})
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
    elif a == "resume" and len(parts) > 2:
        u = parts[2].lstrip("@").lower()
        for cv in S["convs"].values():
            if (cv.get("username") or "").lower() == u:
                cv["human"] = False
                cv["lead_sent"] = False
    save()
    active = sum(1 for c in S["convs"].values() if not c.get("human"))
    await ev.reply(f"Директ Instagram: {'включён' if S['enabled'] else 'выключен'}\n"
                   f"Режим: {'тест, отвечаю только ' + ', '.join('@' + u for u in S['test_users']) if S['mode'] == 'test' else 'все клиенты'}\n"
                   f"Токен: {'есть' if token() else 'НЕТ, нужен файл /opt/radar/ig_token'}\n"
                   f"Диалогов: {len(S['convs'])}, ведёт ассистент: {active}\n\n"
                   f"/igdm on | off\n/igdm test @аккаунт (кому отвечать в тесте)\n/igdm live (отвечать всем)\n/igdm resume @аккаунт (вернуть ассистента в диалог)")


def load_if_needed():
    if not S:
        load()
