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
DAILY = int(os.environ.get("REACTIONS_DAILY", "15"))
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
    return f"Реакции: {'включены' if s.get('on', True) else 'выключены'}. Сегодня {s['total']} из {DAILY}"


def pick(text):
    if SAD_RE.search(text):
        return ["🙏", "🤝", "👍"]
    if WIN_RE.search(text):
        return ["🔥", "👍", "🤝"]
    return ["👍", "🤝", "🔥"]


async def maybe_react(user, chat_id, msg_id, author_id, text):
    s = _load()
    if not s.get("on", True) or s["total"] >= DAILY or s["chats"].get(str(chat_id), 0) >= PER_CHAT or author_id in s["users"]:
        return
    # бронируем слот сразу, чтобы параллельные сообщения не превысили лимит
    s["total"] += 1; s["chats"][str(chat_id)] = s["chats"].get(str(chat_id), 0) + 1; s["users"].append(author_id); _save(s)
    await asyncio.sleep(random.randint(*DELAY))
    h = datetime.now(DUBAI).hour
    if QUIET[0] <= h < QUIET[1]:
        await asyncio.sleep(((QUIET[1] - h) * 3600) + random.randint(300, 2400))
    for emo in pick(text):
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
