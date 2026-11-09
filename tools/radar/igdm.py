"""Директ Instagram @ronin.dubai (бывший @fortex__uae): ассистент отвечает по базе знаний, задаёт вопросы владельцу и передаёт готовых лидов.

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


# ===== Созвоны (правило Александра 08.11) =====
# Клиент назвал день -> Александр в боте даёт время -> клиент согласен (call_ok) ->
# событие в Google Календарь (веб-хук Apps Script, файл gcal_hook), встреча в Zoom (файл zoom_creds, если есть),
# за 40 минут напоминаем клиенту, за 5 минут шлём ссылку клиенту и в бот.
from datetime import timezone, timedelta
DXB = timezone(timedelta(hours=4))
WD = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
ZOOM_RE = re.compile(r"https?://\S*zoom\.\S+")


def call_when(ts):
    d = datetime.fromtimestamp(ts, DXB)
    return f"{WD[d.weekday()]} {d:%d.%m} в {d:%H:%M} по Дубаю"


async def zoom_create(topic, ts, minutes):
    """Встреча в Zoom через Server-to-Server OAuth. Нет ключей или ошибка -> None."""
    cr = re.findall(r"[A-Za-z0-9_\-]{15,}", secret("zoom_creds"))
    if len(cr) < 3:
        CTX["zoom_err"] = f"в сохранённых ключах {len(cr)} значения вместо 3, отправь /igdm zoom ещё раз"
        return None
    cr = cr[:3]
    acc, cid_, sec = cr
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            t = await c.post(f"https://zoom.us/oauth/token?grant_type=account_credentials&account_id={acc}", auth=(cid_, sec))
            tok = t.json().get("access_token")
            if not tok:
                CTX["zoom_err"] = f"token {t.status_code}: {t.text[:200]}"; log.warning("zoom %s", CTX["zoom_err"]); return None
            hd = {"Authorization": f"Bearer {tok}"}
            uid = "me"
            try:  # Server-to-Server OAuth иногда не принимает "me": берём владельца аккаунта
                u = (await c.get("https://api.zoom.us/v2/users", headers=hd, params={"page_size": 1})).json()
                if not u.get("users"):
                    log.warning("zoom users %s", str(u)[:200])
                uid = ((u.get("users") or [{}])[0].get("id")) or "me"
            except Exception:
                pass
            r = await c.post(f"https://api.zoom.us/v2/users/{uid}/meetings", headers=hd,
                             json={"topic": topic, "type": 2, "duration": minutes, "timezone": "Asia/Dubai",
                                   "start_time": datetime.fromtimestamp(ts, DXB).strftime("%Y-%m-%dT%H:%M:%S"),
                                   "settings": {"join_before_host": True, "waiting_room": False}})
            j = r.json()
            if not j.get("join_url"):
                CTX["zoom_err"] = f"meeting {r.status_code}: {str(j)[:200]}"; log.warning("zoom %s", CTX["zoom_err"])
            return j.get("join_url")
    except Exception as e:
        CTX["zoom_err"] = f"exception: {str(e)[:200]}"; log.warning("zoom: %s", e)
        return None


async def gcal_put(cv):
    """Событие в Google Календарь владельца через веб-хук Apps Script. True = поставлено."""
    hook = secret("gcal_hook")
    call = cv.get("call") or {}
    if not hook or not call.get("at"):
        return False
    who = cv.get("name") or ""
    tgl = f"https://t.me/{cv.get('username')}" if cv.get("username") and not str(cv.get("username")).isdigit() else ""
    body = {"id": call.get("gcal_id") or "",
            "title": f"Созвон: {cv.get('services') or 'консультация'}, {who} @{cv.get('username')}".replace(",  @", ", @"),
            "start": datetime.fromtimestamp(call["at"], DXB).isoformat(),
            "end": datetime.fromtimestamp(call["at"] + call.get("min", 60) * 60, DXB).isoformat(),
            "description": "\n".join(x for x in [cv.get("summary") or "", tgl, call.get("link") or ""] if x)}
    try:
        async with httpx.AsyncClient(timeout=40, follow_redirects=True) as c:
            r = await c.post(hook, content=json.dumps(body), headers={"Content-Type": "text/plain"})
            j = json.loads(r.text) if r.text.strip().startswith("{") else {}
            if j.get("id"):
                call["gcal_id"] = j["id"]
                return True
            log.warning("gcal %s %s", r.status_code, r.text[:200])
    except Exception as e:
        log.warning("gcal: %s", e)
    return False


async def say(cv, text):
    """Сообщение клиенту в его канале (в Telegram с человеческой скоростью)."""
    uid = cv["uid"]
    ok = await (tg_human(int(uid[3:]), text) if str(uid).startswith("tg:") else send(uid, text))
    if ok:
        cv["history"].append({"role": "bot", "text": text, "ts": time.time()})
        save()
    return ok


async def call_tick(now):
    """Напоминания по подтверждённым созвонам: за 40 минут клиенту, за 5 минут ссылка клиенту и в бот."""
    for cid, cv in list(S.get("convs", {}).items()):
        call = cv.get("call") or {}
        if call.get("status") != "confirmed" or not call.get("at"):
            continue
        at = call["at"]
        if now > at + 3600:
            call["status"] = "done"; save(); continue
        if not call.get("link") and not call.get("zoom_tried") and secret("zoom_creds") and now < at:
            # созвон подтвердили до подключения Zoom: создаём встречу заранее, ссылка уйдёт за 5 минут
            call["zoom_tried"] = True
            call["link"] = await zoom_create(f"Fortex UAE: {cv.get('name') or cv.get('username')}", at, call.get("min", 60))
            save()
            if call.get("link"):
                await tell(cid, f"📞 Встреча в Zoom создана: @{html.escape(str(cv.get('username')))}, {html.escape(call_when(at))}\n{html.escape(call['link'])}\n\nКлиенту отправлю за 5 минут до начала.", is_html=True)
            else:
                await tell(cid, f"🔴 <b>Нужно твоё внимание</b>\n\nZoom не создал встречу. Ответ Zoom: <code>{html.escape(str(CTX.get('zoom_err', '?')))}</code>\n\nПерешли это Claude. Ссылку на созвон можно прислать реплаем.", is_html=True)
        if not call.get("r40") and at - 40 * 60 <= now < at - 10 * 60:
            call["r40"] = True; save()
            asyncio.get_event_loop().create_task(say(cv, random.choice([
                "Добрый день! Через 40 минут созваниваемся, всё в силе?",
                "Добрый день! Напоминаю, через 40 минут созвон в Zoom. Всё в силе?"])))
        if not call.get("r5") and at - 5 * 60 <= now < at + 15 * 60:
            call["r5"] = True; save()
            u = html.escape(str(cv.get("username")))
            if call.get("link"):
                asyncio.get_event_loop().create_task(say(cv, f"Вот ссылка на Zoom, подключайтесь: {call['link']}"))
                await tell(cid, f"📞 <b>Через 5 минут созвон</b> с @{u}\n\n{html.escape(call['link'])}", is_html=True)
            else:
                await tell(cid, f"🔴 <b>Нужно твоё внимание</b>\n\n📞 <b>Через 5 минут созвон</b> с @{u}, а ссылки на Zoom нет.\n"
                                f"Пришли ссылку реплаем, Алексей сразу отправит клиенту.", is_html=True)


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


SYSTEM = """Ты сотрудник отдела работы с клиентами Fortex UAE (Дубай). Ты Алексей Ронин. Отвечаешь в директе Instagram @ronin.dubai (бывший @fortex__uae, с 08.11 аккаунт от лица Алексея, с его фото) от первого лица («я», «у нас с командой»), как в Telegram.
Цель: понять задачу человека, предложить подходящую услугу и довести до передачи руководителю с контактом.
Продавай с пользой: если клиенту реально нужно несколько вещей (компания + виза + счёт + карта), предложи комплекс. Делай упор на корпоративные счета, рабочую визу с Emirates ID и карту Emirates NBD Skywards Infinite. Virtual Work предлагай, если нужен просто статус резидента.

