"""Автоответы радара в чатах: короткие экспертные комментарии от аккаунта радара.

Правила:
- отвечаем только на целевые сообщения (score >= 4) от бизнеса и состоятельных людей;
- не отвечаем админам и владельцам чатов, ботам, подозрительным аккаунтам;
- ответ не длиннее сообщения человека, 1–3 коротких предложения;
- перед отправкой пауза 3–15 минут; если за это время Александр сам написал в чат с этого аккаунта
  или нажал «Пропустить»/«Отправить» в карточке, автоответ отменяется;
- ветка максимум из 3 наших сообщений; третье может мягко позвать в личку;
- вопросы «ты бот?», «кто вы?», «это реклама?» и негатив: не отвечаем, сообщаем Александру;
- если за сутки 3+ негативных реакции на наши ответы: автоответы ставятся на паузу, Александру уведомление.
Включить/выключить: /auto on|off в боте.
"""
import asyncio, json, logging, os, random, re, time
from datetime import datetime, timedelta, timezone

import httpx

log = logging.getLogger("autoreply")
BASE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(BASE, "autoreply.json")
DUBAI = timezone(timedelta(hours=4))
DELAY = (180, 900)
FOLLOW_DELAY = (90, 420)
QUIET = (0, 8)
MIN_SCORE = 4
TOPIC_REPLIES = False  # решение Александра 29.10: на вопросы по счетам, ВНЖ и т.п. в чатах сами не отвечаем (удаляют), только посол Дубая
MAX_DEPTH = 2  # решение Александра 28.10: показал экспертность и вовремя закончил, дальше только 👍
ARGUE_RE = re.compile(r"не соглас|это не так|неправд|ошибаете|ошибаешься|не верно|неверно|не правы|не прав\b|вообще не|глупост|сами вы|откуда вы знаете|с чего вы взяли|не факт", re.I)

BOT_Q_RE = re.compile(r"\bбот\b|ты бот|вы бот|нейросет|chat ?gpt|\bgpt\b|кто (ты|вы) так|кто вы\b|откуда (ты|вы)|это реклам|реклама\?|продаёте|продаете|на кого работа", re.I)
NEG_RE = re.compile(r"спам|рекламщ|заткн|отвал|задолбал|надоел|бан\b|забань|кто тебя спрашивал|не пиши|не лезь|мошенн|развод|скам|инфоцыган|клоун|бред|чушь|ерунд", re.I)
SCAMMY_RE = re.compile(r"https?://|t\.me/|@\w{4,}|пишите в лс|пиши в лс|в личку|обмен|наличн|usdt|переведу|гарантия 100|быстрые деньги", re.I)

STYLE = """Ты пишешь ответ в русскоязычном Telegram-чате от имени Алексея. Позиция: «я не главный эксперт, просто кое-что знаю». Пишешь как живой человек, а не как консультант.

КТО ТЫ (это можно рассказывать, если спросят или к слову, коротко и по-свойски): Алексей, живёшь в Дубай Марине, в Дубае с 2022 года, с командой помогаешь с банками, визами и компаниями в ОАЭ. Больше личных подробностей не придумывай (семья, возраст, прошлая работа, где жил раньше): если спросят, отшутись или уйди от темы.
ЧЕЛОВЕЧНОСТЬ: ты не робот «только по делу». Можешь коротко отреагировать на жизнь вокруг: жара, пробки на Шейх Зайед, Марина, цены на аренду, переезд, как сам когда-то обустраивался. Тепло, с лёгкой иронией, по-соседски. Но держи вектор: разговор мягко возвращается к задаче человека (счёт, виза, компания, деньги, бизнес), чтобы он захотел обсудить её с тобой подробнее. Без давления и без продажи в лоб.

Что умеет наша сторона (используй как знание, не как рекламу): счета в банках ОАЭ для владельцев российского паспорта, личные и корпоративные, в том числе сложные случаи после отказов, крипта и трейдинг, сложные фризоны и лицензии; с Emirates ID и без; рабочие визы с Emirates ID (с ними банки работают охотнее, можно официально платить себе зарплату); ВНЖ Virtual Work (дёшево, но в банках слабее); компании во фризонах и на mainland; инфраструктура для ВЭД и расчётов с Китаем и Гонконгом. Ориентиры: личный счёт от 1 500 USD, корпоративный от 5 000 USD, рабочая виза от 5 500 USD, компания во фризоне от 14 000 AED. Сроки по корпоративному счёту 1–3 недели.

СТИЛЬ (строго):
- Ответ короткий: 1–2 предложения, в каждом 5–7 слов максимум, без портянок. Конкретика и цифры (сроки) лучше общих слов, цены почти никогда (банят за рекламу).
- Короткие предложения. Пишешь как в мессенджере: каждое предложение уйдёт отдельным сообщением, поэтому каждое предложение законченное и понятное само по себе.
- Иногда (не всегда) первым предложением короткое приветствие: «Добрый день!» или «Привет!», если в чате так общаются.
- Без кавычек.
- «Всегда говори да»: соглашайся и поддерживай («Да, конечно», «Да, хорошо», «Окей, это решаемо»), не начинай с «нет» и «но», если что-то не так, сначала согласись с целью человека, потом мягко предложи как лучше.
- Не допрос: не задавай вопрос в каждом сообщении, часто просто «Понял», «Принято», «Ага» и что-то по делу. Никогда не повторяй вопрос, который уже задавал или на который человек уже ответил (смотри всю ветку).
- Всего 1–3 предложения. Ответ НЕ длиннее сообщения, на которое отвечаешь.
- Можно многоточие. «:)» почти никогда: примерно один ответ из 10 и только если в ответе реально шутка. Других эмодзи нет.
- Вопрос задавай редко, примерно в каждом третьем ответе. Чаще просто короткое утверждение или мнение.
- Иногда лёгкая ирония, в том числе про скамеров и мутных посредников в таких чатах. Мы на стороне добра.
- Никогда не пиши «по опыту». Без канцелярита, без длинных тире, без ссылок, без контактов.
- Цены почти никогда. В крайнем случае «от X» из ориентиров выше.
- Не обещай 100% и конкретный банк. Не советуй ничего скрывать от банка. Только законные пути: компания и счёт в ОАЭ, зарплата себе через рабочую визу.
- Никогда не спорь. Всегда спокойно и на позитиве. Не упоминай название компании.
- ЗНАЙ, КОГДА ОСТАНОВИТЬСЯ: ты эксперт по Дубаю, но со всеми дружишь. Показал экспертность одной-двумя репликами и закончил. Не втягивайся в длинные обсуждения, не доказывай свою правоту. Если с тобой не согласны: «Да, у всех по-разному» или «Тоже вариант», и всё.
Примеры: «С русским паспортом открывают. Но не везде. Компания уже есть?» / «В Дубае с этим проще. Главное источник средств.» / «Тут половина чата посредники... Банк лучше напрямую.»"""


