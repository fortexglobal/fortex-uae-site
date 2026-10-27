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
FAST = (1, 1)              # клиент в активной переписке: старт почти сразу (1 сек на случай нескольких сообщений подряд)
RUNNING = set()            # диалоги, где ответ уже готовится


def target_secs(text):
    """Сколько секунд «печатаем» в активной переписке: коротко 3, средне 5, длинно 7."""
    n = len(text)
    return 3 if n <= 60 else 5 if n <= 160 else 7
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
        kw["user"].add_event_handler(tg_typing, events.UserUpdate(func=lambda e: bool(getattr(e, "typing", False))))


TYPING = {}  # id собеседника -> когда он последний раз «печатал» (Telegram шлёт это примерно раз в 5 с)


async def tg_typing(ev):
    TYPING[ev.user_id] = time.time()


async def wait_quiet(peer, cid=None, max_wait=120):
    """Ждём, пока человек допишет мысль: он не печатает хотя бы 6 с и с его последнего сообщения прошло 3 с."""
    t_end = time.time() + max_wait
    while time.time() < t_end:
        cv = S["convs"].get(cid) if cid else None
        last_msg = (cv or {}).get("last_user_ts", 0)
        if time.time() - TYPING.get(peer, 0) >= 6 and time.time() - last_msg >= 3:
            return
        await asyncio.sleep(1)


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
    if not S.get("live_2710"):  # 27.10 Александр: Алексей консультирует всех, кто пишет
        S["mode"], S["live_2710"], S["tg_enabled"] = "live", True, True
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
Цель: понять задачу человека, предложить подходящую услугу и довести до передачи руководителю с контактом.
Продавай с пользой: если клиенту реально нужно несколько вещей (компания + виза + счёт + карта), предложи комплекс. Делай упор на корпоративные счета, рабочую визу с Emirates ID и карту Emirates NBD Skywards Infinite. Virtual Work предлагай, если нужен просто статус резидента.

Стиль:
- как живой человек в мессенджере: 1–3 коротких предложения, на «вы», по имени, если оно известно;
- один вопрос за раз, без списков (если человек сам не просит перечислить);
- НЕ ДОПРОС: вопросы не подряд в каждом сообщении. Часто просто подтверди, что услышал, и добавь что-то полезное: «Понял», «Принято», «Ага, ясно», «Окей, тогда так», «Тут понятно». Примерно через раз сообщение без вопроса;
- перед каждым ответом перечитай всю переписку: никогда не спрашивай то, что уже спрашивал или на что человек уже ответил (даже другими словами). Если ответ был неполный, уточни по-другому, а не тем же вопросом;
- без канцелярита, без длинных тире (— и –), без слова «профиль», без выражения «по опыту»;
- смайлик «:)» или эмодзи очень редко: примерно одно сообщение из 7–10, не чаще. Обычно без них;
- первое сообщение: короткое приветствие и вопрос, чем помочь, или сразу ответ на вопрос.

Факты, цены и кейсы бери ТОЛЬКО из базы знаний ниже. Цены пиши «от X». Никаких «100% откроем».
Помогаем честно подготовить документы. Никогда не помогаем скрыть источник средств или обойти проверку: такие запросы и людей в санкционных списках вежливо отклоняй.
Не придумывай имена сотрудников и факты о компании.

Квалификация (выясняй постепенно, по ходу разговора): паспорт какой страны; есть ли компания в ОАЭ и чем занимается; есть ли Emirates ID; были ли отказы или закрытия счетов; какой банк нужен и зачем.

Когда звать владельца (action "ask_owner"): ответа нет в базе знаний, вопрос нестандартный (конкретный банк под необычную деятельность, юридические тонкости, скидки, точный срок по сложному кейсу). Тогда в reply коротко: что уточнишь у коллег и вернёшься (каждый раз своими словами), а в owner_question сам вопрос клиента с контекстом.

Когда передавать (action "handoff"): человек готов двигаться (спрашивает, как начать, просит точную цену под себя, хочет созвониться, соглашается) или просит живого человека. Сначала попроси Telegram или телефон. Как только контакт есть, action "handoff", а в reply: что подключаешь руководителя (руководство), он напишет лично с аккаунта компании @FortexGlobal (там логотип, это наш официальный аккаунт), каждый раз своими словами. Слово «менеджер» не используй.

