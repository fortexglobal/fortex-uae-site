"""Ассистент Криптоофиса: аккаунт Telegram ходит по крипточатам, ставит реакции, иногда отвечает и консультирует в личке.

Логика взята у радара Fortex (tools/radar): паузы, ветка максимум из 3 наших сообщений, ночью тишина,
стоп при негативе и вопросах «ты бот?», ассистент в личке отвечает только тем, кто написал первым.

Управление: команды в «Избранном» (Saved Messages) этого аккаунта. Туда же приходят уведомления и черновики.
  /status            что сделано сегодня
  /mode draft|live   draft: ответы в чатах только черновиком на одобрение; live: отправляет сам через 3–15 минут
  /ok N, /skip N     отправить или отменить черновик N
  /react on|off      реакции
  /auto on|off       ответы в чатах
  /dm on|off         консультант в личке
Ссылка в чатах не даётся никогда. Ссылка и партнёрство только в личке.

Файлы рядом: co.env (API_ID, API_HASH, OPENROUTER_KEY), co.session, kb.md, state.json.
Первый вход: python assistant.py --login (спросит телефон и код из Telegram).
"""
import asyncio, json, logging, os, random, re, sys, time
from datetime import datetime, timedelta, timezone

import httpx
from telethon import TelegramClient, events, functions, types

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("co")
BASE = os.path.dirname(os.path.abspath(__file__))
STATE_F = os.path.join(BASE, "state.json")
KB = open(os.path.join(BASE, "kb.md"), encoding="utf-8").read()
DUBAI = timezone(timedelta(hours=4))
REF = "https://t.me/officeapp/?start=WRKDRPWU4O2"


def _env():
    env = {}
    for line in open(os.path.join(BASE, "co.env"), encoding="utf-8"):
        if "=" in line:
            k, v = line.strip().split("=", 1)
            env[k] = v
    return env


ENV = _env()

# лимиты: начинаем спокойно, потом можно поднять в co.env
REACT_DAILY = int(ENV.get("REACT_DAILY", "20"))
REACT_PER_CHAT = int(ENV.get("REACT_PER_CHAT", "3"))
REACT_DELAY = (60, 600)
REPLY_DAILY = int(ENV.get("REPLY_DAILY", "2"))
REPLY_DELAY = (180, 900)
FOLLOW_DELAY = (90, 420)
SCAN_DAILY = int(ENV.get("SCAN_DAILY", "250"))  # проверок нейросетью в сутки
MAX_DEPTH = 3
QUIET = (0, 8)              # ночью по Дубаю в чатах не пишем и не реагируем
DM_DELAY = (60, 170)        # первая реплика в личке
DM_ACTIVE = 10 * 60
MODELS = ["anthropic/claude-sonnet-4.5", "openai/gpt-4.1", "anthropic/claude-haiku-4.5"]
EMOJI = ("👍", "🔥", "💯", "👌")

TOPIC_RE = re.compile(r"usdt|usdc|tether|юсдт|трон|tron|trc|erc|bep|\btrx\b|энерги|комисс|aml|амл|грязн|чист\w* крипт|"
                      r"заморо|заблок|binance|бинанс|bybit|байбит|okx|bitget|htx|kucoin|бирж|обмен|обменник|p2p|п2п|"
                      r"кошел|wallet|trust|сид|seed|перевод\w* крипт|крипт|биткоин|bitcoin|btc|eth|эфир|solana|\bsol\b|"
                      r"карт[аыуе]|\bcards?\b|\bfees?\b|frozen|blocked|exchange|\bswap|energy|visa|mastercard|виза|apple pay|оплат\w* за рубеж|зарубежн\w* карт|подписк", re.I)
BOT_Q_RE = re.compile(r"\bбот\b|ты бот|вы бот|нейросет|chat ?gpt|\bgpt\b|кто (ты|вы) так|ии отвеча|are you (a )?bot|\bai\b", re.I)
PAID_RE = re.compile(r"(тебе|вам) (за это )?плат|реклам|рефер|реф\w* ссылк|партн[её]рк|продвига|paid|referral|shill|\bads?\b", re.I)
NEG_RE = re.compile(r"spam|scam|shut up|stfu|спам|рекламщ|заткн|отвал|задолбал|надоел|забань|кто тебя спрашивал|не пиши|не лезь|мошенн|развод|скам|клоун|бред|чушь", re.I)
SCAMMY_RE = re.compile(r"https?://|t\.me/|пишите в лс|пиши в лс|наличн|гарантия 100|быстрые деньги|заработок от", re.I)