def _now():
    return datetime.now(DUBAI)


def _load():
    try:
        s = json.load(open(STATE))
    except Exception:
        s = {}
    today = _now().date().isoformat()
    s.setdefault("on", True); s.setdefault("threads", {}); s.setdefault("neg", []); s.setdefault("ours", [])
    if not s.get("on_2910b"):  # 29.10 вечер: включаем обратно, но только продвижение Дубая (до 2 в день), по нашей теме сами не отвечаем
        s["on"] = True; s["on_2910b"] = True
    if s.get("day") != today:
        s.update(day=today, total=0, chats={}, authors=[])
    return s


def _save(s):
    s["ours"] = s["ours"][-500:]
    s["neg"] = [t for t in s["neg"] if t > time.time() - 86400]
    json.dump(s, open(STATE, "w"), ensure_ascii=False)


def set_on(on):
    s = _load(); s["on"] = bool(on); _save(s)


def status():
    s = _load()
    return (f"Автоответы: {'включены' if s['on'] else 'выключены'}. Сегодня {s['total']} из {DAILY}, лимит в одном чате {PER_CHAT_DAY}. "
            f"Негатив за сутки: {len(s['neg'])}")


CTX = {}


def setup(**kw):
    CTX.update(kw)


async def _llm(messages, max_tokens=220):
    async with httpx.AsyncClient(timeout=90) as c:
        for m in ["anthropic/claude-sonnet-4.5", "anthropic/claude-haiku-4.5", "openai/gpt-4.1"]:
            try:
                r = await c.post("https://openrouter.ai/api/v1/chat/completions",
                                 headers={"Authorization": f"Bearer {CTX['openrouter_key']}", "Content-Type": "application/json",
                                          "HTTP-Referer": "https://fortex-uae.com", "X-Title": "Fortex Radar"},
                                 json={"model": m, "messages": messages, "temperature": 0.6, "max_tokens": max_tokens})
                if r.status_code == 200:
                    return r.json()["choices"][0]["message"]["content"].strip()
            except Exception as e:
                log.warning("llm %s: %s", m, e)
    return ""


def short7(t, max_sent=2, max_words=7):
    """Жёстко: не больше 2 предложений, в каждом не больше 7 слов. Длинные предложения выкидываем,
    если все длинные, берём первое и обрезаем до 7 слов."""
    sents = [x.strip() for x in re.findall(r"[^.!?…]+(?:\.\.\.|[.!?…]+)?", t or "") if x.strip()]
    ok = [x for x in sents if len(x.split()) <= max_words][:max_sent]
    if not ok and sents:
        w = sents[0].split()[:max_words]
        ok = [" ".join(w).rstrip(",;:")]
    return " ".join(ok)


def fits7(t, max_sent=2, max_words=7):
    sents = [x.strip() for x in re.findall(r"[^.!?…]+(?:\.\.\.|[.!?…]+)?", t or "") if x.strip()]
    return 0 < len(sents) <= max_sent and all(len(x.split()) <= max_words for x in sents)