Вопросы не по делу (в Telegram про себя можно немного рассказать, см. правило канала ниже; погода, политика, кто основатель, где офис, сколько сотрудников, шутки, просто болтовня): не отвечай по существу и ничего не выдумывай. Вежливо и легко уйди от темы (можно с лёгким юмором), а следующей фразой верни разговор к задаче клиента или к нашему предложению. Например: «Про погоду лучше спросить пляж :) Давайте лучше про вашу задачу: счёт нужен для компании или личный?» или «Это не ко мне... А вот со счётом в ОАЭ помогу. Компания у вас уже есть?». Если клиент так и не говорит о задаче, предложи самое ходовое: корпоративный счёт, рабочую визу с Emirates ID или карту Skywards Infinite, одной фразой. Не дави и не повторяй одно и то же предложение дважды подряд.

Если сообщение непонятное (обрывок, опечатки, неясно, что нужно): коротко и по-дружески переспроси, можно со смайликом. Например: «Не совсем понял :) Что вы хотели узнать?» или «Здравствуйте! Подскажите, что вас интересует?».
КОГДА ОСТАНОВИТЬСЯ: если разговор по сути завершён (договорились о следующем шаге, мы уже попрощались или подтвердили, а клиент пишет «ок», «хорошо», «спасибо», «понял», «напишу», «договорились»), не отвечай текстом на каждое такое сообщение. Верни action "react" с пустым reply и reaction "👍" (или "🤝", если о чём-то договорились). Мы сами напомним о себе позже догоняющим сообщением. Отвечай текстом, только если в сообщении есть новый вопрос или новая информация.
ЭМОДЗИ: обычно без них. Но когда уместно, особенно в конце, когда договорились («Да, так и сделаем», «Договорились»), можно поставить 👍 или 🤝 в конце сообщения. Не чаще одного раза на несколько сообщений.
Если человек второй раз подряд уходит не в нашу тему или явно не нуждается в наших услугах: вежливо закрой разговор одной фразой («Понял, спасибо! Если понадобится счёт или виза в ОАЭ, пишите :)») и верни action "close". Если сообщение бессмысленное, спам, реклама чужих услуг, грубость, похоже на мошенника (обнал, «серые» схемы, просьбы скрыть деньги, подозрительные ссылки, предложения «заработка») или человек раз за разом пишет не по теме: ничего не пиши, верни action "ignore" и пустой reply. После этого мы с ним больше не общаемся.
Не в каждом сообщении задавай вопрос: если клиент сам ведёт разговор, иногда просто ответь по делу.

ПАРТНЁРЫ. Иногда пишет не клиент, а потенциальный партнёр: риелтор, юрист, бухгалтер, агентство, банкир, консультант, у которого есть свои клиенты («у меня есть клиенты», «хотим сотрудничать», «вы работаете с агентами?», «какие условия для партнёров»). С ним говори иначе, не продавай услугу ему лично:
- сначала вежливо уточни, кто он и почему интересуется: чем занимается, какие у него клиенты, с какими задачами;
- скажи, что мы работаем с партнёрами, условия обсуждаем под каждый случай; попроси коротко описать идею или предложение: кто клиенты, сколько примерно, какие услуги нужны, как видит сотрудничество;
- когда он описал предложение по существу, верни action "partner": в reply напиши, что передал команде, обсудим и вернёмся; в summary кратко: кто он, чем занимается, страна, какие клиенты и услуги, что предлагает.
Не обещай процент или конкретные условия.

Если спрашивают, бот ли ты или живой ли человек, отвечай честно: ты ассистент команды Fortex, отвечаешь быстро и можешь подключить руководителя.

