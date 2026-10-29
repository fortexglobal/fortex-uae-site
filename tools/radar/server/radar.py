#!/usr/bin/env python3
"""Fortex UAE — Telegram radar.

User account (Алексей Ронин) reads groups it is a member of, filters messages by
keywords, asks an LLM (OpenRouter) whether the message is a lead and drafts a reply,
then the bot sends the owner: message + draft + buttons. The reply goes out only
after the owner presses «Отправить» (or sends an edited text).
"""
import asyncio, json, os, re, sqlite3, time, logging
from datetime import datetime, timezone

import httpx
from telethon import TelegramClient, events, Button
from telethon.errors import SessionPasswordNeededError, FloodWaitError
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest

import content
import igdm
import starters
import newsfeed
import reactions
import autoreply
BASE = os.path.dirname(os.path.abspath(__file__))
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("radar")


def env(name, default=""):
    return os.environ.get(name, default).strip()


API_ID = int(env("API_ID", "0"))
API_HASH = env("API_HASH")
BOT_TOKEN = env("BOT_TOKEN")
OPENROUTER_KEY = env("OPENROUTER_KEY")
OWNER_USERNAME = env("OWNER_USERNAME").lstrip("@").lower()
MODELS = [m for m in env("MODELS", "anthropic/claude-haiku-4.5,openai/gpt-4o-mini").split(",") if m]
MIN_SCORE = int(env("MIN_SCORE", "3"))
MAX_REPLIES_PER_DAY = int(env("MAX_REPLIES_PER_DAY", "8"))
CHAT_COOLDOWN_H = float(env("CHAT_COOLDOWN_H", "12"))

KEYWORDS = [
    r"сч[её]т", r"банк", r"комплаенс", r"compliance", r"отказ", r"заблокир", r"закрыл[иа]? сч",
    r"emirates ?nbd", r"\bwio\b", r"mashreq", r"\bfab\b", r"\badcb\b", r"\brakbank\b", r"\bubl\b",
    r"\bdib\b", r"\bhsbc\b", r"emirates ?id", r"эмирейтс ?ай ?ди", r"\bвиз[аыу]\b", r"резидент",
    r"virtual ?work", r"удал[её]нк", r"удал[её]нн", r"рабоч(ая|ую) виз", r"переезд", r"переехать",
    r"релокац", r"фризон", r"free ?zone", r"freezone", r"mainland", r"мейнленд", r"лицензи",
    r"открыть компан", r"регистрац\w* компан", r"компани\w* в (дубае|оаэ|эмиратах)", r"налог",
    r"\bvat\b", r"\bндс\b", r"corporate tax", r"зарплат\w* в (дубае|оаэ)", r"ипотек", r"кредитк",
    r"(дубай|оаэ|эмират)",
]
KW_RE = re.compile("|".join(KEYWORDS), re.IGNORECASE)
NEED_UAE_RE = re.compile(r"дуба|оаэ|эмират|uae|dubai|абу|шарджа|фризон|mainland|emirates|wio|nbd|mashreq", re.I)
STRONG_RE = re.compile(r"\bндс\b|\bvat\b|холдинг|контрагент|оборот\w* компан|наша компани|моя компани|зарплатн\w* проект|private banking|золот\w* виз|\bндс\b|\bvat\b|холдинг|контрагент|оборот\w* компан|наша компани|моя компани|зарплатн\w* проект|private banking|золот\w* виз|\bндс\b|\bvat\b|холдинг|контрагент|оборот\w* компан|наша компани|моя компани|зарплатн\w* проект|private banking|золот\w* виз|открыть сч|открыл\w* сч|сч[её]т\w* (за рубеж|за границ|в другой стран|для компан|для бизнес|для ип)|корпоративн\w* сч|расч[её]тн\w* сч|зарубежн\w* (сч|банк|компан)|иностранн\w* (сч|банк|компан)|отказал\w*|отказ в открыт|заблокир\w* сч|закрыл\w* сч|закрыва\w* сч|комплаенс|compliance|нерезидент|где открыть|какой банк|\bвнж\b|вид на жительств|резидентств|резиденц|рабоч\w* виз|virtual ?work|emirates ?id|релокац|переезд\w* (в дуба|в оаэ|в эмират)|открыть компан|зарегистрировать компан|регистрац\w* компан|компани\w* за рубеж|фризон|free ?zone|mainland|платежн\w* агент|платёжн\w* агент|агентск\w* (схем|договор)|\bвэд\b|внешнеэконом|импорт|экспорт|поставщик|китай|кита[яю]|гонконг|hong ?kong|юан|\bcny\b|оплат\w* (поставщик|инвойс|контракт)|инвойс|контракт\w* с (китай|поставщ)|платежи (в китай|за товар|поставщ)|расч[её]т\w* с (китай|поставщ|контрагент)", re.I)