CHAT_STYLE = f"""Ты пишешь в русскоязычном Telegram-чате от первого лица, как живой человек (AR), который давно в крипте.
Ты сам около года пользуешься сервисом «Криптоофис» (Crypto Office) и тебе он реально нравится. Знания о нём ниже.

{KB}

ПРАВИЛА ДЛЯ ЧАТА (строго):
- Сначала польза: ответ по сути вопроса человека. Сервис упоминай не в каждом ответе, только когда это прямо помогает.
- Если упоминаешь, то без названия: «я пользуюсь одним сервисом, около года, мне удобно, всем рекомендую».
- Название говори, только если прямо спросили, одним словом «Криптоофис». Никогда не давай ссылку, не пиши @officeapp,
  не пиши «смотри у меня в профиле», «в описании», вообще не упоминай профиль и описание аккаунта.
- Не зови в личку, кроме случая, когда в задании сказано, что это третье сообщение.
- Если спросили, платят ли тебе или есть ли рефералка: честно «да, там есть рефералка, 15% с первой линии, дальше 5% и 2%,
  но рекомендую, потому что сам пользуюсь».
- Никогда не советуй прогонять грязную, рискованную или санкционную крипту через обмен, чтобы её приняла биржа.
  Про риск можно только «проверь адрес на AML до сделки и не бери крипту с высоким риском».
- Не выдумывай цифры, которых нет в знаниях. Не обещай безопасность и прибыль. Не называй кошелёк некастодиальным.
- Крипточаты (особенно про Binance и биржи) жёсткие и быстро банят. Пиши очень аккуратно и очень коротко:
  обычно 1 предложение, максимум 2, по 3–8 простых слов. Простые слова, как пишут в таких чатах. Никаких длинных,
  умных и «экспертных» фраз, без канцелярита, без длинных тире, без эмодзи (изредка «:)»).
- Ответ всегда заметно короче сообщения человека. Можно спорить спокойно, фактами, без наездов.
- Отвечай на языке чата и сообщения: если пишут по-английски, отвечай по-английски, если по-русски, по-русски.
  Название сервиса по-английски: Crypto Office.
"""

CLASSIFY = """Сообщение из Telegram-чата «{title}». Предыдущие сообщения:
{history}

Сообщение:
{text}

Оцени, насколько это наша тема: переводы и обмен USDT и крипты, комиссии и энергия TRON, AML и заморозки, кошельки,
уход и блокировки бирж, зарубежные карты и оплата с крипты. Ответь строго JSON без пояснений:
{{"score": 1-5, "react": true|false, "reply": "черновик ответа или пустая строка"}}
score: 5 — прямой вопрос, где наш опыт реально помогает; 4 — конкретный вопрос по теме; 3 — обсуждение по теме;
1–2 — не наша тема, реклама, флуд, продажа услуг. react = true, если сообщение по теме и нормальное (не реклама, не скам).
reply пиши только при score >= 4, по правилам чата, на языке сообщения, одно короткое предложение. Не упоминай сервис, если без этого можно дать полезный ответ."""

DM_SYSTEM = f"""Ты AR, отвечаешь в личных сообщениях Telegram. Человек написал тебе сам, чаще всего после твоих комментариев в
крипточатах. Ты около года пользуешься сервисом «Криптоофис» (Crypto Office) и консультируешь по нему, как знакомый, который
в теме. Знания ниже, ничего сверх них не выдумывай.

{KB}

ПРАВИЛА В ЛИЧКЕ:
- Пиши на языке собеседника (русский или английский). Коротко, по-человечески, 1–3 простых предложения. На «ты», если человек на «ты», иначе на «вы». Без длинных тире.
- Консультируй полностью: что умеет сервис, как начать, энергия, AML, карта, обмен.
- Когда человек готов попробовать или спрашивает, где зарегистрироваться, дай ссылку: {REF}
- Если человеку интересно зарабатывать, предложи: «давай структуру построим, тут можно и зарабатывать: 15% с первой линии,
  5% со второй, 2% с третьей». Дохода не обещай.
- Если спросят про рефералку, честно скажи, что ссылка реферальная.
- Если в знаниях нет ответа (например, точная комиссия по карте), скажи, что точную цифру бот показывает перед операцией,
  или ответь ровно «УТОЧНЮ», и владелец ответит сам.
- Никогда не советуй, как обойти AML-проверки бирж или «очистить» рискованную крипту.
- Если спрашивают, бот ли ты, ответь ровно «УТОЧНЮ».
Верни только текст ответа."""