async def shorten(t):
    """Если черновик длиннее нормы, переписываем коротко (1–2 предложения по 5–7 слов), смысл сохраняем."""
    t = (t or "").strip().strip('"«»')
    if not t or fits7(t):
        return t
    try:
        r = await _llm([{"role": "user", "content": "Перепиши ответ для чата максимально коротко: 1–2 предложения, в каждом не больше 7 слов. "
                         "Сохрани главный смысл и живой разговорный тон, без кавычек, без цен. Верни только текст.\n\n" + t}], max_tokens=80)
        r = (r or "").strip().strip('"«»')
        if r:
            t = r
    except Exception:
        pass
    return short7(t)


def _clean(t, limit):
    t = short7((t or "").strip().strip('"«»'))
    t = t.replace("—", ",").replace("–", ",")
    t = re.sub(r"(?i)по (моему )?опыту,?\s*", "", t)
    t = re.sub(r"\s+,", ",", t).strip()
    if t:
        t = t[0].upper() + t[1:]
    sents = re.findall(r"[^.!?…]+(?:\.\.\.|[.!?…])?", t)
    out = ""
    for snt in sents[:3]:
        snt = snt.strip()
        if not snt:
            continue
        cand = (out + " " + snt).strip()
        if len(cand) > max(limit, 25):
            break
        out = cand
    # вопрос не в каждом ответе: примерно в 2 из 3 случаев убираем вопросительные фразы, если есть что оставить
    if "?" in out and random.random() < 0.65:
        keep = [x.strip() for x in re.findall(r"[^.!?…]+(?:\.\.\.|[.!?…])?", out) if x.strip() and not x.strip().endswith("?")]
        if keep:
            out = " ".join(keep)
    # смайлик только изредка (примерно 1 из 10), остальное без него
    if ":)" in out and random.random() > 0.1:
        out = re.sub(r"\s*:\)+", "", out).strip()
        if out and out[-1] not in ".!?…":
            out += "."
    return out


def _parts(text):
    """Как пишут в мессенджере: одно предложение = одно сообщение, без точки в конце, без кавычек.
    Вопросительный и восклицательный знаки остаются, многоточие тоже."""
    t = re.sub(r'[«»"„“”]', "", text or "").strip()
    out = []
    for snt in re.findall(r"[^.!?…]+(?:\.\.\.|[.!?…]+)?", t):
        snt = snt.strip()
        if not snt:
            continue
        if snt.endswith(".") and not snt.endswith("..."):
            snt = snt[:-1].rstrip()
        out.append(snt)
    return out[:4] or ([t] if t else [])


_LOCKS, _LAST = {}, {}
MIN_GAP = 5.0  # между любыми двумя нашими сообщениями одному человеку или в один чат не меньше 5 секунд


def peer_lock(peer):
    if peer not in _LOCKS:
        _LOCKS[peer] = asyncio.Lock()
    return _LOCKS[peer]


def gap_left(peer):
    """Сколько ещё подождать, чтобы с прошлого нашего сообщения прошло не меньше MIN_GAP."""
    return max(0.0, MIN_GAP - (time.time() - _LAST.get(peer, 0)))


def mark_sent(peer):
    _LAST[peer] = time.time()


async def _send(user, chat_id, text, reply_to):
    """Как человек: прочитал через 2–3 с, потом каждое предложение отдельным сообщением,
    перед каждым «печатает» 5–10 с (короткое 5, длинное до 10). Возвращает список сообщений."""
    await asyncio.sleep(random.uniform(2, 3))
    try:
        await user.send_read_acknowledge(chat_id, max_id=reply_to)
    except Exception:
        pass
    msgs = []
    async with peer_lock(chat_id):
        for k, part in enumerate(_parts(text)):
            secs = max(5.0, min(10.0, 5.0 + len(part) / 12) + random.uniform(-0.4, 0.4)) + gap_left(chat_id)
            try:
                async with user.action(chat_id, "typing"):
                    await asyncio.sleep(secs)
            except Exception:
                await asyncio.sleep(secs)
            msgs.append(await user.send_message(chat_id, part, reply_to=reply_to if k == 0 else None))
            mark_sent(chat_id)
    try:  # журнал всех наших сообщений в чатах: потом проверяем, сколько из них удалили
        st = _load()
        st.setdefault("sent_log", []).extend([[chat_id, m.id, int(time.time())] for m in msgs])
        st["sent_log"] = st["sent_log"][-1500:]
        _save(st)
    except Exception:
        pass
    return msgs


SURV_F = os.path.join(BASE, "survival.json")