# Переводы денег, обмен, вывод: опасная зона (мошенники, краденые деньги), такие сообщения не берём
EXCLUDE_RE = re.compile(r"обмен\w*|обменник|обнал|\bp2p\b|переведу|перевед[ёе]м|кто (может |сможет )?перевест|нужен перевод|перевод\w* (из росси|в росси|на карт|деньг)|перевест\w* (деньги|средства)|вывест\w* (деньги|средства)|вывод средств|отправить деньги|переслать деньги|принять (платеж|перевод|деньги) на карт|\bдроп|наличн\w* (в|за)|кэш|cash|usdt|тезер|tether|крипт\w* (на|в) (наличн|карт|рубл)", re.I)
KEEP_RE = re.compile(r"внж|резидент|виз[аыу]|emirates ?id|компан|корпоративн|сч[её]т (компан|для бизнес)|платежн\w* агент|платёжн\w* агент|вэд|китай|гонконг|поставщ|инвойс", re.I)

AGREE_RE = re.compile(r"соглас|верно|точно|так и есть|плюсую|поддерживаю|полностью|спасибо|благодар|дельн|по делу|в точку|\+\s*1|👍|💯", re.I)

SYSTEM_PROMPT = """Ты помогаешь Алексею Ронину (Fortex UAE, Дубай, с 2022 года) находить в русскоязычных Telegram-чатах людей, которым нужна наша помощь, и готовишь короткий ответ в чат.

Что делает Fortex UAE (под ключ, со всеми банками ОАЭ):
- корпоративные счета для владельцев с российским паспортом, в том числе сложные случаи: после отказов, крипта и трейдинг, сложные фризоны и лицензии (от 5 000 USD, в кейсах 2–3 недели). Это главное направление;
- рабочая виза с Emirates ID через нашу компанию (от 5 500 USD), с ней Emirates NBD с кредиткой без депозита;
- компании во фризонах и на mainland (от 14 000 / 22 000 AED);
- инфраструктура для платёжных агентов и торговли с Китаем, Гонконгом и другими странами: компания и счета в ОАЭ, юани, быстрые платежи поставщикам (кейс: UBL с юанями за 2,5 недели);
- личный счёт, в том числе удалённо (от 1 500 USD); ВНЖ Virtual Work с Emirates ID (от 2 000 USD, 7–10 дней, самый доступный, но в банках слабее рабочей визы).
Нельзя: обещать 100%, гарантировать конкретный банк, советовать что-то скрыть от банка, упоминать fortex.finance, писать как реклама.

ЦЕЛЕВЫЕ темы (только они):
(1) ВНЖ, резидентство, визы, Emirates ID, переезд в ОАЭ;
(2) банковские счета и инфраструктура: открыть счёт для компании или себя, отказы и закрытия счетов, выбор банка, комплаенс;
(3) открыть компанию в ОАЭ или за рубежом, фризона или mainland;
(4) платёжные агенты, ВЭД, импорт и экспорт, оплата поставщикам, торговля с Китаем, Гонконгом и другими странами, кто ищет или сравнивает инфраструктуру (её можно перевести на ОАЭ).
НЕ РЕЛЕВАНТНО никогда (score 1): переводы денег людям, обмен валют и крипты, вывод средств из России, «кто переведёт», P2P, наличные, просьбы принять деньги на карту, всё похожее на обнал или мошенничество. Также реклама конкурентов, новости, шутки, бытовые вопросы, туристические карты.

ПОПАДАНИЕ (поле hit):
прямое: человек спрашивает или пишет о проблеме именно по счетам и банкам в ОАЭ, ВНЖ и визам ОАЭ, Emirates ID, компаниям в ОАЭ (фризона, mainland, лицензия). Любой человек, не важно, богатый или нет.
косвенное: платёжные агенты, переводы и оплаты за границу, карты, расчёты с Китаем, ВЭД, а также любой разговор человека с деньгами или бизнесом.
нет: всё остальное, в том числе визы и счета других стран без связи с ОАЭ, бытовые темы Дубая (еда, жильё, такси), реклама, новости.

НАШ КЛИЕНТ (главный фильтр): люди с деньгами и бизнесом. Собственники и директора компаний, предприниматели с международным бизнесом, компании в нескольких странах, ВЭД, импорт и экспорт с серьёзными объёмами, платёжные агенты и те, кто строит расчёты с контрагентами, НДС/VAT, холдинги, инвесторы, трейдеры и крипто-проекты с оборотами, люди, которые переезжают с семьёй и капиталом, хотят нормальный банк, кредитку, ипотеку, золотую визу. Признаки: «моя компания», «наши контрагенты», «оборот», «поставки», «инвойсы», «юрлицо», «несколько стран», «холдинг», «зарплатный проект», крупные суммы (от десятков тысяч долларов), премиальные банки (Emirates NBD, Mashreq, ADCB, FAB, private banking).
НЕ НАШ КЛИЕНТ (score 1–2, даже если тема формально про счёт или карту): мелкие личные задачи на небольшие деньги. Например, оформить армянскую, киргизскую, казахскую или другую зарубежную карту за 15–30 тысяч рублей, пополнить китайскую карту или UnionPay на 10 тысяч, оплатить подписку или отель за границей, «где дешевле карта», студенты и туристы, поиск самого дешёвого способа. Такие люди не купят услугу за тысячи долларов.
Если по сообщению непонятно, бизнес это или мелкая личная задача, смотри на контекст чата и формулировки; при сомнениях ставь не выше 3.

РЕАКЦИЯ (поле reaction): ставим только людям с деньгами и бизнесом (tier бизнес или состоятельный частный) в разговоре по нашим темам, прямо или косвенно. Иначе пусто.
💯 или 🔥 — человек высказал мысль или факт, который совпадает с нашим опытом и с которым мы согласны и уверены (например: «банки ОАЭ смотрят прежде всего на источник средств», «с рабочей визой счёт открыть проще», «держать всё на одной бирже рискованно»). 💯 для точного экспертного утверждения, 🔥 для сильного кейса, результата или удачного решения.
😁 — человек из нашей аудитории в обсуждении по нашей теме удачно пошутил.
👍 — человек сказал что-то по нашей теме (прямо или косвенно), что мы можем подтвердить, поделился полезным опытом или задал толковый вопрос.
Не ставим реакцию на рекламу, жалобы на мошенников, политику, мелкие личные задачи (дешёвые карты, мелкие переводы) и спорные или неверные утверждения.

Оцени сообщение и ответь строго JSON без пояснений:
{"relevant": true|false, "score": 1-5, "hit": "прямое|косвенное|нет", "tier": "бизнес|состоятельный частный|мелкий|непонятно", "reaction": "👍|🔥|💯|😁 или пусто", "topic": "счёт|ВНЖ|компания|ВЭД|другое", "said": "суть сообщения одной фразой", "meaning": "что это значит для нас: кто человек (бизнес или частник, примерный масштаб), какая у него задача и чем мы можем помочь, 1–2 фразы", "reply": "черновик ответа или пустая строка"}
score: 5 — бизнес или состоятельный человек с прямым запросом по целевой теме (отказ банка компании, нужен корпоративный счёт, ВНЖ с переездом, компания в ОАЭ, платёжный агент или расчёты с Китаем на объёмах); 4 — конкретный вопрос по целевой теме от бизнеса или состоятельного человека; 3 — обсуждение по целевой теме, где виден бизнес-контекст и можно дать дельный совет; 1–2 — мелкие личные задачи, нецелевые темы, не отвечать.

Правила ответа (reply): пиши как живой человек в чате, который в теме, но без пафоса («я не главный эксперт, просто кое-что знаю»). Ответ КОРОТКИЙ: 1–2 предложения, в каждом 5–7 слов максимум, без портянок; каждое предложение уйдёт отдельным сообщением, без кавычек. Конкретика (сроки, «с паспортом РФ открывают», цифры) лучше общих слов; цены почти никогда, чтобы не забанили за рекламу. Пишешь от имени Алексея: живёт в Дубай Марине, в Дубае с 2022 года, с командой помогает с банками, визами и компаниями; можно коротко и по-свойски, с лёгкой иронией, но разговор мягко ведёт к задаче человека. Всего 1–3 предложения. Ответ НИКОГДА не длиннее сообщения, на которое отвечаем; иногда одно предложение. «:)» почти никогда: примерно один ответ из 10 и только если это реально шутка. Можно многоточие. Вопрос редко, примерно в каждом третьем ответе. Чаще просто короткое мнение или факт. Иногда лёгкая ирония, в том числе про скамеров и мутных посредников в таких чатах (мы на стороне добра). Никогда не пиши «по опыту». Без канцелярита, без эмодзи-картинок (только «:)»), без длинных тире, без ссылок, без контактов, без «пишите в личку» и без цен (в крайнем случае «от X» по ориентирам выше). Можно спокойно и уверенно говорить, что в ОАЭ это решаемо: счета с российским паспортом, с Emirates ID и без, компании, криптосчета, сложные виды деятельности. Не обещай 100% и конкретный банк. Не советуй ничего скрывать от банка, только законные пути (компания и счёт в ОАЭ, зарплата себе через рабочую визу). Никогда не спорь, всегда на позитиве. Не упоминай Fortex. Примеры: «С русским паспортом открывают. Но не везде. Компания уже есть?» / «В Дубае с этим проще. Главное источник средств.»"""