Ответь строго JSON без пояснений:
{"reply": "<текст клиенту>", "action": "none|ask_owner|handoff|partner|close|ignore|react", "reaction": "<👍 или 🤝, только для react>", "owner_question": "<если ask_owner>", "contact": "<Telegram или телефон, если клиент дал>", "name": "<имя клиента, если известно>", "summary": "<кратко: кто, задача, что предложили>", "services": "<какие услуги интересны>"}

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
                                       # system (правила + база знаний) одинаковый: кэшируем, повторно стоит ~в 10 раз дешевле
                                       "messages": [{"role": "system", "content": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]},
                                                    {"role": "user", "content": user}]})
                if r.status_code != 200:
                    log.warning("llm %s -> %s", m, r.status_code); continue
                mm = re.search(r"\{.*\}", r.json()["choices"][0]["message"]["content"], re.S)
                if mm:
                    return json.loads(mm.group(0))
            except Exception as e:
                log.warning("llm %s: %s", m, e)
    return None


EMOJI_RE = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF]" + r"|:\)|\)\)+|;\)")


def tame_emoji(t, cv):
    """Смайлики редко: не чаще одного на 7 наших сообщений."""
    recent = [h["text"] for h in cv["history"] if h["role"] == "bot"][-7:]
    deal = re.search(r"[👍🤝]\s*$", t) and not any(re.search(r"[👍🤝]", x) for x in recent[-3:])
    if deal:  # 👍/🤝 в конце, когда договорились: оставляем, если недавно не было
        return re.sub(EMOJI_RE.pattern.replace("[\U0001F300-\U0001FAFF\u2600-\u27BF]|", ""), "", t).strip()
    if any(EMOJI_RE.search(x) for x in recent) or random.random() < 0.6:
        t = EMOJI_RE.sub("", t)
        t = re.sub(r"\s+([.,!?])", r"\1", t)
        t = re.sub(r"\s{2,}", " ", t).strip()
    return t


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
    active = time.time() - last_ts(cv, "bot") < ACTIVE_WIN
    if active:
        cv["next_at"] = time.time() + 0.4
        cv["fast"] = True
        cid = cv.get("uid")
        if cid in S["convs"]:
            asyncio.get_event_loop().create_task(kick(cid, 0.5))
    elif not cv.get("next_at"):
        cv["next_at"] = time.time() + random.randint(*DELAY)
        cv["fast"] = False


async def kick(cid, delay):
    await asyncio.sleep(delay)
    cv = S["convs"].get(cid)
    if cv and cv.get("next_at") and cv["next_at"] <= time.time() and not cv.get("human"):
        await reply_to(cid)


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
Если мы уже нормально общались (было несколько сообщений с обеих сторон), пиши тепло, как знакомому: по имени, если знаешь («Сергей, привет! Как ваши дела?», «Как продвигается с переездом?»), и только потом по делу. В Telegram ты Алексей, пиши от первого лица.
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
    if cid in RUNNING:
        return
    RUNNING.add(cid)
    try:
        await _reply_to(cid)
    finally:
        RUNNING.discard(cid)


