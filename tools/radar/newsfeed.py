"""Сборщик новостей Дубая из Telegram-каналов для рилсов.

Аккаунт радара подписан на каналы (/news add @канал). Каждый день в 08:30 по Дубаю
собираем посты за последние 26 часов, сортируем по просмотрам и реакциям
и кладём в репозиторий: news/tg/<ГГГГ-ММ-ДД>.json. Оттуда их берёт задача, которая пишет рилсы.
Тексты каналов используются только как источник фактов, в рилсах пересказываем своими словами.
"""
import asyncio, json, logging, os, time
from datetime import datetime, timedelta, timezone

log = logging.getLogger("newsfeed")
BASE = os.path.dirname(os.path.abspath(__file__))
STATE_F = os.path.join(BASE, "newsfeed.json")
DUBAI = timezone(timedelta(hours=4))
RUN_AT = (8, 30)
CTX = {}
S = {}


def setup(**kw):
    CTX.update(kw)


def load():
    global S
    try:
        S = json.load(open(STATE_F))
    except Exception:
        S = {}
    S.setdefault("channels", ["uaegeneralnews", "dubaimap"])
    S.setdefault("last", "")


def save():
    json.dump(S, open(STATE_F, "w"), ensure_ascii=False, indent=1)


def norm(name):
    name = name.strip()
    for p in ("https://t.me/", "http://t.me/", "t.me/", "@"):
        if name.startswith(p):
            name = name[len(p):]
    return name.strip("/").split("/")[0]


async def ensure_joined(u, ch):
    from telethon.tl.functions.channels import JoinChannelRequest
    try:
        await u(JoinChannelRequest(ch))
    except Exception as e:
        log.info("join %s: %s", ch, e)


async def collect():
    import content
    u = CTX["user"]
    since = time.time() - 26 * 3600
    items = []
    for ch in S["channels"]:
        try:
            await ensure_joined(u, ch)
            async for m in u.iter_messages(ch, limit=80):
                if not m.date or m.date.timestamp() < since:
                    break
                text = (m.raw_text or "").strip()
                if len(text) < 40:
                    continue
                reacts = 0
                try:
                    reacts = sum(r.count for r in (m.reactions.results if m.reactions else []))
                except Exception:
                    pass
                items.append({"channel": ch, "url": f"https://t.me/{ch}/{m.id}", "date": m.date.astimezone(DUBAI).isoformat(timespec="minutes"),
                              "views": m.views or 0, "forwards": m.forwards or 0, "reactions": reacts, "text": text[:1500]})
        except Exception as e:
            log.warning("channel %s: %s", ch, e)
    items.sort(key=lambda x: x["views"] + 20 * x["forwards"] + 10 * x["reactions"], reverse=True)
    day = datetime.now(DUBAI).date().isoformat()
    data = json.dumps({"date": day, "channels": S["channels"], "items": items[:40]}, ensure_ascii=False, indent=1)
    path = f"news/tg/{day}.json"
    _, sha = await content.gh_get(path)
    await content.gh_put(path, data, sha, f"News feed {day}")
    return len(items)


async def resolve_to(u, to, name=""):
    """Кому отправить: id, @username или ссылка; если не нашли, ищем в диалогах по имени."""
    if "/+" in str(to) or "joinchat/" in str(to):  # закрытый чат по ссылке-приглашению
        from telethon.tl.functions.messages import CheckChatInviteRequest, ImportChatInviteRequest
        from telethon.tl.types import ChatInviteAlready
        h = str(to).rstrip("/").split("/")[-1].lstrip("+")
        try:
            r = await u(CheckChatInviteRequest(h))
            if isinstance(r, ChatInviteAlready):
                return r.chat
            r = await u(ImportChatInviteRequest(h))
            return r.chats[0]
        except Exception as e:
            log.info("invite %s: %s", h, e)
    else:
        try:
            return await u.get_entity(int(to) if str(to).lstrip("-").isdigit() else to)
        except Exception:
            pass
    async for d in u.iter_dialogs(limit=300):
        if (to and str(getattr(d.entity, "id", "")) == str(to).lstrip("-")) or \
           (name and name.lower() in (d.name or "").lower()):
            return d.entity
    return None


async def outbox():
    """Очередь сообщений от имени Алексея: radar/outbox.json в репозитории.
    Запись: {"id", "to" (id, @username или ссылка на чат), "to_name" (запасной поиск по имени диалога), "html", "status": "new"}.
    Отправляем записи со status new, ставим sent/error и пишем владельцу."""
    import content
    raw, sha = await content.gh_get("radar/outbox.json")
    if not raw:
        return
    items = json.loads(raw)
    todo = [it for it in items if it.get("status") == "new"]
    if not todo:
        return
    u = CTX["user"]
    for it in todo:
        try:
            ent = await resolve_to(u, it.get("to", ""), it.get("to_name", ""))
            if not ent:
                raise RuntimeError("получатель не найден")
            m = await u.send_message(ent, it["html"], parse_mode="html", link_preview=False)
            it["status"], it["sent_at"], it["msg_id"] = "sent", datetime.now(DUBAI).isoformat(timespec="minutes"), m.id
            await CTX["notify"](f"✉️ Алексей отправил сообщение «{it['id']}»")
        except Exception as e:
            it["status"], it["error"] = "error", str(e)[:200]
            await CTX["notify"](f"🔴 Алексей не смог отправить «{it['id']}»: {str(e)[:150]}")
    await content.gh_put("radar/outbox.json", json.dumps(items, ensure_ascii=False, indent=1), sha, "Алексей: очередь отправлена")


async def loop():
    load()
    await asyncio.sleep(90)
    while True:
        try:
            await outbox()
        except Exception:
            log.exception("outbox")
        try:
            now = datetime.now(DUBAI)
            day = now.date().isoformat()
            if (now.hour, now.minute) >= RUN_AT and S["last"] != day:
                S["last"] = day; save()
                n = await collect()
                log.info("news collected: %s", n)
        except Exception:
            log.exception("newsfeed")
        await asyncio.sleep(60)


async def command(ev):
    if not S:
        load()
    parts = ev.raw_text.split()
    a = parts[1].lower() if len(parts) > 1 else ""
    if a == "add" and len(parts) > 2:
        for p in parts[2:]:
            ch = norm(p)
            if ch and ch not in S["channels"]:
                S["channels"].append(ch)
                await ensure_joined(CTX["user"], ch)
    elif a == "del" and len(parts) > 2:
        S["channels"] = [c for c in S["channels"] if c != norm(parts[2])]
    elif a == "now":
        await ev.reply("Собираю новости за сутки…")
        n = await collect()
        save()
        return await ev.reply(f"Готово: {n} постов за сутки сохранено для рилсов")
    save()
    await ev.reply("Каналы для новостей рилсов:\n" + "\n".join(f"• @{c}" for c in S["channels"]) +
                   "\n\nСбор каждый день в 08:30.\n/news add @канал\n/news del @канал\n/news now (собрать сейчас)")