# ---------------- storage ----------------
db = sqlite3.connect(os.path.join(BASE, "radar.db"))
db.execute("create table if not exists kv(k text primary key, v text)")
db.execute("""create table if not exists leads(id integer primary key autoincrement, ts real, chat_id integer,
 chat_title text, msg_id integer, author text, author_id integer, text text, score integer, topic text,
 draft text, status text, link text)""")
db.execute("create table if not exists seen(chat_id integer, msg_id integer, primary key(chat_id,msg_id))")
db.commit()


def kv_get(k, d=None):
    r = db.execute("select v from kv where k=?", (k,)).fetchone()
    return r[0] if r else d


def kv_set(k, v):
    db.execute("insert or replace into kv values(?,?)", (k, str(v)))
    db.commit()


user = TelegramClient(os.path.join(BASE, "user"), API_ID, API_HASH)
bot = TelegramClient(os.path.join(BASE, "bot"), API_ID, API_HASH)
login_client = TelegramClient(os.path.join(BASE, "user"), API_ID, API_HASH, receive_updates=False)
AUTHED = {"v": False}

state = {"login": None, "phone": None, "edit": {}}


def owner_id():
    v = kv_get("owner_id")
    return int(v) if v else None


def is_owner(sender):
    oid = owner_id()
    if oid:
        return sender.id == oid
    return False