async def _reply_to(cid):
    cv = S["convs"][cid]
    cv["next_at"] = 0
    # в живой переписке время считаем от сообщения клиента, иначе от начала ответа
    t0 = cv.get("last_user_ts", time.time()) if cv.get("fast") else time.time()
    is_tg = str(cv.get("uid", "")).startswith("tg:")
    u = CTX.get("user")
    typing = None
    if is_tg and u:
        await wait_quiet(int(cv["uid"][3:]), cid)  # человек допечатывает: не перебиваем
    if is_tg and u:
        try:
            peer = int(cv["uid"][3:])
            await asyncio.sleep(random.uniform(2, 3))  # прочитано не мгновенно
            await u.send_read_acknowledge(peer)
        except Exception as e:
            log.warning("tg read: %s", e)
    extra = ""
    if cv.get("pending_q"):
        extra = f"\n\nСейчас мы ждём ответ коллег на вопрос: «{cv['pending_q']}». Не обещай ответ ещё раз, но можешь продолжать разговор по другим темам."
    if cv.get("lead_sent"):
        extra += ("\n\nКлиент уже передан руководителю. Не проси контакт снова и не делай action handoff. "
                  "Отвечай коротко на его вопросы по базе знаний, а если вопрос про следующий шаг, скажи, что руководитель уже в курсе и скоро напишет с аккаунта @FortexGlobal. "
                  "Если он просто благодарит или прощается, ответь одной короткой фразой.")
    if str(cv.get("uid", "")).startswith("tg:") and cv.get("source") == "напрямую" and not cv.get("asked_src") \
            and sum(1 for h in cv["history"] if h["role"] == "bot") >= 2:
        extra += ("\n\nМы не знаем, откуда клиент о нас узнал. В этом сообщении, если это к месту (не в разгар важного вопроса), "
                  "между делом один раз спроси, где он нас нашёл («Кстати, подскажите, где вы нас нашли?»). Больше этот вопрос не задавай.")
        cv["asked_src"] = time.time()
    size = pick_length(cv)
    if str(cv.get("uid", "")).startswith("tg:"):
        uname = cv.get("username")
        extra += ("\n\nКанал: Telegram (личные сообщения). Здесь ты Алексей и пишешь от первого лица («я», «у нас с командой»). "
                  "Алексей живёт в Дубай Марине, в Дубае с 2022 года, с командой помогает с банками, визами и компаниями в ОАЭ. "
                  "Это можно коротко и по-свойски рассказать, если спросят или к слову, можно чуть поболтать про жизнь в Дубае с лёгкой иронией, "
                  "но разговор мягко возвращай к задаче клиента и к сделке. Других личных подробностей не придумывай. "
                  "Пиши как в мессенджере: короткие предложения, каждое уйдёт отдельным сообщением, без кавычек, максимум 3–4 предложения." + (f" Контакт клиента уже есть: @{uname}. Контакт НЕ проси: когда клиент готов, сразу action handoff." if uname and not uname.isdigit() else ""))
    prev = [h for h in cv["history"][:-1] if h["role"] in ("user", "bot", "owner")]
    gap = (cv.get("last_user_ts", time.time()) - prev[-1]["ts"]) if prev and prev[-1].get("ts") else 0
    if len(prev) >= 2 and gap > 12 * 3600:  # человек вернулся после паузы: мы уже знакомы
        nm = cv.get("name") or ""
        extra += (f"\n\nЧеловек вернулся после паузы ({int(gap // 3600)} ч), мы уже общались раньше. Начни тепло, как со знакомым: "
                  f"по имени{(' (' + nm + ')') if nm else ''}, например «О, {nm or 'привет'}! Как ваши дела?» или «Рад снова слышать», "
                  "можно одной фразой вспомнить, о чём говорили в прошлый раз. Потом коротко по делу. Не пересказывай всю прошлую переписку.")
    t_ask = time.time()
    res = await llm(SYSTEM + kb(), f"Клиент: @{cv.get('username')}\nПереписка:\n{transcript(cv)}{extra}\n\n"
                                   f"Длина этого ответа: {LENGTHS[size]}. Не делай его похожим по длине и построению на наши прошлые сообщения.\n"
                                   f"Напиши следующее сообщение клиенту.")
    if res and res.get("action") == "ignore":
        if typing:
            await typing.__aexit__(None, None, None)
        cv["fu_at"] = 0
        cv["muted"] = True  # скамер, спам, грубость, не наш человек: больше не отвечаем
        save()
        return
    if res and res.get("action") == "react":  # разговор закончен: не пишем, ставим реакцию на последнее сообщение клиента
        if is_tg and u:
            try:
                from telethon.tl.functions.messages import SendReactionRequest
                from telethon.tl.types import ReactionEmoji
                peer = int(cv["uid"][3:])
                async for m in u.iter_messages(peer, limit=5):
                    if not m.out:
                        emo = res.get("reaction") if res.get("reaction") in ("👍", "🤝") else "👍"
                        await asyncio.sleep(random.uniform(3, 8))
                        await u(SendReactionRequest(peer=peer, msg_id=m.id, reaction=[ReactionEmoji(emoticon=emo)]))
                        break
            except Exception as e:
                log.warning("tg react: %s", e)
        cv["history"].append({"role": "note", "text": "(поставили реакцию, разговор на паузе)", "ts": time.time()})
        save()
        return
    if not res or not res.get("reply"):
        if typing:
            await typing.__aexit__(None, None, None)
        return
    text = tame_emoji(clean(res["reply"]), cv)
    if is_tg and u:
        if cv.get("last_user_ts", 0) > t_ask:  # пока думали, человек дописал: отвечаем уже на всё вместе
            cv["next_at"] = time.time()
            asyncio.get_event_loop().create_task(kick(cid, 1))
            return
        ok = await tg_human(int(cv["uid"][3:]), text)
    else:
        # «печатаем» так, чтобы от начала до ответа прошло 3/5/7 секунд (если нейросеть думала дольше, отвечаем сразу)
        await asyncio.sleep(max(0, target_secs(text) - (time.time() - t0)))
        ok = await send(cv["uid"], text)
    if not ok:
        return
    cv["history"].append({"role": "bot", "text": text, "ts": time.time()})
    if res.get("action") == "close":
        cv["fu_at"] = 0  # разговор закрыт: догоняющие не шлём
        cv["muted"] = True  # не наш клиент: дальше не отвечаем
    else:
        schedule_followup(cv, 0)
    for k in ("name", "contact", "summary", "services"):
        if res.get(k):
            cv[k] = res[k]
    act = res.get("action")
    if act == "ask_owner" and res.get("owner_question"):
        cv["pending_q"] = res["owner_question"]
        await tell(cid, f"❓ <b>Вопрос из {'Telegram' if is_tg else 'директа'}</b> @{html.escape(str(cv.get('username')))}\n\n"
                        f"<b>{html.escape(res['owner_question'])}</b>\n\n"
                        f"<b>━━━ Последние сообщения ━━━</b>\n\n{transcript_html(cv, 6, 1500)}", is_html=True)
    elif cv.get("lead_sent"):
        # клиент уже передан: ассистент отвечает дальше, а тебе показываем, что он написал
        await tell(cid, f"💬 <b>Клиент уже у тебя</b> @{html.escape(str(cv.get('username')))} написал снова\n\n"
                        f"{transcript_html(cv, 2, 1200)}", is_html=True)
    elif act == "partner":
        cv["lead_sent"] = True
        cv["partner"] = True
        await tell(cid,
            f"🤝 <b>Партнёр из {'Telegram' if is_tg else 'Instagram'}:</b> @{html.escape(str(cv.get('username')))}\n\n"
            f"<b>Имя:</b> {html.escape(str(cv.get('name') or '?'))}\n"
            f"<b>Суть:</b> {html.escape(str(cv.get('summary') or ''))}\n\n"
            f"<b>━━━ Переписка ━━━</b>\n\n{transcript_html(cv)}\n\n"
            f"<b>Ассистент сказал, что команда обсудит и вернётся.</b> Ответь ему сам или реплаем сюда.", is_html=True)
    elif act == "handoff":
        cv["lead_sent"] = True
        await tell(cid,
            f"🔥 <b>Лид из {'Telegram' if is_tg else 'Instagram'}:</b> @{html.escape(str(cv.get('username')))}\n\n"
            f"<b>Имя:</b> {html.escape(str(cv.get('name') or '?'))}\n"
            f"<b>Контакт:</b> {html.escape(str(cv.get('contact') or 'не дал, пиши в директ'))}\n"
            f"<b>Интерес:</b> {html.escape(str(cv.get('services') or '?'))}\n\n"
            f"<b>Кратко:</b> {html.escape(str(cv.get('summary') or ''))}\n\n"
            f"<b>━━━ Переписка ━━━</b>\n\n{transcript_html(cv)}\n\n"
            f"<b>Дальше ведёшь ты.</b> Пока ты не написал клиенту сам, ассистент вежливо отвечает на его вопросы и говорит, что руководитель скоро свяжется.", is_html=True)
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
            if S["enabled"]:
                if S.get("transport", "graph") == "graph" and token() and time.time() - S.get("_polled", 0) >= POLL:
                    S["_polled"] = time.time()
                    await poll()
                now = time.time()
                for cid, cv in list(S["convs"].items()):
                    if cv.get("next_at") and cv["next_at"] <= now and not cv.get("human"):
                        asyncio.get_event_loop().create_task(reply_to(cid))
                    elif cv.get("fu_at") and cv["fu_at"] <= now and not cv.get("next_at"):
                        await followup(cid)
                if not S.get("booted"):
                    S["booted"] = True
                    save()
        except Exception:
            log.exception("igdm loop")
        await asyncio.sleep(2)


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
async def tg_human(peer, text):
    """Как человек в мессенджере: одно предложение = одно сообщение, без точки в конце и кавычек,
    перед каждым «печатает» 5–10 с (короткое 5, длинное до 10)."""
    u = CTX.get("user")
    if not u:
        return None
    import autoreply
    last = None
    async with autoreply.peer_lock(peer):  # ответ и догоняющее не перемешиваются, всё идёт по очереди
        for part in autoreply._parts(text):
            secs = max(5.0, min(10.0, 5.0 + len(part) / 12) + random.uniform(-0.4, 0.4))
            try:
                if time.time() - TYPING.get(peer, 0) < 6:  # человек печатает: подождём, не перебиваем
                    await wait_quiet(peer, f"tg:{peer}", max_wait=60)
                async with u.action(peer, "typing"):
                    await asyncio.sleep(secs + autoreply.gap_left(peer))
                m = await u.send_message(peer, part)
                autoreply.mark_sent(peer)
                S["sent"].append(f"tg:{m.id}")
                last = m.id
            except Exception as e:
                log.warning("tg send: %s", e)
                break
    return last