async def survival(user):
    """Какие наши сообщения в чатах ещё живы, а какие удалили (или нас выкинули из чата). Пишет survival.json, смотритель выкладывает его в отчёт."""
    s = _load()
    ts_of = {(int(c), int(i)): t for c, i, t in s.get("sent_log", [])}
    by = {}
    for c, i in s.get("ours", []) + [[c, i] for c, i, _ in s.get("sent_log", [])]:
        if int(i) not in by.setdefault(int(c), []):
            by[int(c)].append(int(i))
    items = []
    for c, ids in by.items():
        title = str(c)
        try:
            ent = await user.get_entity(c)
            title = getattr(ent, "title", title)
            msgs = await user.get_messages(ent, ids=ids)
        except Exception as e:
            items += [{"chat": title, "id": i, "alive": None, "err": type(e).__name__, "ts": ts_of.get((c, i))} for i in ids]
            continue
        for i, m in zip(ids, msgs):
            if m:
                items.append({"chat": title, "id": i, "alive": True, "ts": int(m.date.timestamp())})
                continue
            t = ts_of.get((c, i))
            if not t:  # время удалённого: по ближайшему сообщению перед ним
                try:
                    prev = await user.get_messages(ent, limit=1, offset_id=i)
                    t = int(prev[0].date.timestamp()) if prev else None
                except Exception:
                    t = None
            items.append({"chat": title, "id": i, "alive": False, "ts": t})
        await asyncio.sleep(2)
    json.dump({"at": int(time.time()), "items": items}, open(SURV_F, "w"), ensure_ascii=False)
    log.info("survival: %d messages checked", len(items))


async def survival_loop(user):
    await asyncio.sleep(90)
    while True:
        try:
            await survival(user)
        except Exception as e:
            log.warning("survival: %s", e)
        await asyncio.sleep(6 * 3600)


async def _owner_wrote(user, chat_id, after_id, ours):
    try:
        async for m in user.iter_messages(chat_id, from_user="me", min_id=after_id, limit=20):
            if [chat_id, m.id] not in ours:
                return True
    except Exception as e:
        log.warning("owner check: %s", e)
    return False


async def _is_admin(user, chat_id, uid):
    try:
        p = await user.get_permissions(chat_id, uid)
        return bool(p.is_admin or p.is_creator)
    except Exception:
        return False


def _suspicious(sender, text):
    if getattr(sender, "scam", False) or getattr(sender, "fake", False) or getattr(sender, "bot", False):
        return True
    if not getattr(sender, "username", None) and not getattr(sender, "photo", None):
        return True
    return bool(SCAMMY_RE.search(text))


_STYLE_CACHE = {}