async def notify(text, **kw):
    oid = owner_id()
    if oid:
        try:
            return await bot.send_message(oid, text, link_preview=False, **kw)
        except Exception as e:
            log.warning("notify failed: %s", e)


# ---------------- LLM ----------------
async def ask_llm(chat_title, text):
    payload_msgs = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Чат: {chat_title}\nСообщение:\n{text[:3000]}"},
    ]
    async with httpx.AsyncClient(timeout=60) as c:
        for model in MODELS:
            try:
                r = await c.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={"Authorization": f"Bearer {OPENROUTER_KEY}", "Content-Type": "application/json",
                             "HTTP-Referer": "https://fortex-uae.com", "X-Title": "Fortex Radar"},
                    json={"model": model, "messages": payload_msgs, "temperature": 0.3, "max_tokens": 600},
                )
                if r.status_code != 200:
                    log.warning("LLM %s -> %s %s", model, r.status_code, r.text[:200])
                    continue
                out = r.json()["choices"][0]["message"]["content"]
                m = re.search(r"\{.*\}", out, re.S)
                if not m:
                    continue
                return json.loads(m.group(0))
            except Exception as e:
                log.warning("LLM error %s: %s", model, e)
    return None


# ---------------- limits ----------------
def replies_today():
    start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    return db.execute("select count(*) from leads where status='sent' and ts>=?", (start,)).fetchone()[0]


def chat_recently_replied(chat_id):
    since = time.time() - CHAT_COOLDOWN_H * 3600
    return db.execute("select count(*) from leads where status='sent' and chat_id=? and ts>=?",
                      (chat_id, since)).fetchone()[0] > 0


def clean_draft(t):
    t = autoreply.short7((t or "").strip().strip('"«»'))
    t = t.replace(" — ", ", ").replace(" – ", ", ").replace("—", "-").replace("–", "-")
    while t.endswith(".") and not t.endswith(".."):
        t = t[:-1].rstrip()
    return t