Стиль:
- как живой человек в мессенджере: 1–3 коротких предложения, на «ты» (решение Александра 09.11: пишем клиентам на «ты», даже если в примерах базы знаний «вы»), по имени, если оно известно;
- один вопрос за раз, без списков (если человек сам не просит перечислить);
- «ВСЕГДА ГОВОРИ ДА»: на то, что человек говорит, реагируй позитивно и с согласием: «Да, конечно», «Да, хорошо», «Окей, сделаем», «Да, это решаемо», «Понял, принято». Не спорь и не начинай с «нет» или «но»; если что-то невозможно, сначала согласись с целью человека, потом предложи, как сделать иначе. Подтверждения каждый раз разные, не повторяй одно и то же;
- НЕ ДОПРОС: вопросы не подряд в каждом сообщении. Часто просто подтверди, что услышал, и добавь что-то полезное: «Понял», «Принято», «Ага, ясно», «Окей, тогда так», «Тут понятно». Примерно через раз сообщение без вопроса;
- перед каждым ответом перечитай всю переписку: никогда не спрашивай то, что уже спрашивал или на что человек уже ответил (даже другими словами). Если ответ был неполный, уточни по-другому, а не тем же вопросом;
- без канцелярита, без длинных тире (— и –), без слова «профиль», без выражения «по опыту»;
- смайлик «:)» или эмодзи очень редко: примерно одно сообщение из 7–10, не чаще. Обычно без них;
- первое сообщение: короткое приветствие и вопрос, чем помочь, или сразу ответ на вопрос.
- ДИАЛОГ, А НЕ ПРОСТЫНЯ (правило Александра 08.11): отвечай только на то, что спросили (спросили про личный счёт: про корпоративный ни слова), максимум 2–3 коротких предложения за раз, потом один вопрос и ждём ответа. Не вываливай всё сразу: пусть клиент сам спрашивает дальше.
- НЕ ОТКЛАДЫВАЙ ОТВЕТ (правило Александра 07.11): никогда не пиши «сейчас распишу», «сейчас напишу», «сейчас расскажу», «напишу по этапам», «чуть позже отвечу» вместо ответа. Если человек просит расписать по этапам, подробнее, что входит, какие сроки, отвечай сразу в этом же сообщении, по делу, с этапами и сроками из базы знаний. Если в базе нет ответа, это ask_owner.

Факты, цены и кейсы бери ТОЛЬКО из базы знаний ниже. Цены пиши «от X». Никаких «100% откроем».
Помогаем честно подготовить документы. Никогда не помогаем скрыть источник средств или обойти проверку: такие запросы и людей в санкционных списках вежливо отклоняй.
Не придумывай имена сотрудников и факты о компании.

Квалификация (выясняй постепенно, по ходу разговора): паспорт какой страны; есть ли компания в ОАЭ и чем занимается; есть ли Emirates ID; были ли отказы или закрытия счетов; какой банк нужен и зачем.

НЕ ВЫДУМЫВАЙ (правило Александра 03.11): любые цифры, проценты (в том числе доли оплаты, предоплаты, этапов), сроки, условия, документы и обещания только из базы знаний дословно по смыслу. Про встречу говори только «встретимся, всё расскажем и покажем»; не обещай принести лицензии, договоры или другие документы и не называй место. Если в базе нет точного ответа, это ask_owner, а не догадка.
Когда звать владельца (action "ask_owner"): ответа нет в базе знаний, вопрос нестандартный (конкретный банк под необычную деятельность, юридические тонкости, скидки, точный срок по сложному кейсу). Тогда в reply коротко: что уточнишь у коллег и вернёшься (каждый раз своими словами), а в owner_question сам вопрос клиента с контекстом.