def now():
    return datetime.now(DUBAI)


def quiet():
    return QUIET[0] <= now().hour < QUIET[1]


S = {}


def load():
    global S
    try:
        S = json.load(open(STATE_F, encoding="utf-8"))
    except Exception:
        S = {}
    for k, v in {"mode": "draft", "react": True, "auto": True, "dm": True, "threads": {}, "ours": [], "neg": [],
                 "drafts": {}, "next_draft": 1, "dms": {}, "muted": []}.items():
        S.setdefault(k, v)
    roll()


def roll():
    today = now().date().isoformat()
    if S.get("day") != today:
        S.update(day=today, reacts=0, react_chats={}, replies=0, reply_chats=[], authors=[], scans=0, seen=0, topical=0)


def save():
    S["ours"] = S["ours"][-1000:]
    S["neg"] = [t for t in S["neg"] if t > time.time() - 86400]
    json.dump(S, open(STATE_F, "w", encoding="utf-8"), ensure_ascii=False)


client = TelegramClient(os.path.join(BASE, "co"), int(ENV["API_ID"]), ENV["API_HASH"])
ME = {}


async def notify(text):
    """Уведомления AR: на его основной аккаунт (задаётся командой /owner @username в Избранном), иначе в Избранное."""
    try:
        m = await client.send_message(S.get("owner") or "me", "🤖 " + text[:3900])
        if S.get("owner"):
            S["ours"].append([S["owner"], m.id]); save()
        return m
    except Exception as e:
        log.warning("notify: %s", e)


async def llm(messages, max_tokens=300, json_mode=False):
    body = {"messages": messages, "temperature": 0.6, "max_tokens": max_tokens}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    async with httpx.AsyncClient(timeout=90) as c:
        for m in MODELS:
            try:
                r = await c.post("https://openrouter.ai/api/v1/chat/completions",
                                 headers={"Authorization": f"Bearer {ENV['OPENROUTER_KEY']}", "X-Title": "Cryptooffice assistant"},
                                 json={**body, "model": m})
                if r.status_code == 200:
                    return r.json()["choices"][0]["message"]["content"].strip()
                log.warning("llm %s: %s %s", m, r.status_code, r.text[:200])
            except Exception as e:
                log.warning("llm %s: %s", m, e)
    return ""


def clean(t, limit):
    t = (t or "").strip().strip('"«»')
    t = t.replace("—", ",").replace("–", ",")
    t = re.sub(r"https?://\S+|t\.me/\S+|@officeapp", "", t)   # в чатах ссылок не бывает
    t = re.sub(r"(?i)[^.!?]*(профил|описани\w* аккаунт|в био)[^.!?]*[.!?]?", "", t)
    t = re.sub(r"\s+", " ", t).strip(" ,")
    sents = re.findall(r"[^.!?…]+(?:\.\.\.|[.!?…])?", t)
    out = ""
    for snt in sents[:2]:
        cand = (out + " " + snt.strip()).strip()
        if len(cand) > max(limit, 40):
            break
        out = cand
    return out


async def is_admin(chat_id, uid):
    try:
        p = await client.get_permissions(chat_id, uid)
        return bool(p.is_admin or p.is_creator)
    except Exception:
        return False


def suspicious(sender, text):
    if not isinstance(sender, types.User) or sender.bot or getattr(sender, "scam", False) or getattr(sender, "fake", False):
        return True
    return bool(SCAMMY_RE.search(text))