# ---------------- user account: watching ----------------
CHATS_OFF = True  # решение Александра 29.10: вся активность в чатах выключена (чтение, лиды, реакции, ответы, посол Дубая). Работает только личка
@user.on(events.NewMessage(incoming=True))
async def on_group_message(ev):
    try:
        if CHATS_OFF or kv_get("paused") == "1" or not ev.is_group:  # 29.10: в чатах ничего не читаем и не делаем
            return
        text = ev.raw_text or ""
        if ev.is_reply:
            try:
                rm = await ev.get_reply_message()
                if rm and rm.out:
                    if AGREE_RE.search(text):
                        asyncio.get_event_loop().create_task(reactions.maybe_react(user, ev.chat_id, ev.id, ev.sender_id, text, "👍"))
                    asyncio.get_event_loop().create_task(autoreply.on_reply_to_us(user, ev, rm, text))
                    return
            except Exception as e:
                log.warning("reply check: %s", e)
        asyncio.get_event_loop().create_task(reactions.wealth_scan(user, ev, text))
        asyncio.get_event_loop().create_task(autoreply.maybe_ambassador(user, ev, text))
        if len(text) < 20:
            return
        sender = await ev.get_sender()
        if sender is None or getattr(sender, "bot", False):
            return
        chat = await ev.get_chat()
        title = getattr(chat, "title", "чат")
        # chats not about UAE: require a UAE mention
        if not (NEED_UAE_RE.search(text) or STRONG_RE.search(text) or (NEED_UAE_RE.search(title) and KW_RE.search(text))):
            return
        if EXCLUDE_RE.search(text) and not KEEP_RE.search(text):
            return
        if db.execute("select 1 from seen where chat_id=? and msg_id=?", (ev.chat_id, ev.id)).fetchone():
            return
        db.execute("insert or ignore into seen values(?,?)", (ev.chat_id, ev.id)); db.commit()

        res = await ask_llm(title, text)
        if res:
            asyncio.get_event_loop().create_task(autoreply.maybe_visibility(user, ev, sender, text, res))
        if res and res.get("reaction") in reactions.ALLOWED and res.get("tier") in ("бизнес", "состоятельный частный"):
            asyncio.get_event_loop().create_task(reactions.maybe_react(user, ev.chat_id, ev.id, sender.id, text, res["reaction"]))
        if not res or not res.get("relevant") or int(res.get("score", 0)) < MIN_SCORE:
            return
        uname = getattr(sender, "username", None)
        author = " ".join(x for x in [getattr(sender, "first_name", ""), getattr(sender, "last_name", "")] if x) or "?"
        if uname:
            author += f" (@{uname})"
        link = ""
        if getattr(chat, "username", None):
            link = f"https://t.me/{chat.username}/{ev.id}"
        else:
            link = f"https://t.me/c/{str(ev.chat_id).replace('-100', '')}/{ev.id}"
        draft = clean_draft(await autoreply.shorten(res.get("reply", "")))  # один раз: в карточке и при «Отправить» один и тот же текст
        cur = db.execute(
            "insert into leads(ts,chat_id,chat_title,msg_id,author,author_id,text,score,topic,draft,status,link) values(?,?,?,?,?,?,?,?,?,?,?,?)",
            (time.time(), ev.chat_id, title, ev.id, author, sender.id, text, int(res.get("score", 0)),
             res.get("topic", ""), draft, "new", link))
        db.commit()
        lid = cur.lastrowid
        warn = ""
        if chat_recently_replied(ev.chat_id):
            warn = f"\n• В этом чате уже отвечали за последние {CHAT_COOLDOWN_H:g} ч, лучше пропустить"
        if replies_today() >= MAX_REPLIES_PER_DAY:
            warn += f"\n• Дневной лимит ответов ({MAX_REPLIES_PER_DAY}) исчерпан"
        import html as _h
        e = lambda x: _h.escape(str(x or ""))
        said = text if len(text) <= 280 else text[:270].rsplit(" ", 1)[0] + "…"
        meaning = (res.get("meaning") or res.get("why", "")).strip()
        if len(meaning) > 160:
            meaning = meaning[:155].rsplit(" ", 1)[0] + "…"
        msg = (f"<b>🎯 Лид #{lid} · {e(res.get('score'))}/5 · {e(res.get('topic',''))} · {e(res.get('tier',''))}</b>\n"
               f"{e(title)} · {e(author)} · <a href=\"{e(link)}\">открыть</a>\n\n"
               f"<b>💬 Что написал</b>\n{e(said)}\n\n"
               + (f"<b>🧠 Что это значит</b>\n{e(meaning)}\n\n" if meaning else "")
               + f"<b>✍️ Предлагаю ответить</b> (нажми, чтобы скопировать)\n<code>{e(draft)}</code>"
               + (f"\n\n<b>⚠️ Внимание</b>{e(warn)}" if warn else ""))
        await notify(msg, parse_mode="html", buttons=[
            [Button.inline("✅ Отправить", f"send:{lid}".encode()), Button.inline("✏️ Изменить", f"edit:{lid}".encode())],
            [Button.inline("👍 Реакция", f"react:{lid}".encode()), Button.inline("❌ Отказать", f"skip:{lid}".encode())],
        ])
        asyncio.get_event_loop().create_task(autoreply.maybe_auto_reply(user, ev, sender, text, res, lid, db))
    except Exception as e:
        log.exception("watch error: %s", e)


async def send_reply(lid, text):
    row = db.execute("select chat_id,msg_id,status from leads where id=?", (lid,)).fetchone()
    if not row:
        return "Лид не найден."
    chat_id, msg_id, status = row
    if status == "sent":
        return "Уже отправлено."
    try:
        await autoreply._send(user, chat_id, text, msg_id)
    except FloodWaitError as e:
        return f"Telegram просит подождать {e.seconds} сек. Попробуйте позже."
    except Exception as e:
        return f"Не удалось отправить: {e}"
    db.execute("update leads set status='sent', draft=?, ts=? where id=?", (text, time.time(), lid)); db.commit()
    return "✅ Отправлено в чат."


# ---------------- bot: owner interface ----------------
HELP = ("Команды:\n/status — состояние\n/login — подключить аккаунт радара\n/chats — чаты в радаре\n"
        "/join ссылка — вступить в чат (не больше 3–5 в день)\n/pause и /resume — пауза\n/stats — статистика\n/reactions — автореакции (on/off)\n/auto — автоответы в чатах (on/off)")


@bot.on(events.NewMessage(pattern=r"^/start"))
async def cmd_start(ev):
    s = await ev.get_sender()
    if not owner_id():
        uname = (getattr(s, "username", "") or "").lower()
        if OWNER_USERNAME and uname != OWNER_USERNAME:
            return await ev.reply("Этот бот приватный.")
        kv_set("owner_id", s.id)
    if not is_owner(s):
        return await ev.reply("Этот бот приватный.")
    authed = AUTHED["v"]
    await ev.reply("Радар Fortex UAE на связи.\n" + ("Аккаунт радара подключён." if authed else "Аккаунт радара ещё не подключён — отправьте /login") + "\n\n" + HELP)


@bot.on(events.NewMessage(pattern=r"^/login"))
async def cmd_login(ev):
    if not is_owner(await ev.get_sender()):
        return
    if AUTHED["v"]:
        return await ev.reply("Аккаунт уже подключён.")
    state["login"] = "phone"
    await ev.reply("Пришлите номер телефона аккаунта радара (Алексей Ронин) в формате +971XXXXXXXXX")