async def chat_style(user, chat_id):
    """Как пишут в чате: медианная длина последних сообщений. Возвращает (limit, подсказка для нейросети)."""
    c = _STYLE_CACHE.get(chat_id)
    if c and c[0] > time.time() - 6 * 3600:
        return c[1], c[2]
    lens = []
    try:
        async for m in user.iter_messages(chat_id, limit=60):
            if m.raw_text and not m.out:
                lens.append(len(m.raw_text))
    except Exception as e:
        log.warning("chat style: %s", e)
    lens.sort()
    med = lens[len(lens) // 2] if lens else 80
    if med < 50:
        lim, hint = 70, "В этом чате пишут очень коротко, одной строкой. Пиши так же: одна короткая фраза."
    elif med < 130:
        lim, hint = 160, "В этом чате пишут коротко, 1–2 предложения. Пиши так же."
    else:
        lim, hint = 320, "В этом чате принято писать развёрнуто. Можно 2–4 предложения, но без воды."
    _STYLE_CACHE[chat_id] = (time.time(), lim, hint)
    return lim, hint


def _quiet():
    return QUIET[0] <= _now().hour < QUIET[1]


async def maybe_auto_reply(user, ev, sender, text, res, lid, db):
    """Первый ответ на сообщение, по которому создана карточка лида. Только при прямом попадании."""
    try:
        s = _load()
        s.setdefault("lead_keys", []).append(f"{ev.chat_id}:{ev.id}"); s["lead_keys"] = s["lead_keys"][-300:]; _save(s)
        if not TOPIC_REPLIES or classify(text, await _title(ev), res) != "direct" or not _can_reply(s, ev.chat_id, sender.id):
            return
        if _suspicious(sender, text) or BOT_Q_RE.search(text) or await _is_admin(user, ev.chat_id, sender.id):
            return
        s["total"] += 1; s["chats"][str(ev.chat_id)] = s["chats"].get(str(ev.chat_id), 0) + 1; s["authors"].append(sender.id); s.setdefault("chat_last", {})[str(ev.chat_id)] = time.time(); _save(s)
        delay = random.randint(*DELAY)
        await CTX["notify"](f"🤖 Лид #{lid}: если ничего не нажмёшь, отвечу сам примерно через {delay // 60} мин. «Пропустить» в карточке отменит")
        await asyncio.sleep(delay)
        st = db.execute("select status from leads where id=?", (lid,)).fetchone()
        s = _load()
        if not s["on"] or (st and st[0] != "new") or await _owner_wrote(user, ev.chat_id, ev.id, s["ours"]):
            s["total"] = max(0, s["total"] - 1); _save(s)
            return
        lim, _hint = await chat_style(user, ev.chat_id)
        draft = _clean(await shorten(res.get("reply", "")), min(len(text), lim) if lim < 300 else len(text))
        if not draft:
            return
        ms = await _send(user, ev.chat_id, draft, ev.id)
        m = ms[0]
        db.execute("update leads set status='auto', draft=?, ts=? where id=?", (draft, time.time(), lid)); db.commit()
        s = _load()
        th = {"depth": 1, "root": text[:800], "author": sender.id, "history": [draft], "lid": lid}
        for x in ms:
            s["ours"].append([ev.chat_id, x.id])
            s["threads"][f"{ev.chat_id}:{x.id}"] = th
        _save(s)
        await CTX["notify"](f"🤖 Ответил сам (лид #{lid}):\n«{draft}»", buttons=CTX["buttons"](ev.chat_id, m.id))
    except Exception as e:
        log.exception("auto reply: %s", e)


async def on_reply_to_us(user, ev, rm, text):
    """Человек ответил на наше сообщение: продолжаем ветку (до 3 наших сообщений)."""
    try:
        s = _load()
        key = f"{ev.chat_id}:{rm.id}"
        th = s["threads"].get(key)
        if not th:
            return  # это было не автосообщение (Александр писал сам), не вмешиваемся
        sender = await ev.get_sender()
        if BOT_Q_RE.search(text) or NEG_RE.search(text):
            th["stopped"] = True
            neg = NEG_RE.search(text) is not None
            if neg:
                s["neg"].append(time.time())
                s.setdefault("muted_chats", {})[str(ev.chat_id)] = int(time.time())  # назвали спамом: в этом чате больше не пишем
            _save(s)
            await CTX["notify"](("⚠️ Негатив на автоответ" if neg else "❓ Спрашивают, кто мы / бот ли это") +
                                f" в чате. Сам не отвечаю, ветку остановил.\n«{text[:500]}»")
            if len([t for t in s["neg"] if t > time.time() - 86400]) >= 3:
                s["on"] = False; _save(s)
                await CTX["notify"]("⛔ За сутки 3 негативных реакции на автоответы. Поставил автоответы на паузу. "
                                    "Посмотри, что не так с тоном. Включить: /auto on")
            return
        if th.get("stopped") or th["depth"] >= MAX_DEPTH or _quiet():
            if not th.get("thumbed") and not _quiet() and ev.sender_id == th.get("author"):
                th["thumbed"] = True; _save(s)
                await _close_thumb(user, ev.chat_id, ev.id)  # разговор закончили: просто 👍 на последнее сообщение
            return
        if ARGUE_RE.search(text):  # спорят: по-дружески соглашаемся одной фразой и заканчиваем
            th["argue"] = True
        if not th.get("starter") and not th.get("argue") and not (TOPIC_RE.search(text) or "?" in text):
            return  # ушли от нашей темы: молчим
        if await _is_admin(user, ev.chat_id, ev.sender_id) and ev.sender_id != th["author"]:
            return
        await asyncio.sleep(random.randint(*FOLLOW_DELAY))
        s = _load()
        if not s["on"] or await _owner_wrote(user, ev.chat_id, ev.id, s["ours"]):
            return
        depth = th["depth"] + 1
        lim, hint = await chat_style(user, ev.chat_id)
        if th.get("argue"):
            task = ("Человек не согласен или спорит. Не спорь и ничего не доказывай: по-дружески признай, что у всех по-разному "
                    "или что его вариант тоже рабочий, одной короткой фразой. Без вопроса. Это последнее сообщение в ветке.")
            depth = MAX_DEPTH
        elif th.get("starter"):
            task = ("Это обсуждение начали мы своим вопросом, человек ответил. Отреагируй по-человечески: коротко поблагодари или согласись, "
                    "можешь задать один уточняющий вопрос по сути. Мы разбираемся в теме, но говорим скромно. Если в разговоре прозвучала задача, которую мы решаем "
                    "(счёт, виза, компания, переводы через ОАЭ), и это звучит уместно, можно вскользь одной фразой сказать, что в Дубае такое решаемо и мы этим занимаемся, "
                    "без цен и без «пишите в личку», если человек сам не интересуется. Не продавай. Не придумывай личных историй." + (
                    " Это наше последнее сообщение в ветке: если человеку это актуально, можно спокойно сказать «если что, пишите в личку»." if depth >= MAX_DEPTH else ""))
        else:
          task = ("Это наше последнее сообщение в ветке: коротко ответь по сути и закругли разговор по-дружески, без вопроса. "
                "Только если человеку явно нужна помощь, вскользь: «Если что, пишите в личку. Подскажу.»"
                if depth >= MAX_DEPTH else "Коротко ответь по сути. Вопрос только если без него никак.")
        task += "\n" + hint
        msgs = [{"role": "system", "content": STYLE},
                {"role": "user", "content": f"Исходное сообщение человека:\n{th['root']}\n\nНаши ответы:\n" +
                 "\n".join(th["history"]) + f"\n\nНовое сообщение в ветке:\n{text[:800]}\n\n{task}\n"
                 "Если отвечать не нужно (просто «спасибо», «ок»), верни пустую строку. Верни только текст ответа."}]
        reply = _clean(await shorten(await _llm(msgs)), max(len(text), lim) if th.get("starter") else (len(text) if depth < MAX_DEPTH else max(len(text), 90)))
        if not reply:  # «спасибо», «ок» и т.п.: не отвечаем, ставим 👍 и закрываем ветку
            th["stopped"] = True; th["thumbed"] = True; _save(s)
            await _close_thumb(user, ev.chat_id, ev.id)
            return
        ms = await _send(user, ev.chat_id, reply, ev.id)
        m = ms[0]
        s = _load()
        th.update(depth=depth); th["history"].append(reply)
        for x in ms:
            s["ours"].append([ev.chat_id, x.id])
            s["threads"][f"{ev.chat_id}:{x.id}"] = th
        _save(s)
        await CTX["notify"](f"🤖 Продолжил ветку ({depth}/{MAX_DEPTH}):\n«{reply}»", buttons=CTX["buttons"](ev.chat_id, m.id))
    except Exception as e:
        log.exception("follow up: %s", e)


async def _close_thumb(user, chat_id, msg_id):
    """Конец разговора: через паузу ставим 👍 (если в чате нельзя, 🤝 или 🙏) на последнее сообщение человека."""
    try:
        from telethon.tl.functions.messages import SendReactionRequest
        from telethon.tl.types import ReactionEmoji
        await asyncio.sleep(random.randint(20, 90))
        for emo in ("👍", "🤝", "🙏"):
            try:
                await user(SendReactionRequest(peer=chat_id, msg_id=msg_id, reaction=[ReactionEmoji(emoticon=emo)]))
                log.info("close thumb %s in %s/%s", emo, chat_id, msg_id)
                return
            except Exception as e:
                if "REACTION_INVALID" in str(e) or "REACTION_EMPTY" in str(e):
                    continue
                log.warning("close thumb: %s", e)
                return
    except Exception as e:
        log.warning("close thumb: %s", e)


async def delete_message(user, chat_id, msg_id):
    try:
        await user.delete_messages(chat_id, [msg_id])
        return "Удалил"
    except Exception as e:
        return f"Не получилось удалить: {e}"


# ---------- маршрутизация: прямое попадание -> ответ (+👍), косвенное -> только реакция, мимо -> ничего ----------
DAILY = int(os.environ.get("AUTO_DAILY", "6"))   # 28.10: очень аккуратно, в паре чатов забанили за «спам»
PER_CHAT_DAY = 1
CHAT_GAP_H = 72                                    # в одном чате не чаще раза в 3 дня
GEO_RE = re.compile(r"дуба[йеяю]|\bоаэ\b|эмират|\buae\b|dubai|абу[- ]?даби|abu ?dhabi|шардж|sharjah|аджман|ajman|рас[- ]?аль|ras al", re.I)
EID_RE = re.compile(r"emirates ?id|эмирейтс ?(ай ?ди|id)|\bэмирейтс\b", re.I)
TOPIC_RE = re.compile(r"сч[её]т|банк|\bвнж\b|виз[аыуе]|резидент|ресидент|резиденц|emirates ?id|эмирейтс|компани|лиценз|фри ?зон|free ?zone|freezone|mainland|мейнленд|golden|золот\w* виз|virtual work|отказал|заблокир|заморозил", re.I)
INDIRECT_RE = re.compile(r"платёжн\w* агент|платежн\w* агент|оплатить|оплат[аиу]|перевод|перевест|swift|свифт|инвойс|контрагент|\bвэд\b|импорт|экспорт|кита[йяе]|юан|alipay|wechat|карт[аыуе]\b|карточк|обнал|\busdt\b|крипт\w* в фиат", re.I)
QUESTION_RE = re.compile(r"\?|подскажите|подскажи|кто знает|кто-нибудь|кто открывал|кто делал|посоветуйте|как (сделать|получить|открыть|продлить|оформить)|почему|зачем|можно ли|нужно ли|сколько|ищу|нужен|нужна|нужно|не могу|не получается|отказ", re.I)


async def _title(ev):
    try:
        ch = await ev.get_chat()
        return getattr(ch, "title", "") or ""
    except Exception:
        return ""


def classify(text, title, res):
    """'direct' | 'indirect' | 'none'. Прямое: тема наша (счёт, банк, ВНЖ, виза, Emirates ID, компания) и речь про ОАЭ
    (в тексте или это дубайский чат), и это вопрос, просьба или проблема. Нейросеть может только понизить до «мимо»."""
    hit = (res or {}).get("hit", "")
    geo = GEO_RE.search(text) or GEO_RE.search(title) or EID_RE.search(text)
    if TOPIC_RE.search(text) and geo and QUESTION_RE.search(text) and hit != "нет":
        return "direct"
    if hit == "прямое" and TOPIC_RE.search(text) and geo:
        return "direct"
    rich = (res or {}).get("tier") in ("бизнес", "состоятельный частный")
    if rich or hit == "косвенное" or (INDIRECT_RE.search(text) and (res or {}).get("relevant") and hit != "нет"):
        return "indirect"
    return "none"


def _can_reply(s, chat_id, author):
    last = s.setdefault("chat_last", {}).get(str(chat_id), 0)
    return (s["on"] and not _quiet() and s["total"] < DAILY and s["chats"].get(str(chat_id), 0) < PER_CHAT_DAY
            and author not in s["authors"] and str(chat_id) not in s.setdefault("muted_chats", {})
            and time.time() - last > CHAT_GAP_H * 3600)


def _kb():
    try:
        return open(os.path.join(BASE, "kb.md"), encoding="utf-8").read()[:9000]
    except Exception:
        return ""


async def _react(user, ev, sender, text, emo="👍"):
    try:
        import reactions
        emo = emo if emo in reactions.ALLOWED else "👍"
        asyncio.get_event_loop().create_task(reactions.maybe_react(user, ev.chat_id, ev.id, sender.id, text, emo))
    except Exception as e:
        log.warning("react: %s", e)


async def maybe_visibility(user, ev, sender, text, res):
    """Вызывается на каждое сообщение после оценки нейросетью. Прямое попадание: ответ + 👍 (любому человеку).
    Если по сообщению создана карточка лида, отвечает ветка лида (там работает «Пропустить»)."""
    try:
        if not res or len(text) < 15:
            return
        kind = classify(text, await _title(ev), res)
        if kind == "none":
            return
        if _suspicious(sender, text) or BOT_Q_RE.search(text) or await _is_admin(user, ev.chat_id, sender.id):
            return
        await _react(user, ev, sender, text, res.get("reaction") or "👍")
        if kind != "direct" or not TOPIC_REPLIES:
            return  # косвенное: только реакция
        await asyncio.sleep(20)  # даём ветке лида забрать сообщение
        s = _load()
        if f"{ev.chat_id}:{ev.id}" in s.get("lead_keys", []) or not _can_reply(s, ev.chat_id, sender.id):
            return
        s["total"] += 1; s["chats"][str(ev.chat_id)] = s["chats"].get(str(ev.chat_id), 0) + 1; s["authors"].append(sender.id); s.setdefault("chat_last", {})[str(ev.chat_id)] = time.time(); _save(s)
        lim, hint = await chat_style(user, ev.chat_id)
        sysmsg = [{"type": "text", "text": STYLE + "\n\nСПРАВКА:\n" + _kb(), "cache_control": {"type": "ephemeral"}},
                  {"type": "text", "text": "Это прямой вопрос по нашей теме. Ответь строго по сути вопроса одним-двумя короткими фактами, "
                   "как знающий человек в чате. Не уходи в сторону и не отвечай на то, о чём не спрашивали. Без продажи. "
                   "Если точного ответа нет в справке, скажи осторожно и общими словами, ничего не выдумывай.\n" + (hint or "")}]
        draft = _clean(await shorten(await _llm([{"role": "system", "content": sysmsg}, {"role": "user", "content": text}])),
                       min(max(len(text), 60), lim) if lim < 300 else len(text))
        if not draft:
            return
        delay = random.randint(*DELAY)
        await CTX["notify"](f"🎯 Прямое попадание ({res.get('topic', '')}). Отвечу через {delay // 60} мин. Ответишь сам, промолчу.\n«{text[:300]}»\n\nЧерновик: «{draft}»")
        await asyncio.sleep(delay)
        s = _load()
        if not s["on"] or await _owner_wrote(user, ev.chat_id, ev.id, s["ours"]):
            return
        ms = await _send(user, ev.chat_id, draft, ev.id)
        m = ms[0]
        s = _load()
        th = {"depth": 1, "root": text[:800], "author": sender.id, "history": [draft], "lid": None}
        for x in ms:
            s["ours"].append([ev.chat_id, x.id])
            s["threads"][f"{ev.chat_id}:{x.id}"] = th
        _save(s)
        await CTX["notify"](f"🤖 Ответил:\n«{draft}»", buttons=CTX["buttons"](ev.chat_id, m.id))
    except Exception as e:
        log.exception("route: %s", e)


# ===== Посол Дубая: иногда коротко и по-доброму рассказываем, почему в Дубае хорошо жить =====
# Не про услуги и не про цены. Только там, где люди сами обсуждают переезд, где жить, налоги, безопасность, климат.
AMB_RE = re.compile(r"переезд|переехать|переезжа|релокац|эмигр|уехать (из|в|жить)|куда (уехать|переехать|податься)|где (жить|лучше жить)|"
                    r"страна для жизни|сменить страну|внж|виз[аыу] (в|для)|налог|безопасн|стабильн|жара|жарко|климат|"
                    r"дуба|оаэ|эмират|абу-?даби|бали|таиланд|пхукет|турци|кипр|грузи|серби|черногори|испани|португали|европ", re.I)
AMB_DAILY = int(os.environ.get("AMB_DAILY", "2"))   # всего в день по всем чатам
AMB_CHAT_DAYS = 7                                    # в одном чате не чаще раза в неделю
AMB_SCANS = 30                                       # проверок нейросетью в день (экономия)
AMB_STYLE = """Ты Алексей: живёшь в Дубай Марине, в Дубае с 2022 года. В русскоязычном чате люди обсуждают переезд, где жить, налоги, безопасность, климат или другие страны.
Иногда, когда это к месту, ты коротко и по-доброму вставляешь, почему в Дубае жить хорошо. Как живой человек, не как реклама.
Плюсы Дубая, которые можно упоминать (одну-две мысли за раз): спокойно и безопасно, в окно выглянешь, тишь да гладь; нет подоходного налога для физлиц; удобно для бизнеса и банков; много целеустремлённых людей, которые работают и развиваются; город для молодых и прогрессивных; перелёты в любую точку; всё работает, сервис.
Честно признавай минусы, если их называют: да, летом жарко, да, ценник выше. Но люди живут и постоянно приезжают.
НЕЛЬЗЯ: политика, войны и конфликты, критика других стран и народов, санкции, религия; цены на наши услуги, реклама услуг, ссылки, контакты, «пишите в личку»; спорить или давить; повторять «Дубай, Дубай» в каждом сообщении.
Формат: 1–2 коротких предложения по 5–7 слов, каждое уйдёт отдельным сообщением, без кавычек, без точки в конце. Можно лёгкая ирония.
Если вставка здесь неуместна (тема не та, люди ссорятся, трагедия, политика, реклама, нас не поймут), верни ровно SKIP."""


def _amb_ok(s, chat_id):
    a = s.setdefault("amb", {"day": "", "n": 0, "scans": 0, "chats": {}})
    today = _now().date().isoformat()
    if a.get("day") != today:
        a.update(day=today, n=0, scans=0)
    last = a["chats"].get(str(chat_id), 0)
    if str(chat_id) in s.setdefault("muted_chats", {}):
        return False
    return s["on"] and not _quiet() and a["n"] < AMB_DAILY and a["scans"] < AMB_SCANS and time.time() - last > AMB_CHAT_DAYS * 86400


async def maybe_ambassador(user, ev, text):
    """Вызывается на сообщения в группах. Дешёвый фильтр, потом нейросеть решает, уместно ли вставить слово про Дубай."""
    try:
        if ev.out or not ev.is_group or len(text) < 40 or not AMB_RE.search(text):
            return
        s = _load()
        if not _amb_ok(s, ev.chat_id):
            return
        sender = await ev.get_sender()
        if sender is None or getattr(sender, "bot", False) or _suspicious(sender, text) or await _is_admin(user, ev.chat_id, sender.id):
            return
        s["amb"]["scans"] += 1; _save(s)
        ctx = []
        async for m in user.iter_messages(ev.chat_id, limit=8):
            if m.raw_text and m.id != ev.id:
                ctx.append(m.raw_text.strip().replace("\n", " ")[:200])
        if len(ctx) < 4:
            return  # чат почти пустой: не живое обсуждение
        title = await _title(ev)
        draft = await _llm([{"role": "system", "content": AMB_STYLE},
                            {"role": "user", "content": f"Чат: {title}\nПоследние сообщения:\n" + "\n".join(f"- {c}" for c in reversed(ctx)) +
                             f"\n\nСообщение, на которое можно ответить:\n{text[:800]}\n\nТвой ответ или SKIP:"}], max_tokens=120)
        draft = (draft or "").strip()
        if not draft or draft.upper().startswith("SKIP"):
            return
        draft = _clean(await shorten(draft), max(len(text), 80))
        if not draft:
            return
        await asyncio.sleep(random.randint(*FOLLOW_DELAY))
        s = _load()
        if not _amb_ok(s, ev.chat_id) or await _owner_wrote(user, ev.chat_id, ev.id, s["ours"]):
            return
        ms = await _send(user, ev.chat_id, draft, ev.id)
        s = _load()
        s["amb"]["n"] += 1; s["amb"]["chats"][str(ev.chat_id)] = time.time()
        th = {"depth": 1, "root": text[:800], "author": sender.id, "history": [draft], "lid": None, "starter": True}
        for x in ms:
            s["ours"].append([ev.chat_id, x.id])
            s["threads"][f"{ev.chat_id}:{x.id}"] = th
        _save(s)
        await CTX["notify"](f"🌴 Про Дубай в «{title}»:\n«{draft}»", buttons=CTX["buttons"](ev.chat_id, ms[0].id))
    except Exception as e:
        log.exception("ambassador: %s", e)