async def owner_wrote(chat_id, after_id):
    """AR сам написал в чат с этого аккаунта после сообщения: тогда не вмешиваемся."""
    try:
        async for m in client.iter_messages(chat_id, from_user="me", min_id=after_id, limit=20):
            if [chat_id, m.id] not in S["ours"]:
                return True
    except Exception as e:
        log.warning("owner check: %s", e)
    return False


async def send_ours(chat_id, text, reply_to=None):
    m = await client.send_message(chat_id, text, reply_to=reply_to)
    S["ours"].append([chat_id, m.id]); save()
    return m


# ---------- реакции ----------

ALLOWED = {}


async def allowed_emoji(chat_id):
    """Какие реакции разрешены в чате: None = любые, [] = никакие."""
    if chat_id not in ALLOWED:
        try:
            peer = await client.get_input_entity(chat_id)
            if isinstance(peer, types.InputPeerChannel):
                full = (await client(functions.channels.GetFullChannelRequest(peer))).full_chat
            else:
                full = (await client(functions.messages.GetFullChatRequest(peer.chat_id))).full_chat
            ar = full.available_reactions
            if isinstance(ar, types.ChatReactionsSome):
                ALLOWED[chat_id] = [x.emoticon for x in ar.reactions if isinstance(x, types.ReactionEmoji)]
            elif isinstance(ar, types.ChatReactionsAll):
                ALLOWED[chat_id] = None
            else:
                ALLOWED[chat_id] = []
        except Exception as e:
            log.warning("reactions of %s: %s", chat_id, e)
            ALLOWED[chat_id] = None
    return ALLOWED[chat_id]


async def react(chat_id, msg_id, emoji=None):
    roll()
    if not S["react"] or quiet() or S["reacts"] >= REACT_DAILY or S["react_chats"].get(str(chat_id), 0) >= REACT_PER_CHAT:
        return
    ok = await allowed_emoji(chat_id)
    if ok == []:
        return
    pick = [e for e in ([emoji] if emoji else EMOJI) if ok is None or e in ok] or (ok[:1] if ok else [])
    if not pick:
        return
    # место в лимите занимаем сразу, чтобы пачка сообщений не обошла лимит
    S["reacts"] += 1; S["react_chats"][str(chat_id)] = S["react_chats"].get(str(chat_id), 0) + 1; save()
    await asyncio.sleep(random.randint(*REACT_DELAY))
    if quiet():
        return
    try:
        await client(functions.messages.SendReactionRequest(peer=chat_id, msg_id=msg_id,
                                                            reaction=[types.ReactionEmoji(emoticon=random.choice(pick))]))
        log.info("react ok: %s %s", await chat_title(chat_id), msg_id)
    except Exception as e:
        log.warning("react %s: %s", chat_id, e)


# ---------- ответы в чатах ----------

async def deliver(chat_id, reply_to, text, thread, label):
    """draft: черновик в Избранное; live: пауза, потом отправка, если AR не вмешался."""
    if S["mode"] == "draft":
        n = S["next_draft"]; S["next_draft"] += 1
        S["drafts"][str(n)] = {"chat": chat_id, "reply_to": reply_to, "text": text, "thread": thread, "ts": time.time()}
        save()
        m = await notify(f"{label}\nЧерновик #{n}:\n«{text}»\n\nОтветь на это сообщение «+», чтобы отправить, или «-», чтобы отменить.")
        if m:
            S.setdefault("draft_msgs", {})[str(m.id)] = str(n); save()
        return
    await asyncio.sleep(random.randint(*(REPLY_DELAY if thread["depth"] == 1 else FOLLOW_DELAY)))
    if not S["auto"] or quiet() or await owner_wrote(chat_id, reply_to):
        return
    await post_reply(chat_id, reply_to, text, thread)
    await notify(f"{label}\nОтправил:\n«{text}»")


async def post_reply(chat_id, reply_to, text, thread):
    m = await send_ours(chat_id, text, reply_to)
    thread = dict(thread); thread["history"] = thread.get("history", []) + [text]
    S["threads"][f"{chat_id}:{m.id}"] = thread; save()


async def chat_title(chat_id):
    try:
        e = await client.get_entity(chat_id)
        return getattr(e, "title", "") or str(chat_id)
    except Exception:
        return str(chat_id)