async def tg_send(peer, text):
    u = CTX.get("user")
    if not u:
        return None
    try:
        await asyncio.sleep(random.uniform(2, 3))
        await u.send_read_acknowledge(peer)
    except Exception:
        pass
    return await tg_human(peer, text)


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
        if cv.get("asked_src") and cv.get("source") == "напрямую" and time.time() - cv["asked_src"] < 86400:
            low = text.lower()
            for k, w in (("инст", "instagram"), ("instagram", "instagram"), ("тредс", "threads"), ("threads", "threads"), ("сайт", "с сайта"),
                         ("гугл", "поиск"), ("google", "поиск"), ("яндекс", "поиск"), ("поиск", "поиск"), ("канал", "telegram-канал"),
                         ("чат", "telegram-чат"), ("знаком", "рекомендация"), ("друг", "рекомендация"), ("посовет", "рекомендация"),
                         ("письм", "письма"), ("почт", "письма"), ("дзен", "дзен"), ("youtube", "youtube"), ("ютуб", "youtube")):
                if k in low:
                    st = S.setdefault("src_stats", {}).setdefault(time.strftime("%Y-%m-%d"), {})
                    st["напрямую"] = max(0, st.get("напрямую", 0) - 1)
                    st[w] = st.get(w, 0) + 1
                    cv["source"] = w
                    try:
                        json.dump(S["src_stats"], open(os.path.join(BASE, "consult_sources.json"), "w"), ensure_ascii=False)
                    except Exception:
                        pass
                    await tell(cid, f"📍 @{snd.username or snd.id} нашёл нас: {w}")
                    break
        if not cv.get("source"):  # откуда пришёл: по фразе из ссылки «Бесплатная консультация» (/c/<источник>)
            low = text.lower()
            for k, w in (("сайт", "с сайта"), ("instagram", "instagram"), ("threads", "threads"), ("канал", "telegram-канал"),
                         ("письм", "письма"), ("дзен", "дзен"), ("бот", "бота-проверки")):
                if "пишу" in low and k in low:
                    cv["source"] = w
                    break
            cv.setdefault("source", "напрямую")
            day = time.strftime("%Y-%m-%d")
            st = S.setdefault("src_stats", {}).setdefault(day, {})
            st[cv["source"]] = st.get(cv["source"], 0) + 1
            try:
                json.dump(S["src_stats"], open(os.path.join(BASE, "consult_sources.json"), "w"), ensure_ascii=False)
            except Exception:
                pass
            if "консультац" in low:
                await tell(cid, f"🆓 Запрос на бесплатную консультацию от @{snd.username or snd.id} (источник: {cv['source']})")
        cv["history"].append({"role": "user", "text": text, "ts": time.time()})
        cv["history"] = cv["history"][-60:]
        if cv.get("human") or cv.get("muted"):
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