СОЗВОН (правило Александра 08.11): если человек готов созвониться или соглашается («хорошо», «интересно», «давайте созвонимся»), сам предложи Zoom: так сразу можно задать все вопросы, понятнее и быстрее. И спроси, в какой день ему удобнее (каждый раз своими словами, коротко). Время и день сам не назначай, ссылку на Zoom не обещай, контакт для созвона не проси. action "none". Когда человек назвал день или дни (и время, если назвал), action "call", в call_days его слова про день и время, а в reply коротко: сейчас уточню время и подтвержу. Дальше ждём ответ Александра, он придёт как ответ коллеги. Когда мы предложили клиенту время созвона и он согласен, action "call_ok" и короткое подтверждение: ссылку на Zoom пришлёшь перед началом.
Когда передавать (action "handoff"): человек готов двигаться (спрашивает, как начать, просит точную цену под себя, соглашается начать оформление) или просит живого человека. Сначала попроси Telegram или телефон. Как только контакт есть, action "handoff", а в reply: что подключаешь руководителя (руководство), он напишет лично с аккаунта компании @FortexGlobal (там логотип, это наш официальный аккаунт), каждый раз своими словами. Слово «менеджер» не используй.

Вопросы не по делу (в Telegram про себя можно немного рассказать, см. правило канала ниже; погода, политика, кто основатель, где офис, сколько сотрудников, шутки, просто болтовня): не отвечай по существу и ничего не выдумывай. Вежливо и легко уйди от темы (можно с лёгким юмором), а следующей фразой верни разговор к задаче клиента или к нашему предложению. Например: «Про погоду лучше спросить пляж :) Давайте лучше про вашу задачу: счёт нужен для компании или личный?» или «Это не ко мне... А вот со счётом в ОАЭ помогу. Компания у вас уже есть?». Если клиент так и не говорит о задаче, предложи самое ходовое: корпоративный счёт, рабочую визу с Emirates ID или карту Skywards Infinite, одной фразой. Не дави и не повторяй одно и то же предложение дважды подряд.

Если сообщение непонятное (обрывок, опечатки, неясно, что нужно): коротко и по-дружески переспроси, можно со смайликом. Например: «Не совсем понял :) Что вы хотели узнать?» или «Здравствуйте! Подскажите, что вас интересует?».
КОГДА ОСТАНОВИТЬСЯ: если разговор по сути завершён (договорились о следующем шаге, мы уже попрощались или подтвердили, а клиент пишет «ок», «хорошо», «спасибо», «понял», «напишу», «договорились»), не отвечай текстом на каждое такое сообщение. Верни action "react" с пустым reply и reaction "👍" (или "🤝", если о чём-то договорились). Мы сами напомним о себе позже догоняющим сообщением. Отвечай текстом, только если в сообщении есть новый вопрос или новая информация.
ЭМОДЗИ: обычно без них. Но когда уместно, особенно в конце, когда договорились («Да, так и сделаем», «Договорились»), можно поставить 👍 или 🤝 в конце сообщения. Не чаще одного раза на несколько сообщений.
Если человек второй раз подряд уходит не в нашу тему или явно не нуждается в наших услугах: вежливо закрой разговор одной фразой («Понял, спасибо! Если понадобится счёт или виза в ОАЭ, пишите :)») и верни action "close". Если сообщение бессмысленное, спам, реклама чужих услуг, грубость, похоже на мошенника (обнал, «серые» схемы, просьбы скрыть деньги, подозрительные ссылки, предложения «заработка») или человек раз за разом пишет не по теме: ничего не пиши, верни action "ignore" и пустой reply. После этого мы с ним больше не общаемся.
Не в каждом сообщении задавай вопрос: если клиент сам ведёт разговор, иногда просто ответь по делу.

ПАРТНЁРЫ. Иногда пишет не клиент, а потенциальный партнёр: риелтор, юрист, бухгалтер, агентство, банкир, консультант, у которого есть свои клиенты («у меня есть клиенты», «хотим сотрудничать», «вы работаете с агентами?», «какие условия для партнёров»). Партнёр так же важен, как клиент: его надо расположить к себе и заинтересовать. С ним говори как с коллегой, не продавай услугу ему лично:
- тепло, на равных: «Здравствуйте, коллега!», «Рад знакомству», «Отличная идея, давайте обсудим»;
- уточни, кто он: чем занимается, какие у него клиенты и с какими задачами (по одному вопросу, не допрос);
- объясни, что мы работаем с партнёрами и у нас есть партнёрские условия: он приводит клиентов со счетами, визами, компаниями, переводами, мы делаем всю работу под ключ, ему вознаграждение;
- ответь на его вопросы по нашим услугам и процессу по базе знаний, покажи, что с нами просто и надёжно;
- конкретные условия (процент, выплаты) индивидуальные: скажи, что по условиям свяжешь его с руководителем, который напишет с аккаунта компании @FortexGlobal;
- когда он готов обсуждать условия или описал предложение, верни action "partner": в reply, что подключаешь руководителя для обсуждения условий; в summary кратко: кто он, чем занимается, страна, какие клиенты и услуги, что предлагает.
Не обещай процент или конкретные цифры вознаграждения.

ОСОБЫЕ СЛУЧАИ (action "alert"): пишут правоохранительные или госорганы, полиция, суд, налоговая, юристы с претензией, угрозы, шантаж, журналисты с расследованием, требования удалить данные, что-то опасное или экстремальное. Ничего не обещай и не обсуждай по существу, никаких фактов о компании и клиентах. В reply одна нейтральная вежливая фраза: «Понял, передам руководителю, с вами свяжутся». В summary кратко, кто пишет и что хочет.

Если спрашивают, бот ли ты или живой ли человек, отвечай честно: ты ассистент команды Fortex, отвечаешь быстро и можешь подключить руководителя.

ПАУЗА НА РАСЧЁТ (правило Александра 08.11): если для ответа нужно что-то посчитать (ипотека, платёж, расходы) или уточнить у коллег, а клиент согласился («да, давайте», «посчитайте»), не выдавай расчёт мгновенно. В reply короткая фраза «Сейчас прикину, пару минут» (или «Уточню и вернусь»), а сам ответ положи в поле "then" (2–3 коротких предложения с цифрами-ориентирами и вопросом), и "then_min": 3–5. Он уйдёт через эти минуты. Для обычных вопросов поля then не используй.

Ответь строго JSON без пояснений:
{"reply": "<текст клиенту>", "then": "<только при паузе на расчёт>", "then_min": 0, "action": "none|ask_owner|call|call_ok|handoff|partner|alert|close|ignore|react", "call_days": "<только для call: какие дни и время назвал клиент>", "reaction": "<👍 или 🤝, только для react>", "owner_question": "<если ask_owner>", "contact": "<Telegram или телефон, если клиент дал>", "name": "<имя клиента, если известно>", "summary": "<кратко: кто, задача, что предложили>", "services": "<какие услуги интересны>"}

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