async def on_group(ev, text):
    roll()
    S["seen"] = S.get("seen", 0) + 1
    if not TOPIC_RE.search(text):
        return
    S["topical"] = S.get("topical", 0) + 1
    if S["scans"] >= SCAN_DAILY:
        return
    sender = await ev.get_sender()
    if suspicious(sender, text):
        return
    # лайк по теме ставим сразу, без нейросети
    if not BOT_Q_RE.search(text) and not NEG_RE.search(text):
        asyncio.create_task(react(ev.chat_id, ev.id))
    S["scans"] += 1; save()
    hist = []
    try:
        async for m in client.iter_messages(ev.chat_id, limit=6, max_id=ev.id):
            if m.raw_text:
                hist.append(m.raw_text[:300])
    except Exception:
        pass
    title = await chat_title(ev.chat_id)
    msgs = [{"role": "system", "content": CHAT_STYLE},
            {"role": "user", "content": CLASSIFY.format(title=title, history="\n".join(f"- {h}" for h in reversed(hist)) or "(нет)",
                                                       text=text[:1500])}]
    raw = await llm(msgs, 400, json_mode=True)
    try:
        res = json.loads(re.search(r"\{.*\}", raw, re.S).group(0))
    except Exception:
        return
    score = int(res.get("score", 0) or 0)
    if score < 4 or not S["auto"] or quiet():
        return
    if S["replies"] >= REPLY_DAILY or ev.chat_id in S["reply_chats"] or sender.id in S["authors"]:
        return
    if BOT_Q_RE.search(text) or await is_admin(ev.chat_id, sender.id):
        return
    draft = clean(res.get("reply", ""), int(len(text) * 0.7) if len(text) > 60 else 80)
    if not draft:
        return
    S["replies"] += 1; S["reply_chats"].append(ev.chat_id); S["authors"].append(sender.id); save()
    thread = {"depth": 1, "root": text[:800], "author": sender.id, "history": []}
    await deliver(ev.chat_id, ev.id, draft, thread, f"Чат «{title}». Человек пишет:\n«{text[:600]}»")


async def on_reply_to_us(ev, rm, text):
    th = S["threads"].get(f"{ev.chat_id}:{rm.id}")
    if not th:
        return  # это писал сам AR, не вмешиваемся
    title = await chat_title(ev.chat_id)
    if BOT_Q_RE.search(text) or NEG_RE.search(text):
        neg = NEG_RE.search(text) is not None
        if neg:
            S["neg"].append(time.time())
        th["stopped"] = True; save()
        await notify(("⚠️ Негатив на наш ответ" if neg else "❓ Спрашивают, не бот ли это") +
                     f" в «{title}». Сам не отвечаю, ветку остановил.\n«{text[:500]}»")
        if len([t for t in S["neg"] if t > time.time() - 86400]) >= 3:
            S["auto"] = False; save()
            await notify("⛔ За сутки 3 негативных реакции. Поставил ответы в чатах на паузу. Включить: /auto on")
        return
    if th.get("stopped") or th["depth"] >= MAX_DEPTH or not S["auto"] or quiet():
        return
    if ev.sender_id != th["author"] and await is_admin(ev.chat_id, ev.sender_id):
        return
    depth = th["depth"] + 1
    task = ("Это наше третье и последнее сообщение в ветке. Коротко ответь по сути и добавь: «Пиши в личку, всё расскажу» "
            "(по-английски: «DM me, I'll explain»). Без ссылок." if depth == MAX_DEPTH else "Коротко ответь по сути, как в живом разговоре.")
    if PAID_RE.search(text):
        task += " Человек спрашивает про оплату или рекламу: ответь честно про рефералку по правилам."
    msgs = [{"role": "system", "content": CHAT_STYLE},
            {"role": "user", "content": f"Исходное сообщение человека:\n{th['root']}\n\nНаши ответы:\n" + "\n".join(th["history"]) +
             f"\n\nНовое сообщение в ветке:\n{text[:800]}\n\n{task}\nЕсли отвечать не нужно (просто «спасибо», «ок»), "
             "верни пустую строку. Верни только текст ответа."}]
    reply = clean(await llm(msgs), max(int(len(text) * 0.7), 90))
    if not reply:
        return
    th = dict(th, depth=depth)
    await deliver(ev.chat_id, ev.id, reply, th, f"Ветка в «{title}» ({depth}/{MAX_DEPTH}). Человек ответил:\n«{text[:500]}»")