@bot.on(events.NewMessage(pattern=r"^/status"))
async def cmd_status(ev):
    if not is_owner(await ev.get_sender()):
        return
    authed = AUTHED["v"]
    me = await user.get_me() if authed else None
    await ev.reply(f"Аккаунт: {'подключён — ' + (me.first_name or '') if me else 'не подключён'}\n"
                   f"Пауза: {'да' if kv_get('paused') == '1' else 'нет'}\n"
                   f"Ответов сегодня: {replies_today()}/{MAX_REPLIES_PER_DAY}")


@bot.on(events.NewMessage(pattern=r"^/pause"))
async def cmd_pause(ev):
    if is_owner(await ev.get_sender()):
        kv_set("paused", "1"); await ev.reply("Радар на паузе.")


@bot.on(events.NewMessage(pattern=r"^/resume"))
async def cmd_resume(ev):
    if is_owner(await ev.get_sender()):
        kv_set("paused", "0"); await ev.reply("Радар снова работает.")


@bot.on(events.NewMessage(pattern=r"^/auto"))
async def cmd_auto(ev):
    if not is_owner(await ev.get_sender()):
        return
    arg = (ev.raw_text.split() + [""])[1].lower()
    if arg in ("on", "вкл"):
        autoreply.set_on(True)
    elif arg in ("off", "выкл"):
        autoreply.set_on(False)
    await ev.reply(autoreply.status() + "\nВключить: /auto on, выключить: /auto off")


@bot.on(events.NewMessage(pattern=r"^/reactions"))
async def cmd_reactions(ev):
    if not is_owner(await ev.get_sender()):
        return
    arg = (ev.raw_text.split() + [""])[1].lower()
    if arg in ("on", "вкл"):
        reactions.set_on(True)
    elif arg in ("off", "выкл"):
        reactions.set_on(False)
    await ev.reply(reactions.status() + "\nВключить: /reactions on, выключить: /reactions off")


@bot.on(events.NewMessage(pattern=r"^/stats"))
async def cmd_stats(ev):
    if not is_owner(await ev.get_sender()):
        return
    rows = db.execute("select status,count(*) from leads where ts>=? group by status", (time.time() - 7 * 86400,)).fetchall()
    d = dict(rows)
    await ev.reply(f"За 7 дней: найдено {sum(d.values())}, отправлено {d.get('sent',0)}, пропущено {d.get('skip',0)}, без решения {d.get('new',0)}")


@bot.on(events.NewMessage(pattern=r"^/chats"))
async def cmd_chats(ev):
    if not is_owner(await ev.get_sender()):
        return
    if not AUTHED["v"]:
        return await ev.reply("Сначала /login")
    names = [d.name for d in await user.get_dialogs(limit=300) if d.is_group]
    await ev.reply(f"Групп в радаре: {len(names)}\n" + "\n".join("• " + n for n in names[:100]))


@bot.on(events.NewMessage(pattern=r"^/join"))
async def cmd_join(ev):
    if not is_owner(await ev.get_sender()):
        return
    parts = ev.raw_text.split(maxsplit=1)
    if len(parts) < 2:
        return await ev.reply("Формат: /join https://t.me/имя_чата")
    link = parts[1].strip()
    try:
        m = re.search(r"t\.me/(?:joinchat/|\+)([\w-]+)", link)
        if m:
            await user(ImportChatInviteRequest(m.group(1)))
        else:
            name = re.sub(r"^(https?://)?t\.me/", "", link).strip("/@ ")
            await user(JoinChannelRequest(name))
        await ev.reply("Вступил. Если в чате нужно одобрение админа — дождитесь его.")
    except FloodWaitError as e:
        await ev.reply(f"Telegram ограничил вступления, подождите {e.seconds // 60} мин.")
    except Exception as e:
        await ev.reply(f"Не получилось: {e}")


@bot.on(events.CallbackQuery)
async def on_button(ev):
    if not is_owner(await ev.get_sender()):
        return
    if ev.data.startswith(b"c"):
        return await content.on_button(ev)
    if ev.data.startswith(b"adel:"):
        _, ch, mid = ev.data.decode().split(":")
        res = await autoreply.delete_message(user, int(ch), int(mid))
        return await ev.answer(res)
    action, lid = ev.data.decode().split(":")
    lid = int(lid)
    if action == "send":
        draft = db.execute("select draft from leads where id=?", (lid,)).fetchone()
        res = await send_reply(lid, draft[0] if draft else "")
        await ev.answer(res[:180], alert=False)
        await ev.reply(f"Лид #{lid}: {res}")
    elif action == "skip":
        db.execute("update leads set status='skip' where id=?", (lid,)); db.commit()
        await ev.answer("Отказ: без ответа и без реакции")
        await ev.edit(buttons=None)
    elif action == "react":
        row = db.execute("select chat_id,msg_id from leads where id=?", (lid,)).fetchone()
        db.execute("update leads set status='react' where id=?", (lid,)); db.commit()
        try:
            from telethon.tl.functions.messages import SendReactionRequest
            from telethon.tl.types import ReactionEmoji
            await user(SendReactionRequest(peer=row[0], msg_id=row[1], reaction=[ReactionEmoji(emoticon="👍")]))
            await ev.answer("👍 Поставил реакцию, без ответа")
        except Exception as ex:
            await ev.answer(f"Реакция не встала: {str(ex)[:120]}", alert=True)
        await ev.edit(buttons=None)
    elif action == "edit":
        state["edit"][ev.sender_id] = lid
        await ev.reply(f"Пришли свой текст для #{lid}: нажми на текст ответа в карточке, он скопируется, вставь сюда и поправь. Отправлю в чат по одному предложению")