FOLLOWUP = """Ты Алексей, сотрудник Fortex UAE в личных сообщениях (Telegram или Instagram), пишешь от первого лица, на «ты», без длинных тире, без слова «профиль», без кавычек-ёлочек вокруг своих фраз.
Клиент перестал отвечать. Задача: вернуть его в диалог ПОЛЬЗОЙ ПО ЕГО ТЕМЕ, а не вопросом «надумали?».

ГЛАВНОЕ ПРАВИЛО ДОЖИМА (Александр, 08.11):
- Не спрашивай «если интересно, напишу?», «актуально?», «вопрос уже решили?», «надумали?». Не предлагай рассказать, а сразу расскажи.
- Возьми из переписки, что человеку нужно (его задача, вопрос, ситуация), и из базы знаний то, что ему реально полезно и интересно: этапы и сроки, что входит, варианты (например, разные кредитки Emirates NBD, с депозитом и без), цены, нюансы, которые он мог не знать.
- Если он спрашивал «распиши по этапам», «что входит», «какие сроки», а мы не ответили, догоняющее это и есть полный ответ на его вопрос.
- Пиши ОДНИМ структурированным сообщением: 2–3 коротких абзаца по 1–3 предложения, между абзацами пустая строка. Можно короткий список этапов (1., 2., 3.). Не простыня: всего до 700 знаков.
- Обращайся к его кейсу: «Вы писали, что…», «Под вашу задачу…».
- В конце один простой вопрос по делу, на который легко ответить (например, про паспорт, сроки, когда планирует быть в Дубае). Не «интересно?».
- Только факты из базы знаний, ничего не выдумывай.

Номер догоняющего: {n} из 3.
- Первое (через 15 минут, человек прочитал и молчит): если мы что-то не дописали или пообещали, это полный ответ по правилу выше (block true). Если всё ответили, то одна короткая лёгкая фраза по теме (block false).
- Второе и третье: всегда полезное сообщение по его теме по правилу выше (block true), каждый раз с новым углом и другой пользой, не повторяй прошлые догоняющие. Третье последнее и спокойное: польза плюс в конце мягко, что будем рады помочь, когда будет актуально.
- Если с последнего сообщения прошло меньше 12 часов, не здоровайся заново. Если больше суток и мы нормально общались, можно тепло по имени («Дмитрий, добрый день!») и сразу по делу.
Если по переписке видно, что клиент закончил разговор, отказался, сказал «спасибо, не надо» или попрощался, не пиши: верни skip true.
Ответь JSON: {{"skip": false, "block": true, "reply": "<текст, абзацы через пустую строку>"}}"""


async def followup(cid):
    cv = S["convs"][cid]
    stage = cv.get("fu", 0)
    cv["fu_at"] = 0
    tg = str(cv.get("uid", "")).startswith("tg:")
    if (cv.get("call") or {}).get("status") == "confirmed":
        save(); return  # созвон назначен: не дожимаем, только напоминания
    if cv.get("human") or cv.get("lead_sent") or cv.get("pending_q") or (not tg and time.time() - (cv.get("last_user_ts") or 0) > WINDOW):
        save(); return
    if tg and stage == 0 and not cv.get("fu_unread_waited"):
        # правило Александра 08.11: через 15 минут догоняем, только если человек уже ПРОЧИТАЛ наше сообщение.
        # Не прочитал: он просто отошёл, ждём 2–3 часа (не поздно вечером), потом пишем.
        try:
            from telethon.tl.functions.messages import GetPeerDialogsRequest
            u = CTX.get("user")
            peer = int(cv["uid"][3:])
            last_out = 0
            async for m in u.iter_messages(peer, limit=15):
                if m.out:
                    last_out = m.id
                    break
            r = await u(GetPeerDialogsRequest(peers=[peer]))
            read_upto = r.dialogs[0].read_outbox_max_id if r.dialogs else 0
            if last_out and read_upto < last_out:
                at = time.time() + random.randint(2 * 3600, 3 * 3600)
                h = time.gmtime(at + 4 * 3600).tm_hour
                if h >= 21 or h < QUIET[1]:  # поздно вечером не пишем: переносим на утро
                    at += ((QUIET[1] + 24 - h) % 24) * 3600 + random.randint(1800, 5400)
                cv["fu_unread_waited"] = True
                cv["fu"], cv["fu_at"] = stage, at
                save()
                return
        except Exception as e:
            log.warning("tg read check: %s", e)
    cv.pop("fu_unread_waited", None)
    last_ts = max([h.get("ts") or 0 for h in cv.get("history", [])] or [0])
    hrs = (time.time() - last_ts) / 3600 if last_ts else 99
    res = await llm(FOLLOWUP.format(n=stage + 1) + "\n\nБАЗА ЗНАНИЙ:\n" + kb(),
                    f"Переписка:\n{transcript(cv)}\n\nС последнего сообщения прошло {hrs:.1f} ч"
                    + (" (меньше 12 ч: не здоровайся)." if hrs < 12 else ".") + "\nНапиши догоняющее сообщение.")
    if res and res.get("reply") and DEFER_RE.search(res["reply"]):
        res = await llm(FOLLOWUP.format(n=stage + 1) + "\n\nБАЗА ЗНАНИЙ:\n" + kb(),
                        f"Переписка:\n{transcript(cv)}\n\nТвой вариант «{res['reply']}» опять обещает написать позже. Дай сам ответ сейчас, по делу, без приветствия.") or res
    if not res or res.get("skip") or not res.get("reply"):
        save(); return
    block = bool(res.get("block")) or stage >= 1
    text = clean(res["reply"])
    if block and tg:
        sent = await tg_block(int(cv["uid"][3:]), text)  # одним сообщением с абзацами, «печатает» долго, как человек
    else:
        sent = await send(cv["uid"], text)
    if sent:
        cv["history"].append({"role": "bot", "text": text, "ts": time.time(), "fu": stage + 1})
        schedule_followup(cv, stage + 1)
    save()