# ---------- личка ----------

RUNNING = set()


async def on_dm(ev, text):
    uid = ev.chat_id
    if not S["dm"] or uid in S["muted"] or uid in RUNNING:
        return
    sender = await ev.get_sender()
    if not isinstance(sender, types.User) or sender.bot or sender.id == 777000:
        return
    cv = S["dms"].setdefault(str(uid), {"last_ours": 0})
    RUNNING.add(uid)
    try:
        active = time.time() - cv.get("last_ours", 0) < DM_ACTIVE
        await asyncio.sleep(random.uniform(1, 3) if active else random.randint(*DM_DELAY))
        hist = []
        async for m in client.iter_messages(uid, limit=30):
            if m.raw_text:
                hist.append({"role": "assistant" if m.out else "user", "content": m.raw_text[:1500]})
        hist.reverse()
        if hist and hist[-1]["role"] == "assistant":
            return  # уже ответили (или AR ответил сам)
        reply = (await llm([{"role": "system", "content": DM_SYSTEM}] + hist, 500)).replace("—", ",")
        if not reply:
            return
        if reply.strip().upper().startswith("УТОЧНЮ"):
            await client.send_message(uid, "Уточню и вернусь.")
            cv["last_ours"] = time.time(); S["muted"].append(uid); save()
            name = sender.first_name or sender.username or uid
            await notify(f"❓ В личке {name} (id {uid}) спрашивает то, чего нет в базе:\n«{text[:800]}»\n"
                         f"Ответь ему сам. В этом диалоге я замолчал, вернуть: /unmute {uid}")
            return
        async with client.action(uid, "typing"):
            await asyncio.sleep(min(2 + len(reply) / 25, 8))
        m = await client.send_message(uid, reply)
        S["ours"].append([uid, m.id]); cv["last_ours"] = time.time(); save()
    except Exception as e:
        log.exception("dm: %s", e)
    finally:
        RUNNING.discard(uid)


# ---------- события ----------

@client.on(events.NewMessage(incoming=True))
async def on_incoming(ev):
    text = ev.raw_text or ""
    if not text.strip():
        return
    try:
        if ev.is_private:
            if S.get("owner") and ev.chat_id == S["owner"]:
                await owner_command(ev, text.strip())
                return
            asyncio.create_task(on_dm(ev, text))
            return
        if not ev.is_group:
            return
        if ev.is_reply:
            rm = await ev.get_reply_message()
            if rm and rm.out:
                if re.search(r"(?i)спасибо|согласен|точно|плюсую|\+1|в точку", text):
                    asyncio.create_task(react(ev.chat_id, ev.id, "👍"))
                asyncio.create_task(on_reply_to_us(ev, rm, text))
                return
        asyncio.create_task(on_group(ev, text))
    except Exception as e:
        log.exception("incoming: %s", e)


@client.on(events.NewMessage(outgoing=True))
async def on_outgoing(ev):
    # AR сам написал кому-то в личку с этого аккаунта: в этом диалоге ассистент замолкает
    if ev.is_private and ev.chat_id not in (ME.get("id"), S.get("owner")) and [ev.chat_id, ev.id] not in S["ours"]:
        await asyncio.sleep(2)
        if [ev.chat_id, ev.id] not in S["ours"] and ev.chat_id not in S["muted"]:
            S["muted"].append(ev.chat_id); save()
        return
    if ev.chat_id != ME.get("id"):
        return
    await command((ev.raw_text or "").strip())


async def owner_command(ev, t):
    """Сообщение с основного аккаунта AR: «+» / «-» ответом на черновик или команда."""
    if ev.is_reply and t in ("+", "-", "ок", "ok", "да", "нет"):
        n = S.get("draft_msgs", {}).get(str(ev.reply_to_msg_id))
        if n:
            await command(("/ok " if t in ("+", "ок", "ok", "да") else "/skip ") + n)
            return
    await command(t)


