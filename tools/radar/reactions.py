"""Автоматические реакции аккаунта радара на сообщения по нашим темам.
Лимиты: не больше DAILY в сутки на весь аккаунт, PER_CHAT в одном чате, 1 на одного человека в сутки.
Реакция ставится со случайной задержкой, как живой человек. Выключить: /reactions off в боте."""
import asyncio, json, logging, os, random, re, time
from datetime import datetime, timedelta, timezone

from telethon.tl.functions.messages import SendReactionRequest
from telethon.tl.types import ReactionEmoji

log = logging.getLogger("reactions")
BASE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(BASE, "reactions.json")
DUBAI = timezone(timedelta(hours=4))
DAILY = int(os.environ.get("REACTIONS_DAILY", "25"))
PER_CHAT = 3
DELAY = (60, 600)
QUIET = (1, 8)  # ночью по Дубаю не реагируем, люди так не делают

SAD_RE = re.compile(r"отказ|отказал|заблок|закрыл|закрыва|не могу|не получа|проблем|помогите|подскажите,? пожалуйста|беда|морозят|заморозил", re.I)
WIN_RE = re.compile(r"получилось|открыли|открыл сч|одобрил|одобрили|удалось|спасибо всем|рекоменд", re.I)


def _load():
    try:
        s = json.load(open(STATE))
    except Exception:
        s = {}
    today = datetime.now(DUBAI).date().isoformat()
    if s.get("day") != today:
        s = {"day": today, "total": 0, "chats": {}, "users": [], "on": s.get("on", True), "log": []}
    return s


def _save(s):
    json.dump(s, open(STATE, "w"), ensure_ascii=False)


def set_on(on):
    s = _load(); s["on"] = bool(on); _save(s)


def status():
    s = _load()
    rich = s.get("rich", [])
    lines = [f"Реакции: {'включены' if s.get('on', True) else 'выключены'}. Сегодня {s['total']} из {DAILY}",
             f"Ресурсным людям вне темы: {len(rich)} (проверено нейросетью {s.get('scans', 0)} из {SCAN_DAILY})"]
    for t, ch, mid, emo, w, why in rich[-5:]:
        lines.append(f"{emo} {w}/5 · {why}")
    return "\n".join(lines)


ALLOWED = ("👍", "🔥", "💯", "😁")

# ---------- реакции «ресурсным» людям даже не по нашей теме ----------
# Логика: человек с деньгами и международным бизнесом (видно по контексту его сообщений) получает уместную реакцию
# от аккаунта радара. Любопытство «кто это поставил» приводит его к нам. Один человек не чаще раза в 14 дней.
WEALTH_RE = re.compile(
    r"бизнес|компани|фирм|офис|сотрудник|команд[ау]|поставщик|контракт|оборот|выручк|прибыл|инвест|недвиж|квартир|вилл|апарт|"
    r"застройщ|off.?plan|golden|золот\w* виз|резидент|внж|переезд|релокац|семь[ёеи]|частн\w* школ|яхт|porsche|mercedes|bmw|"
    r"range rover|бизнес.?класс|импорт|экспорт|логист|склад|товар|маркетплейс|крипт|трейд|фонд|актив|капитал|траст|"
    r"счёт|счет|банк|кредитк|ипотек|офшор|холдинг|франшиз|ресторан|клиник|стартап|IT|разработ|агентств", re.I)
SCAN_DAILY = 150          # не больше проверок нейросетью в сутки
USER_COOLDOWN = 14 * 86400
SEEN_F = os.path.join(BASE, "reacted_users.json")
SCAN_MODELS = ["google/gemini-2.5-flash", "openai/gpt-4.1-mini", "anthropic/claude-haiku-4.5"]
WEALTH_PROMPT = """Ты помогаешь компании в Дубае (корпоративные и личные счета в банках ОАЭ, рабочие визы и Emirates ID, компании, ВНЖ; чек от 2 000 до 10 000 USD) находить в Telegram-чатах ресурсных людей.
Чат: «{title}».
Последние сообщения этого человека в чате (старые сверху):
{history}
{reply}Новое сообщение:
«{text}»

Оцени человека по всему контексту, даже если тема не про банки и визы:
- wealth 0–5: насколько вероятно, что у него свой бизнес (особенно международный), заметный доход или капитал и он может себе позволить переезд в Дубай, ВНЖ, корпоративный счёт за 5–6 тыс. USD или премиальную кредитку. 5 = явный владелец бизнеса или инвестор; 4 = очень вероятно (бизнес, недвижимость, переезд семьёй, сотрудники, импорт, премиальные покупки); 3 = возможно; 0–2 = нет признаков, студент, наёмный работник с мелкими задачами, ищет подработку или дешёвые услуги.
- ok: можно ли уместно поставить реакцию на ЭТО сообщение. Нельзя (false): жалоба, горе, конфликт, ругань, политика, религия, реклама и самопиар, предупреждение о мошенниках, просьба о помощи в беде, спорное или неверное утверждение, сообщение, где реакция от незнакомца выглядит странно.
- reaction: 💯 человек сказал верную, уверенную мысль, с которой можно согласиться; 🔥 поделился результатом, удачным решением, крутыми новостями или планами; 👍 нормальный вопрос, полезная информация или нейтральное деловое сообщение; 😁 удачно пошутил. Если ok=false, пусто.
Ответь строго JSON: {{"wealth": 0-5, "ok": true|false, "reaction": "💯|🔥|👍|😁|", "why": "до 12 слов"}}"""