# длина ответа чередуется, чтобы сообщения не были одинаковыми
LENGTHS = {"short": "очень коротко, 2–8 слов, одна фраза (например «Да, откроем.» или «А паспорт какой?»)",
           "medium": "одно-два коротких предложения, до 140 знаков",
           "long": "два-три предложения, до 260 знаков, только если правда нужно объяснить",
           "detail": "человек просит подробнее: ответь сразу по сути, 2–3 коротких предложения (главное: первый шаг, срок, цена из базы знаний), остальное расскажешь, когда он ответит; каждое предложение уйдёт отдельным сообщением; не обещай расписать позже"}


DETAIL_RE = re.compile(r"распиш|поэтап|по этап|подробн|что входит|что включ|как это работает|какие сроки|в какие сроки|сколько времени|расскаж|объясни|по шагам|опиши", re.I)
DEFER_RE = re.compile(r"(сейчас|щас|скоро|чуть позже|позже)\s+(распишу|напишу|расскажу|отвечу|пришлю|скину)|напишу по этапам|распишу", re.I)


def pick_length(cv):
    last = next((h.get("text", "") for h in reversed(cv.get("history", [])) if h.get("role") == "user"), "")
    if DETAIL_RE.search(last or ""):
        cv["last_len"] = "detail"
        return "detail"
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
            await u.send_read_acknowledge(peer)  # уже прочитано через 3 с в tg_read_soon, здесь на всякий случай
        except Exception as e:
            log.warning("tg read: %s", e)
    extra = ""
    if cv.get("pending_q"):
        extra = f"\n\nСейчас мы ждём ответ коллег на вопрос: «{cv['pending_q']}». Не обещай ответ ещё раз, но можешь продолжать разговор по другим темам."
    call = cv.get("call") or {}
    if call.get("status") == "proposed":
        extra += (f"\n\nМы предложили клиенту созвон в Zoom: {call_when(call['at'])}. Если клиент согласен на это время, action call_ok и короткое подтверждение "
                  "(что ссылку на Zoom пришлёшь перед началом). Если просит другой день или время, action call и в call_days его вариант.")
    elif call.get("status") == "confirmed" and call.get("at", 0) > time.time() - 3600:
        extra += (f"\n\nСозвон в Zoom уже подтверждён: {call_when(call['at'])}. Ссылку пришлём за 5 минут до начала. "
                  "Если клиент подтверждает, что всё в силе, ответь коротко. Если просит перенести, action call и в call_days новый вариант.")
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
    if res and res.get("reply") and not res.get("then") and DEFER_RE.search(res["reply"]) and len(res["reply"]) < 120:
        # «сейчас распишу» без самого ответа: просим ответить сразу (правило Александра 07.11)
        res = await llm(SYSTEM + kb(), f"Клиент: @{cv.get('username')}\nПереписка:\n{transcript(cv)}{extra}\n\n"
                                       f"Твой вариант «{res['reply']}» только обещает ответ. Дай сам ответ сейчас: {LENGTHS['detail']}.\n"
                                       f"Напиши следующее сообщение клиенту.") or res
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
    if res.get("then") and is_tg:  # «ушли посчитать»: вернёмся с ответом через 3–5 минут
        mins = max(2.0, min(6.0, float(res.get("then_min") or 4)))
        cv["then_text"] = tame_emoji(clean(res["then"]), cv)
        cv["then_at"] = time.time() + mins * 60 + random.randint(-20, 40)
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
    elif act == "call":
        days = str(res.get("call_days") or "день не уточнил")
        cv["pending_q"] = f"Клиент готов созвониться в Zoom ({days}). Какое время подтвердить?"
        cv["call_q"] = True
        await tell(cid, f"🔴 <b>Нужно твоё внимание</b>\n\n📞 <b>Готов на созвон в Zoom:</b> @{html.escape(str(cv.get('username')))}\n"
                        f"<b>Когда удобно:</b> {html.escape(days)}\n"
                        f"<b>Суть:</b> {html.escape(str(cv.get('summary') or ''))}\n\n"
                        f"<b>Какое время подтвердить?</b> Ответь реплаем, Алексей передаст клиенту.\n\n"
                        f"<b>━━━ Последние сообщения ━━━</b>\n\n{transcript_html(cv, 6, 1500)}", is_html=True)
    elif act == "call_ok" and (cv.get("call") or {}).get("at"):
        call = cv["call"]
        call["status"] = "confirmed"
        call["r40"] = call["r5"] = False
        if not call.get("link"):
            call["link"] = await zoom_create(f"Fortex UAE: {cv.get('name') or cv.get('username')}", call["at"], call.get("min", 60))
        ok = await gcal_put(cv)
        save()
        await tell(cid, f"✅ <b>Созвон подтверждён:</b> @{html.escape(str(cv.get('username')))}\n"
                        f"<b>Когда:</b> {html.escape(call_when(call['at']))}, {call.get('min', 60)} мин\n"
                        f"<b>Календарь:</b> {'поставил' if ok else 'не поставил (нет подключения), поставь сам'}\n"
                        f"<b>Zoom:</b> {html.escape(call['link']) if call.get('link') else 'ссылки нет, пришли реплаем до начала'}\n\n"
                        f"Клиенту напомню за 40 минут, ссылку отправлю за 5 минут.", is_html=True)
    elif cv.get("lead_sent"):
        pass  # клиент уже передан: ассистент отвечает сам, Александра не дёргаем на каждое сообщение
    elif act == "partner":
        cv["lead_sent"] = True
        cv["partner"] = True
        await tell(cid,
            f"🤝 <b>Партнёр из {'Telegram' if is_tg else 'Instagram'}:</b> @{html.escape(str(cv.get('username')))}\n\n"
            f"<b>Имя:</b> {html.escape(str(cv.get('name') or '?'))}\n"
            f"<b>Суть:</b> {html.escape(str(cv.get('summary') or ''))}\n\n"
            f"<b>━━━ Переписка ━━━</b>\n\n{transcript_html(cv)}\n\n"
            f"<b>Ассистент сказал, что команда обсудит и вернётся.</b> Ответь ему сам или реплаем сюда.", is_html=True)
    elif act == "alert":
        cv["lead_sent"] = True
        cv["human"] = True  # дальше ассистент молчит, ведёт Александр
        await tell(cid,
            f"🚨 <b>Особый случай в {'Telegram' if is_tg else 'Instagram'}:</b> @{html.escape(str(cv.get('username')))}\n"
            f"<b>Суть:</b> {html.escape(str(cv.get('summary') or ''))}\n\n"
            f"<b>━━━ Переписка ━━━</b>\n\n{transcript_html(cv)}\n\n"
            f"<b>Ассистент ответил нейтрально и замолчал.</b> Дальше реши сам.", is_html=True)
    elif act == "handoff":
        cv["lead_sent"] = True
        await tell(cid,
            f"🔥 <b>Готовый лид из {'Telegram' if is_tg else 'Instagram'}:</b> @{html.escape(str(cv.get('username')))}\n"
            + (f"Открыть переписку: https://t.me/{html.escape(str(cv.get('username')))}\n" if is_tg and cv.get('username') and not str(cv.get('username')).isdigit() else "")
            + (f"Источник: {html.escape(str(cv.get('source')))}\n" if cv.get('source') else "") + "\n"
            + f"<b>Имя:</b> {html.escape(str(cv.get('name') or '?'))}\n"
            + f"<b>Контакт:</b> {html.escape(str(cv.get('contact') or 'не дал, пиши в директ'))}\n"
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
                if not CTX.get("resumed"):
                    # после перезапуска (обновление ассистента) не бросаем людей, которым не успели ответить (08.11)
                    CTX["resumed"] = True
                    for cid, cv in list(S["convs"].items()):
                        # разово 08.11 17:37: дожим Дмитрия по новому правилу (Александр попросил отправить)
                        if ("dmitriy_fu" not in S.setdefault("oneoff", []) and str(cv.get("uid", "")).startswith("tg:")
                                and any("Что включает поэтапно" in (x.get("text") or "") for x in (cv.get("history") or []))):
                            S["oneoff"].append("dmitriy_fu")
                            cv["human"] = False
                            cv["muted"] = False
                            save()
                            txt = ("Дмитрий, коротко по пакету:\n\n"
                                   "1. Зарплатный счёт в Emirates NBD\n"
                                   "2. Кредитка Skywards Infinite без депозита: лимит, мили, бизнес-залы\n"
                                   "3. Дебетовая карта в подарок\n"
                                   "Всё вместе около 3 рабочих дней, пакет 5 000 AED\n\n"
                                   "Банкир встречается с вами в Дубае: подпись и пара вопросов. Через 1–2 дня приходит welcome letter с номером счёта\n\n"
                                   "У вас Emirates ID уже есть?")
                            async def _dfu(cv=cv, cid=cid, txt=txt):
                                await asyncio.sleep(random.randint(10, 30))
                                if await tg_block(int(cv["uid"][3:]), txt):
                                    cv["history"].append({"role": "bot", "text": txt, "ts": time.time(), "fu": 4})
                                    cv["fu_at"] = 0
                                    save()
                                    await tell(cid, f"Отправил дожим @{cv.get('username')}:\n\n{txt}")
                            asyncio.get_event_loop().create_task(_dfu())
                            continue
                        # разово 08.11 17:49: Марина подтвердила 12:00 (09.11): созвон подтверждён, напоминания 11:20 и 11:55
                        if ("marina_call_12" not in S.setdefault("oneoff", [])
                                and any((x.get("text") or "").strip() == "Окей, тогда так" for x in (cv.get("history") or []))):
                            S["oneoff"] += ["marina_call_12", "marina_call_obj"]
                            cv["call"] = {"at": datetime(2026, 11, 9, 12, 0, tzinfo=DXB).timestamp(), "min": 60,
                                          "status": "confirmed", "link": (cv.get("call") or {}).get("link"),
                                          "gcal_id": "cjcagsdedip8fbtak8e3mo1cro", "r40": False, "r5": False}
                            cv["call_q"] = False
                            cv["pending_q"] = None
                            cv["fu_at"] = 0
                            save()
                        # разово 08.11: созвон Марины (09.11 10:00) в новую логику: подтвердит -> календарь и напоминания
                        if ("marina_call_obj" not in S.setdefault("oneoff", []) and "marina_call" in S["oneoff"]
                                and any((x.get("text") or "").strip() == "Окей, тогда так" for x in (cv.get("history") or []))):
                            S["oneoff"].append("marina_call_obj")
                            if not cv.get("call"):
                                cv["call"] = {"at": datetime(2026, 11, 9, 10, 0, tzinfo=DXB).timestamp(), "min": 60, "status": "proposed", "link": None}
                            save()
                        # разово 08.11 15:08: Александр просит предложить Марине созвон завтра в 10:00
                        hz = cv.get("history") or []
                        if ("marina_call" not in S.setdefault("oneoff", []) and str(cv.get("uid", "")).startswith("tg:")
                                and any((x.get("text") or "").strip() == "Окей, тогда так" for x in hz)):
                            S["oneoff"].append("marina_call")
                            save()
                            msg = "Хорошо, давайте. Завтра в 10 утра по Дубаю удобно будет созвониться в Zoom?"
                            async def _call(cv=cv, cid=cid, msg=msg):
                                await asyncio.sleep(random.randint(10, 25))
                                if await tg_human(int(cv["uid"][3:]), msg):
                                    cv["history"].append({"role": "bot", "text": msg, "ts": time.time()})
                                    cv["pending_q"] = None
                                    schedule_followup(cv, 0)
                                    save()
                                    await tell(cid, f"Предложил @{cv.get('username')} созвон: {msg}")
                            asyncio.get_event_loop().create_task(_call())
                            continue
                        # разово 08.11: ответ Александра на вопрос Марины (part-time во второй компании)
                        h1 = cv.get("history") or []
                        if (cv.get("pending_q") and not CTX.get("marina_pt")
                                and any((x.get("text") or "").strip() == "Окей, тогда так" for x in h1)):
                            CTX["marina_pt"] = True
                            ans = ("Да, так можно: основным работодателем будет наша компания, а во второй компании "
                                   "вы можете быть оформлены на part-time и тоже получать там зарплату")
                            async def _pt(cv=cv, cid=cid, ans=ans):
                                await asyncio.sleep(random.randint(8, 20))
                                r = await llm(REWRITE, f"Вопрос клиента: {cv.get('pending_q')}\nПереписка:\n{transcript(cv, 10)}\n\nОтвет коллеги: {ans}")
                                out = clean((r or {}).get("reply") or ans)
                                if await send(cv["uid"], out):
                                    cv["history"].append({"role": "bot", "text": out, "ts": time.time()})
                                    cv["pending_q"] = None
                                    schedule_followup(cv, 0)
                                    save()
                                    await tell(cid, f"Ответил @{cv.get('username')} про part-time:\n\n{out}")
                            asyncio.get_event_loop().create_task(_pt())
                            continue
                        # разово 08.11: Марина. Наше же «Окей, тогда так» после перезапуска приняли за ручной ответ и замолчали.
                        h0 = cv.get("history") or []
                        if cv.get("human") and any(x.get("role") == "owner" and (x.get("text") or "").strip() == "Окей, тогда так" for x in h0):
                            for x in h0:
                                if x.get("role") == "owner" and (x.get("text") or "").strip() == "Окей, тогда так":
                                    x["role"] = "bot"
                            cv["human"], cv["muted"] = False, False
                            cv["next_at"] = now + random.randint(10, 25)
                            log.info("resume (own message mistaken for manual): %s", cid)
                            await tell(cid, f"Ассистент снова ведёт диалог с @{cv.get('username')} (своё сообщение после перезапуска принял за ручное).")
                            continue
                        h = cv.get("history") or []
                        if (h and h[-1].get("role") == "user" and not cv.get("human") and not cv.get("muted")
                                and not cv.get("next_at") and now - (cv.get("last_user_ts") or 0) < 3 * 3600):
                            cv["next_at"] = now + random.randint(5, 20)
                            log.info("resume after restart: %s", cid)
                await call_tick(now)
                for cid, cv in list(S["convs"].items()):
                    if cv.get("then_at") and cv["then_at"] <= now and not cv.get("human"):
                        txt = cv.pop("then_text", "")
                        cv.pop("then_at", None)
                        if txt and str(cv.get("uid", "")).startswith("tg:"):
                            async def _then(cv=cv, txt=txt):
                                if await tg_human(int(cv["uid"][3:]), txt):
                                    cv["history"].append({"role": "bot", "text": txt, "ts": time.time()})
                                    schedule_followup(cv, 0)
                                    save()
                            asyncio.get_event_loop().create_task(_then())
                        continue
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


REWRITE_CALL = """Ты Алексей из Fortex UAE. Клиент готов созвониться в Zoom, Александр (руководитель) ответил, на какое время его назначить, часто это расшифровка голосового.
Определи дату и время начала созвона по Дубаю и длительность (если не сказано, 60 минут). Дни недели считай от сегодняшней даты: ближайший такой день в будущем.
Напиши клиенту коротко, на «ты», 1–2 предложения, без длинных тире: предложи это время и спроси, удобно ли. Пример: «Давайте в среду в 12:00 по Дубаю, вам удобно?»
Если из ответа Александра время понять нельзя, start null.
Ответь JSON: {"start": "YYYY-MM-DD HH:MM" или null, "minutes": 60, "reply": "<текст клиенту>"}"""


REWRITE = """Ты сотрудник Fortex UAE в директе Instagram. Коллега (владелец) дал ответ на вопрос клиента, часто это расшифровка голосового.
Перескажи его клиенту коротко и по-человечески, 1–3 предложения, на «ты», без длинных тире, без слова «профиль». Ничего не добавляй от себя, кроме вежливой связки.
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
    call = cv.get("call") or {}
    zl = ZOOM_RE.search(text or "")
    if zl and call.get("status") == "confirmed" and len(text.strip()) < len(zl.group(0)) + 40:
        call["link"] = zl.group(0).rstrip(".,)")
        S["ask"].pop(str(rid), None)
        if time.time() >= call["at"] - 6 * 60:
            call["r5"] = True
            await say(cv, f"Вот ссылка на Zoom, подключайтесь: {call['link']}")
            await ev.reply(f"Отправил ссылку @{cv.get('username')}")
        else:
            save()
            await ev.reply("Ссылку сохранил, Алексей отправит клиенту за 5 минут до начала")
        return True
    if cv.get("call_q"):
        d = datetime.now(DXB)
        r = await llm(REWRITE_CALL, f"Сегодня {WD[d.weekday()]} {d:%Y-%m-%d %H:%M} (Дубай).\nВопрос: {cv.get('pending_q')}\n"
                                    f"Переписка:\n{transcript(cv, 8)}\n\nОтвет Александра: {text}") or {}
        try:
            at = datetime.strptime(r.get("start") or "", "%Y-%m-%d %H:%M").replace(tzinfo=DXB).timestamp()
        except Exception:
            at = 0
        if at > time.time():
            out = clean(r.get("reply") or "")
            if out and await say(cv, out):
                cv["call"] = {"at": at, "min": int(r.get("minutes") or 60), "status": "proposed",
                              "link": zl.group(0).rstrip(".,)") if zl else None}
                cv["call_q"] = False
                cv["pending_q"] = None
                S["ask"].pop(str(rid), None)
                schedule_followup(cv, 0)
                save()
                await ev.reply(f"Предложил @{cv.get('username')}: {call_when(at)}\n\n{out}\n\nКогда клиент согласится, поставлю в календарь.")
                return True
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
    elif a in ("gcal", "zoom") and len(parts) > 2:
        val = " ".join(parts[2:])
        if a == "zoom":
            keys = re.findall(r"[A-Za-z0-9_\-]{15,}", val)
            if len(keys) < 3:
                try:
                    await ev.delete()
                except Exception:
                    pass
                await ev.respond(f"Нашёл {len(keys)} ключа из 3. Нужно: /igdm zoom AccountID ClientID ClientSecret (через пробел, без скобок)")
                return
            val = " ".join(keys[:3])
        open(os.path.join(BASE, "gcal_hook" if a == "gcal" else "zoom_creds"), "w").write(val)
        try:
            await ev.delete()
        except Exception:
            pass
        if a == "zoom":  # новые ключи: пробуем ещё раз создать встречи для уже подтверждённых созвонов
            for c_ in S.get("convs", {}).values():
                if (c_.get("call") or {}).get("status") == "confirmed" and not c_["call"].get("link"):
                    c_["call"]["zoom_tried"] = False
            save()
        await ev.respond(("Google Календарь" if a == "gcal" else "Zoom") + " подключён, сообщение с ключом удалил")
        return
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
                   f"/igdm on | off\n/igdm test @аккаунт (кому отвечать в тесте)\n/igdm live (отвечать всем)\n/igdm pause @аккаунт (ассистент молчит в диалоге)\n/igdm resume @аккаунт (вернуть ассистента)\n/igdm manychat | graph (откуда берём сообщения)\n/igdm tg on | off (отвечать в личке аккаунта радара)\n"
                   f"Календарь: {'подключён' if secret('gcal_hook') else 'нет'}, Zoom: {'подключён' if secret('zoom_creds') else 'нет'}\n/igdm gcal <ссылка веб-хука>\n/igdm zoom <Account ID> <Client ID> <Client Secret>")


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
            # скорость как у живого человека с телефона (~4 знака в секунду), а не 10 секунд на любое сообщение (08.11)
            secs = max(3.0, min(40.0, 1.5 + len(part) / 4.0)) * random.uniform(0.85, 1.15)
            try:
                if time.time() - TYPING.get(peer, 0) < 6:  # человек печатает: подождём, не перебиваем
                    await wait_quiet(peer, f"tg:{peer}", max_wait=60)
                async with u.action(peer, "typing"):
                    await asyncio.sleep(secs + autoreply.gap_left(peer))
                m = await u.send_message(peer, part)
                autoreply.mark_sent(peer)
                S["sent"].append(f"tg:{m.id}")
                save()  # сразу на диск: иначе после перезапуска своё же сообщение примем за «ручной ответ» и замолчим (08.11)
                last = m.id
            except Exception as e:
                log.warning("tg send: %s", e)
                break
    return last


async def tg_block(peer, text):
    """Одно структурированное сообщение (абзацы), перед ним долго «печатает»: ~5 знаков в секунду, до 2 минут (дожим, 08.11)."""
    u = CTX.get("user")
    if not u:
        return None
    import autoreply
    async with autoreply.peer_lock(peer):
        try:
            secs = max(15.0, min(120.0, len(text) / 5.0)) * random.uniform(0.85, 1.15)
            async with u.action(peer, "typing"):
                await asyncio.sleep(secs)
            m = await u.send_message(peer, text)
            autoreply.mark_sent(peer)
            S["sent"].append(f"tg:{m.id}")
            save()
            return m.id
        except Exception as e:
            log.warning("tg block: %s", e)
            return None


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
                    pass  # источник в статистике (keeper/status.json), без отдельного сообщения
                    break
        if not cv.get("source"):  # откуда пришёл: по фразе из ссылки «Бесплатная консультация» (/c/<источник>)
            low = text.lower()
            if "есть вопрос по ипотеке в дубае" in low or "есть вопрос по счёту в оаэ" in low:
                cv["source"] = "с сайта"  # кнопка «Задать вопрос» на страницах /ipoteka/ и /gid/
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
            # о запросе консультации не пишем отдельно: Александру приходит только готовый лид
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
        asyncio.get_event_loop().create_task(tg_read_soon(snd.id, ev.id))  # прочитано через 3 с (решение Александра 03.11)
        on_user_message(cv)
        save()
    except Exception:
        log.exception("tg inbound")


async def tg_read_soon(peer, max_id, delay=3.0):
    """Отметить сообщение прочитанным ровно через ~3 секунды после получения, не дожидаясь ответа."""
    u = CTX.get("user")
    if not u:
        return
    await asyncio.sleep(delay + random.uniform(-0.3, 0.3))
    try:
        await u.send_read_acknowledge(peer, max_id=max_id)
    except Exception as e:
        log.warning("tg read soon: %s", e)


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


async def send_dialogs(ev, text):
    """/dialogs [часов] — владельцу: переписки Алексея за последние N часов (по умолчанию 48), даже если собеседник их удалил."""
    import datetime as _dt
    try:
        hours = int((text.split() + ["48"])[1])
    except Exception:
        hours = 48
    since = time.time() - hours * 3600
    items = [(max([h.get("ts", 0) for h in cv.get("history", [])] or [0]), cid, cv) for cid, cv in S.get("convs", {}).items()]
    items = sorted([x for x in items if x[0] >= since], reverse=True)
    if not items:
        return await ev.reply(f"За последние {hours} ч переписок не было")
    await ev.reply(f"📂 Переписки Алексея за {hours} ч: {len(items)}")
    who = {"user": "👤", "bot": "🤖 Алексей", "owner": "🧑‍💼 Ты"}
    for last, cid, cv in items[:15]:
        ch = "Telegram" if str(cv.get("uid") or "").startswith("tg:") else "Instagram"
        head = (f"<b>@{html.escape(str(cv.get('username') or '?'))}</b> · {ch}"
                + (f" · {html.escape(str(cv.get('name')))}" if cv.get("name") else "")
                + (f"\n<i>{html.escape(str(cv.get('summary')))[:300]}</i>" if cv.get("summary") else ""))
        lines = []
        for h in cv.get("history", []):
            t = _dt.datetime.fromtimestamp(h.get("ts", 0) + 4 * 3600).strftime("%d.%m %H:%M") if h.get("ts") else ""
            lines.append(f"{t} {who.get(h.get('role'), h.get('role'))}: {html.escape(str(h.get('text', '')))}")
        buf = head + "\n\n"
        for ln in lines:
            if len(buf) + len(ln) > 3800:
                await ev.respond(buf, parse_mode="html"); buf = ""
            buf += ln + "\n\n"
        if buf.strip():
            await ev.respond(buf, parse_mode="html")