async def command(t):
    if t.lower().startswith("/owner"):
        name = t.split()[1] if len(t.split()) > 1 else ""
        try:
            u = await client.get_entity(name)
            S["owner"] = u.id; save()
            await notify("Теперь уведомления и черновики приходят сюда. Ответь на черновик «+», чтобы отправить. /status — что сделано.")
        except Exception as e:
            await client.send_message("me", f"🤖 Не нашёл {name}: {e}. Сначала напиши этому аккаунту что-нибудь со своего основного.")
        return
    if not t.startswith("/"):
        return
    parts = t.split()
    cmd, arg = parts[0].lower(), (parts[1].lower() if len(parts) > 1 else "")
    roll()
    if cmd == "/status":
        groups = 0
        async for d in client.iter_dialogs():
            if d.is_group:
                groups += 1
        await notify(f"Чатов: {groups}. Сегодня увидел сообщений: {S.get('seen', 0)}, по нашей теме: {S.get('topical', 0)}, "
                     f"проверено нейросетью: {S['scans']}/{SCAN_DAILY}.\n"
                     f"Режим: {S['mode']}. Реакции: {'вкл' if S['react'] else 'выкл'} ({S['reacts']}/{REACT_DAILY}). "
                     f"Ответы в чатах: {'вкл' if S['auto'] else 'выкл'} ({S['replies']}/{REPLY_DAILY}). "
                     f"Личка: {'вкл' if S['dm'] else 'выкл'}. Черновиков ждут: {len(S['drafts'])}.")
    elif cmd == "/mode" and arg in ("draft", "live"):
        S["mode"] = arg; save(); await notify(f"Режим: {arg}")
    elif cmd in ("/react", "/auto", "/dm") and arg in ("on", "off"):
        S[cmd[1:]] = arg == "on"; save(); await notify(f"{cmd[1:]}: {arg}")
    elif cmd == "/unmute" and arg.lstrip("-").isdigit():
        S["muted"] = [x for x in S["muted"] if x != int(arg)]; save(); await notify("Снова отвечаю в этом диалоге")
    elif cmd in ("/ok", "/skip") and arg in S["drafts"]:
        d = S["drafts"].pop(arg); save()
        if cmd == "/ok":
            try:
                await post_reply(d["chat"], d["reply_to"], d["text"], d["thread"]); await notify(f"Отправил #{arg}")
            except Exception as e:
                await notify(f"Не получилось отправить #{arg}: {e}")
        else:
            await notify(f"Отменил #{arg}")


async def main():
    load()
    await client.connect()
    if not await client.is_user_authorized():
        log.error("нет входа в аккаунт: запусти python assistant.py --login")
        await asyncio.sleep(300)
        return
    me = await client.get_me()
    ME["id"] = me.id
    log.info("started as %s", me.username or me.id)
    await notify(f"Запустился. Режим {S['mode']}: ответы в чатах приходят сюда черновиками. Команды: /status, /mode live, /react off, /dm off.")
    await client.run_until_disconnected()


async def qr_login():
    """Вход по QR, если код из Telegram не приходит: Настройки → Устройства → Подключить устройство."""
    import getpass
    import qrcode
    from telethon.errors import SessionPasswordNeededError
    await client.connect()
    if not await client.is_user_authorized():
        qr = await client.qr_login()
        while True:
            q = qrcode.QRCode(border=1)
            q.add_data(qr.url)
            print("\nНа телефоне в аккаунте-ассистенте: Настройки → Устройства → Подключить устройство, и наведи камеру на QR:\n")
            q.print_ascii(invert=True)
            try:
                await qr.wait(timeout=60)
                break
            except asyncio.TimeoutError:
                print("QR устарел, показываю новый...")
                await qr.recreate()
            except SessionPasswordNeededError:
                await client.sign_in(password=getpass.getpass("Облачный пароль аккаунта: "))
                break
    me = await client.get_me()
    print(f"Вход выполнен: {me.first_name} @{me.username or ''}")
    await client.disconnect()


if __name__ == "__main__":
    if "--qr" in sys.argv:
        client.loop.run_until_complete(qr_login())
    elif "--login" in sys.argv:
        async def login():
            await client.start()
            me = await client.get_me()
            print(f"Вход выполнен: {me.first_name} @{me.username or ''}")
            await client.disconnect()
        client.loop.run_until_complete(login())
    else:
        client.loop.run_until_complete(main())