PHOTO_LOCK = asyncio.Lock()


@bot.on(events.NewMessage(func=lambda e: e.is_private and bool(e.photo)))
async def on_owner_photo(ev):
    """Живые фото Александра для Threads: сохраняем в репозиторий threads/photos/, ежедневная задача Threads берёт их в посты."""
    s = await ev.get_sender()
    if not is_owner(s):
        return
    try:
        import content
        data = await ev.download_media(bytes)
        name = f"threads/photos/{datetime.now(content.DUBAI).strftime('%Y%m%d-%H%M%S')}-{ev.id}.jpg"
        await content.gh_put(name, data, None, "Threads: живое фото от Александра")
        async with PHOTO_LOCK:  # альбом приходит пачкой: пишем очередь по одному
            raw, sha = await content.gh_get("threads/photos/inbox.json")
            inbox = json.loads(raw) if raw else []
            inbox.append({"file": name, "caption": (ev.raw_text or "").strip(), "album": str(ev.grouped_id or ""),
                          "at": datetime.now(content.DUBAI).isoformat(timespec="minutes"), "used": False})
            await content.gh_put("threads/photos/inbox.json", json.dumps(inbox, ensure_ascii=False, indent=1), sha, "Threads: фото в очередь")
        if not ev.grouped_id or ev.raw_text:
            await ev.reply(f"📸 Сохранил для Threads (в очереди: {sum(1 for x in inbox if not x['used'])}). "
                           "Можно добавить подпись к фото: что это и где, я сделаю из этого пост")
    except Exception as e:
        log.warning("owner photo: %s", e)
        await ev.reply(f"Не смог сохранить фото: {e}")


@bot.on(events.NewMessage(func=lambda e: e.is_private and not (e.raw_text or "").startswith("/")))
async def on_owner_text(ev):
    s = await ev.get_sender()
    if not is_owner(s):
        return
    if ev.photo:
        return  # фото обрабатывает on_owner_photo
    text = ev.raw_text.strip()
    # login flow
    if state["login"] == "phone":
        state["phone"] = re.sub(r"[^\d+]", "", text)
        try:
            await login_client.send_code_request(state["phone"])
            state["login"] = "code"
            await ev.reply("Telegram прислал код в аккаунт радара. Пришлите его сюда С ПРОБЕЛАМИ между цифрами, например: 1 2 3 4 5 "
                           "(иначе Telegram аннулирует код).")
        except Exception as e:
            state["login"] = None
            await ev.reply(f"Ошибка: {e}")
        return
    if state["login"] == "code":
        code = re.sub(r"\D", "", text)
        try:
            await login_client.sign_in(state["phone"], code)
            state["login"] = None
            await ev.reply("✅ Аккаунт радара подключён. Перезапускаюсь на 15 секунд, потом вступайте в чаты (вручную или /join).")
            asyncio.get_event_loop().call_later(2, os._exit, 0)
        except SessionPasswordNeededError:
            state["login"] = "password"
            await ev.reply("У аккаунта включён облачный пароль. Пришлите его (сообщение удалю).")
        except Exception as e:
            state["login"] = None
            await ev.reply(f"Ошибка входа: {e}. Начните заново: /login")
        try:
            await ev.delete()
        except Exception:
            pass
        return
    if state["login"] == "password":
        try:
            await login_client.sign_in(password=text)
            state["login"] = None
            await ev.reply("✅ Аккаунт радара подключён. Перезапускаюсь на 15 секунд.")
            asyncio.get_event_loop().call_later(2, os._exit, 0)
        except Exception as e:
            state["login"] = None
            await ev.reply(f"Ошибка: {e}. Начните заново: /login")
        try:
            await ev.delete()
        except Exception:
            pass
        return
    if await igdm.maybe_handle(ev, text):
        return
    if await content.maybe_handle(ev, text):
        return
    # edited reply
    lid = state["edit"].pop(s.id, None)
    if lid:
        res = await send_reply(lid, text)
        await ev.reply(f"Лид #{lid}: {res}")
        return
    # голос или текст от владельца = мысль для контента
    if ev.voice or ev.audio:
        await ev.reply("Расшифровываю голосовое…")
        note = await transcribe(ev)
        if not note:
            await ev.reply("Не получилось расшифровать. Попробуйте ещё раз или напишите текстом")
            return
        await save_note(ev, note)
        return
    if len(text) >= 20:
        await save_note(ev, text)
        return
    await ev.reply(HELP)


