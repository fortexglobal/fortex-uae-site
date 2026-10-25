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
DAILY = int(os.environ.get("AUTO_DAILY", "5"))
DELAY = (180, 900)
FOLLOW_DELAY = (90, 420)
QUIET = (0, 8)
MIN_SCORE = 4
MAX_DEPTH = 3

BOT_Q_RE = re.compile(r"\bбот\b|ты бот|вы бот|нейросет|chat ?gpt|\bgpt\b|кто (ты|вы) так|кто вы\b|откуда (ты|вы)|это реклам|реклама\?|продаёте|продаете|на кого работа", re.I)
NEG_RE = re.compile(r"спам|рекламщ|заткн|отвал|задолбал|надоел|бан\b|забань|кто тебя спрашивал|не пиши|не лезь|мошенн|развод|скам|инфоцыган|клоун|бред|чушь|ерунд", re.I)
SCAMMY_RE = re.compile(r"https?://|t\.me/|@\w{4,}|пишите в лс|пиши в лс|в личку|обмен|наличн|usdt|переведу|гарантия 100|быстрые деньги", re.I)

STYLE = """Ты пишешь ответ в русскоязычном Telegram-чате от имени человека, который давно занимается банками, визами и компаниями в ОАЭ. Позиция: «я не главный эксперт, просто кое-что знаю». Пишешь как живой человек.

Что умеет наша сторона (используй как знание, не как рекламу): счета в банках ОАЭ для владельцев российского паспорта, личные и корпоративные, в том числе сложные случаи после отказов, крипта и трейдинг, сложные фризоны и лицензии; с Emirates ID и без; рабочие визы с Emirates ID (с ними банки работают охотнее, можно официально платить себе зарплату); ВНЖ Virtual Work (дёшево, но в банках слабее); компании во фризонах и на mainland; инфраструктура для ВЭД и расчётов с Китаем и Гонконгом. Ориентиры: личный счёт от 1 500 USD, корпоративный от 5 000 USD, рабочая виза от 5 500 USD, компания во фризоне от 14 000 AED. Сроки по счёту обычно 2–4 недели.

СТИЛЬ (строго):
- Короткие предложения по 3–6 слов. Каждое заканчивается точкой (или вопросом).
- Всего 1–3 предложения. Ответ НЕ длиннее сообщения, на которое отвечаешь.
- Можно многоточие. «:)» почти никогда: примерно один ответ из 10 и только если в ответе реально шутка. Других эмодзи нет.
- Вопрос задавай редко, примерно в каждом третьем ответе. Чаще просто короткое утверждение или мнение.
- Иногда лёгкая ирония, в том числе про скамеров и мутных посредников в таких чатах. Мы на стороне добра.
- Никогда не пиши «по опыту». Без канцелярита, без длинных тире, без ссылок, без контактов.
- Цены почти никогда. В крайнем случае «от X» из ориентиров выше.
- Не обещай 100% и конкретный банк. Не советуй ничего скрывать от банка. Только законные пути: компания и счёт в ОАЭ, зарплата себе через рабочую визу.
- Никогда не спорь. Всегда спокойно и на позитиве. Не упоминай название компании.
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
    return (f"Автоответы: {'включены' if s['on'] else 'выключены'}. Сегодня {s['total']} из {DAILY}. "
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


def _clean(t, limit):
    t = (t or "").strip().strip('"«»')
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
    """Первый ответ на целевое сообщение."""
    try:
        s = _load()
        if not s["on"] or _quiet():
            return
        if int(res.get("score", 0)) < MIN_SCORE or res.get("tier") not in ("бизнес", "состоятельный частный"):
            return
        if s["total"] >= DAILY or s["chats"].get(str(ev.chat_id)) or sender.id in s["authors"]:
            return
        if _suspicious(sender, text) or BOT_Q_RE.search(text) or await _is_admin(user, ev.chat_id, sender.id):
            return
        s["total"] += 1; s["chats"][str(ev.chat_id)] = 1; s["authors"].append(sender.id); _save(s)
        delay = random.randint(*DELAY)
        await CTX["notify"](f"🤖 Лид #{lid}: если ничего не нажмёшь, отвечу сам примерно через {delay // 60} мин. «Пропустить» в карточке отменит")
        await asyncio.sleep(delay)
        st = db.execute("select status from leads where id=?", (lid,)).fetchone()
        s = _load()
        if not s["on"] or (st and st[0] != "new") or await _owner_wrote(user, ev.chat_id, ev.id, s["ours"]):
            s["total"] = max(0, s["total"] - 1); _save(s)
            return
        lim, _hint = await chat_style(user, ev.chat_id)
        draft = _clean(res.get("reply", ""), min(len(text), lim) if lim < 300 else len(text))
        if not draft:
            return
        m = await user.send_message(ev.chat_id, draft, reply_to=ev.id)
        db.execute("update leads set status='auto', draft=?, ts=? where id=?", (draft, time.time(), lid)); db.commit()
        s = _load()
        s["ours"].append([ev.chat_id, m.id])
        s["threads"][f"{ev.chat_id}:{m.id}"] = {"depth": 1, "root": text[:800], "author": sender.id, "history": [draft], "lid": lid}
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
            _save(s)
            await CTX["notify"](("⚠️ Негатив на автоответ" if neg else "❓ Спрашивают, кто мы / бот ли это") +
                                f" в чате. Сам не отвечаю, ветку остановил.\n«{text[:500]}»")
            if len([t for t in s["neg"] if t > time.time() - 86400]) >= 3:
                s["on"] = False; _save(s)
                await CTX["notify"]("⛔ За сутки 3 негативных реакции на автоответы. Поставил автоответы на паузу. "
                                    "Посмотри, что не так с тоном. Включить: /auto on")
            return
        if th.get("stopped") or th["depth"] >= MAX_DEPTH or _quiet():
            return
        if await _is_admin(user, ev.chat_id, ev.sender_id) and ev.sender_id != th["author"]:
            return
        await asyncio.sleep(random.randint(*FOLLOW_DELAY))
        s = _load()
        if not s["on"] or await _owner_wrote(user, ev.chat_id, ev.id, s["ours"]):
            return
        depth = th["depth"] + 1
        lim, hint = await chat_style(user, ev.chat_id)
        if th.get("starter"):
            task = ("Это обсуждение начали мы своим вопросом, человек ответил. Отреагируй по-человечески: коротко поблагодари или согласись, "
                    "можешь задать один уточняющий вопрос по сути. Мы разбираемся в теме, но говорим скромно. Если в разговоре прозвучала задача, которую мы решаем "
                    "(счёт, виза, компания, переводы через ОАЭ), и это звучит уместно, можно вскользь одной фразой сказать, что в Дубае такое решаемо и мы этим занимаемся, "
                    "без цен и без «пишите в личку», если человек сам не интересуется. Не продавай. Не придумывай личных историй." + (
                    " Это наше последнее сообщение в ветке: если человеку это актуально, можно спокойно сказать «если что, пишите в личку»." if depth >= MAX_DEPTH else ""))
        else:
          task = ("Это наше третье и последнее сообщение в ветке: коротко ответь по сути и вскользь, без давления, "
                "предложи написать в личку, если нужна консультация (например «Если что, пишите в личку. Подскажу.»)."
                if depth == MAX_DEPTH else "Коротко ответь по сути. Вопрос только если без него никак.")
        task += "\n" + hint
        msgs = [{"role": "system", "content": STYLE},
                {"role": "user", "content": f"Исходное сообщение человека:\n{th['root']}\n\nНаши ответы:\n" +
                 "\n".join(th["history"]) + f"\n\nНовое сообщение в ветке:\n{text[:800]}\n\n{task}\n"
                 "Если отвечать не нужно (просто «спасибо», «ок»), верни пустую строку. Верни только текст ответа."}]
        reply = _clean(await _llm(msgs), max(len(text), lim) if th.get("starter") else (len(text) if depth < MAX_DEPTH else max(len(text), 90)))
        if not reply:
            return
        m = await user.send_message(ev.chat_id, reply, reply_to=ev.id)
        s = _load()
        s["ours"].append([ev.chat_id, m.id])
        th.update(depth=depth); th["history"].append(reply)
        s["threads"][f"{ev.chat_id}:{m.id}"] = th
        _save(s)
        await CTX["notify"](f"🤖 Продолжил ветку ({depth}/{MAX_DEPTH}):\n«{reply}»", buttons=CTX["buttons"](ev.chat_id, m.id))
    except Exception as e:
        log.exception("follow up: %s", e)


async def delete_message(user, chat_id, msg_id):
    try:
        await user.delete_messages(chat_id, [msg_id])
        return "Удалил"
    except Exception as e:
        return f"Не получилось удалить: {e}"