def _seen():
    try:
        return json.load(open(SEEN_F))
    except Exception:
        return {}


async def _scan_llm(prompt):
    import httpx
    key = CTX.get("openrouter_key")
    if not key:
        return None
    async with httpx.AsyncClient(timeout=60) as c:
        for m in SCAN_MODELS:
            try:
                r = await c.post("https://openrouter.ai/api/v1/chat/completions",
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                                 json={"model": m, "max_tokens": 120, "temperature": 0.2,
                                       "messages": [{"role": "user", "content": prompt}]})
                t = r.json()["choices"][0]["message"]["content"]
                j = re.search(r"\{.*\}", t, re.S)
                return json.loads(j.group(0)) if j else None
            except Exception as e:
                log.info("scan model %s: %s", m, e)
    return None


CTX = {}


def setup(**kw):
    CTX.update(kw)


async def wealth_scan(user, ev, text):
    """Вызывается на каждое сообщение в группах. Дёшево отсеивает, нейросеть зовёт только при признаках денег."""
    try:
        if ev.out or not ev.is_group or len(text) < 35 or not WEALTH_RE.search(text):
            return
        s = _load()
        if not s.get("on", True) or s["total"] >= DAILY or s["chats"].get(str(ev.chat_id), 0) >= PER_CHAT:
            return
        if s.get("scans", 0) >= SCAN_DAILY:
            return
        uid = ev.sender_id
        if not uid or uid in s["users"] or time.time() - _seen().get(str(uid), 0) < USER_COOLDOWN:
            return
        sender = await ev.get_sender()
        if getattr(sender, "bot", False):
            return
        s["scans"] = s.get("scans", 0) + 1; _save(s)
        hist = []
        async for m in user.iter_messages(ev.chat_id, from_user=uid, limit=8):
            if m.id != ev.id and m.raw_text:
                hist.append(m.raw_text.strip().replace("\n", " ")[:300])
        reply = ""
        if ev.is_reply:
            try:
                rm = await ev.get_reply_message()
                if rm and rm.raw_text:
                    reply = f"Он отвечает на: «{rm.raw_text.strip()[:300]}»\n"
            except Exception:
                pass
        chat = await ev.get_chat()
        prompt = WEALTH_PROMPT.format(title=getattr(chat, "title", ""), history="\n".join(f"- {h}" for h in reversed(hist)) or "(нет)",
                                      reply=reply, text=text[:1200])
        res = await _scan_llm(prompt)
        if not res:
            return
        w, ok, emo = int(res.get("wealth", 0) or 0), bool(res.get("ok")), res.get("reaction") or ""
        log.info("wealth %s ok=%s %s | %s", w, ok, emo, res.get("why", ""))
        if w >= 4 and ok and emo in ALLOWED:
            seen = _seen(); seen[str(uid)] = int(time.time()); json.dump(seen, open(SEEN_F, "w"))
            s = _load(); s.setdefault("rich", []).append([int(time.time()), ev.chat_id, ev.id, emo, w, res.get("why", "")]); _save(s)
            await maybe_react(user, ev.chat_id, ev.id, uid, text, emo)
    except Exception as e:
        log.warning("wealth_scan: %s", e)


def pick(text):
    if WIN_RE.search(text):
        return ["🔥", "💯", "👍"]
    return ["👍", "🔥"]


async def maybe_react(user, chat_id, msg_id, author_id, text, emoji=None):
    s = _load()
    if not s.get("on", True) or s["total"] >= DAILY or s["chats"].get(str(chat_id), 0) >= PER_CHAT or author_id in s["users"]:
        return
    # бронируем слот сразу, чтобы параллельные сообщения не превысили лимит
    s["total"] += 1; s["chats"][str(chat_id)] = s["chats"].get(str(chat_id), 0) + 1; s["users"].append(author_id); _save(s)
    await asyncio.sleep(random.randint(*DELAY))
    h = datetime.now(DUBAI).hour
    if QUIET[0] <= h < QUIET[1]:
        await asyncio.sleep(((QUIET[1] - h) * 3600) + random.randint(300, 2400))
    order = [emoji, "👍"] if emoji else pick(text)
    for emo in dict.fromkeys(order):
        try:
            await user(SendReactionRequest(peer=chat_id, msg_id=msg_id, reaction=[ReactionEmoji(emoticon=emo)]))
            s = _load(); s["log"].append([int(time.time()), chat_id, msg_id, emo]); _save(s)
            log.info("reaction %s in %s/%s", emo, chat_id, msg_id)
            return
        except Exception as e:
            msg = str(e)
            if "REACTION_INVALID" in msg or "REACTION_EMPTY" in msg:
                continue  # в чате разрешены другие реакции, пробуем следующую
            log.warning("reaction failed: %s", msg)
            break
    s = _load(); s["total"] = max(0, s["total"] - 1); _save(s)  # не получилось, слот возвращаем