async def transcribe(ev):
    """Голосовое от владельца -> текст через OpenRouter (Gemini понимает аудио)."""
    import base64, subprocess, tempfile
    path = await ev.download_media(file=tempfile.gettempdir() + "/")
    data_path, fmt = path, "ogg"
    try:
        mp3 = path.rsplit(".", 1)[0] + ".mp3"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", path, "-ac", "1", "-ar", "16000", "-b:a", "48k", mp3], check=True, timeout=180)
        data_path, fmt = mp3, "mp3"
    except Exception as e:
        log.warning("ffmpeg: %s", e)
    b64 = base64.b64encode(open(data_path, "rb").read()).decode()
    prompt = ("Расшифруй это голосовое сообщение на русском дословно по смыслу. Расставь знаки препинания и абзацы, "
              "убери слова-паразиты (ну, короче, вот, типа), ничего не добавляй от себя. Верни только текст.")
    async with httpx.AsyncClient(timeout=240) as c:
        for model in ["google/gemini-2.5-flash", "google/gemini-2.5-pro"]:
            try:
                r = await c.post("https://openrouter.ai/api/v1/chat/completions",
                    headers={"Authorization": f"Bearer {OPENROUTER_KEY}", "Content-Type": "application/json",
                             "HTTP-Referer": "https://fortex-uae.com", "X-Title": "Fortex Radar"},
                    json={"model": model, "temperature": 0, "messages": [{"role": "user", "content": [
                        {"type": "text", "text": prompt},
                        {"type": "input_audio", "input_audio": {"data": b64, "format": fmt}}]}]})
                if r.status_code == 200:
                    return r.json()["choices"][0]["message"]["content"].strip()
                log.warning("transcribe %s -> %s %s", model, r.status_code, r.text[:200])
            except Exception as e:
                log.warning("transcribe error %s: %s", model, e)
    return None


async def save_note(ev, note):
    """Заметка владельца для контента: в базу и копией боту от аккаунта радара (чтобы её забрал сборщик контента)."""
    db.execute("create table if not exists notes(id integer primary key, ts real, text text)")
    db.execute("insert into notes(ts, text) values(?, ?)", (time.time(), note)); db.commit()
    if ev.voice or ev.audio:
        try:
            me = await bot.get_me()
            for i in range(0, len(note), 3800):
                await user.send_message(me.username, "#заметка\n" + note[i:i + 3800])
        except Exception as e:
            log.warning("note relay failed: %s", e)
    await ev.reply("Записал мысль для контента ✅\n\n" + note[:3500])


@bot.on(events.NewMessage(pattern=r"^/igdm"))
async def cmd_igdm(ev):
    if is_owner(await ev.get_sender()):
        await igdm.command(ev)


@bot.on(events.NewMessage(pattern=r"^/starters"))
async def cmd_starters(ev):
    if is_owner(await ev.get_sender()):
        await starters.command(ev)


@bot.on(events.NewMessage(pattern=r"^/news"))
async def cmd_news(ev):
    if is_owner(await ev.get_sender()):
        await newsfeed.command(ev)


async def main():
    await bot.start(bot_token=BOT_TOKEN)
    reactions.setup(openrouter_key=OPENROUTER_KEY)
    autoreply.setup(openrouter_key=OPENROUTER_KEY, notify=notify,
                    buttons=lambda c, m: [[Button.inline("🗑 Удалить", f"adel:{c}:{m}".encode())]])
    igdm.setup(openrouter_key=OPENROUTER_KEY, notify=notify, transcribe=transcribe, user=user)
    asyncio.get_event_loop().create_task(igdm.loop())
    starters.setup(user=user, notify=notify, openrouter_key=OPENROUTER_KEY, bot_token=BOT_TOKEN, owner_id=owner_id)
    asyncio.get_event_loop().create_task(starters.loop())
    asyncio.get_event_loop().create_task(autoreply.survival_loop(user))
    newsfeed.setup(user=user, notify=notify)
    asyncio.get_event_loop().create_task(newsfeed.loop())
    content.setup(bot_token=BOT_TOKEN, openrouter_key=OPENROUTER_KEY, owner_id=owner_id,
                  kv_get=kv_get, kv_set=kv_set, transcribe=transcribe)
    asyncio.get_event_loop().create_task(content.scheduler())
    await login_client.connect()
    AUTHED["v"] = await login_client.is_user_authorized()
    if AUTHED["v"]:
        await login_client.disconnect()
        await user.connect()
        await user.get_dialogs(limit=50)
        log.info("user authorized")
        await notify("Радар перезапущен и работает.")
        await asyncio.gather(bot.run_until_disconnected(), user.run_until_disconnected())
    else:
        log.info("user not authorized yet")
        await notify("Радар запущен. Подключите аккаунт: /login")
        await bot.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
