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


# ===== Рассылка писем с alexey@fortex-uae.com напрямую через Google Workspace (решение Александра 26.11, вместо Instantly) =====
# Очередь и тексты: mail/queue.json в репозитории (enabled, daily_limit, window, steps по сегментам, leads).
# Состояние отправок хранится на сервере (mail_state.json), раз в день копия уходит в репозиторий mail/state.json.
# Пароль приложения Google: файл mail_pass (бот: /igdm mail <пароль>, сообщение с паролем удаляется).
# Ответы: IMAP раз в 5 минут, письмо остаётся непрочитанным в ящике, владелец получает уведомление 🔴.
MAIL_USER = "alexey@fortex-uae.com"
MAIL_STATE_F = os.path.join(BASE, "mail_state.json")
MS = {}
STOP_WORDS = ("не интерес", "неинтерес", "не актуал", "неактуал", "не пишите", "отпишите", "unsubscribe", "remove me", "not interested", "stop")


def mail_pass():
    try:
        return open(os.path.join(BASE, "mail_pass")).read().strip().replace(" ", "")
    except Exception:
        return ""


def ms_load():
    global MS
    try:
        MS = json.load(open(MAIL_STATE_F))
    except Exception:
        MS = {}
    for k, v in (("leads", {}), ("sent_day", ""), ("sent_n", 0), ("last_send", 0), ("seen_uids", []), ("last_imap", 0),
                 ("report_day", ""), ("push_day", ""), ("queue", None), ("queue_at", 0)):
        MS.setdefault(k, v)


def ms_save():
    json.dump(MS, open(MAIL_STATE_F, "w"), ensure_ascii=False, indent=1)


def _render(t, lead):
    name = (lead.get("name") or "").strip()
    out = (t.replace("{hello}", f"Здравствуйте, {name}!" if name else "Здравствуйте!")
            .replace("{name}", name).replace("{company}", lead.get("company") or "вашей компании")
            .replace("{personal}", (lead.get("personal") or "").strip()))
    while "\n\n\n" in out:
        out = out.replace("\n\n\n", "\n\n")
    return out.strip() + "\n"


def smtp_send(to, subject, body, reply_to_id=None):
    import smtplib, ssl, email.utils
    from email.message import EmailMessage
    m = EmailMessage()
    m["From"] = f"Алексей Ронин <{MAIL_USER}>"
    m["To"] = to
    m["Subject"] = subject
    mid = email.utils.make_msgid(domain="fortex-uae.com")
    m["Message-ID"] = mid
    if reply_to_id:
        m["In-Reply-To"] = reply_to_id
        m["References"] = reply_to_id
    m.set_content(body)
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context(), timeout=60) as sm:
        sm.login(MAIL_USER, mail_pass())
        sm.send_message(m)
    return mid


async def mail_queue():
    """Очередь из репозитория, не чаще раза в 10 минут."""
    import content
    if MS.get("queue") is None or time.time() - MS.get("queue_at", 0) > 600:
        raw, _ = await content.gh_get("mail/queue.json")
        if raw:
            MS["queue"] = json.loads(raw)
        MS["queue_at"] = time.time()
    return MS.get("queue") or {}


async def mail_send_tick():
    q = await mail_queue()
    if not q.get("enabled") or not mail_pass():
        return
    now = datetime.now(DUBAI)
    day = now.date().isoformat()
    if MS["sent_day"] != day:
        MS["sent_day"], MS["sent_n"] = day, 0
    w = q.get("window", [10, 17])
    if now.weekday() >= 5 or not (w[0] <= now.hour < w[1]) or MS["sent_n"] >= int(q.get("daily_limit", 25)):
        return
    import random
    if time.time() - MS["last_send"] < MS.get("gap", 600):
        return
    steps = q.get("steps", {})
    # сначала догоняющие письма, у которых подошёл срок, потом новые
    due, new = [], []
    for ld in q.get("leads", []):
        st = MS["leads"].get(ld["email"].lower(), {})
        if st.get("status") in ("replied", "bounced", "stopped", "done"):
            continue
        seq = steps.get(ld.get("segment")) or steps.get("default") or []
        k = st.get("step", 0)
        if k >= len(seq):
            continue
        if k == 0:
            new.append((ld, st, seq, k))
        elif time.time() >= st.get("next_at", 0):
            due.append((ld, st, seq, k))
    pick = (due or new or [None])[0]
    if not pick:
        return
    ld, st, seq, k = pick
    tpl = seq[k]
    subj = st.get("subject") or _render(tpl["subject"], ld)
    if k > 0:
        subj = subj if subj.lower().startswith("re:") else "Re: " + subj
    try:
        mid = await asyncio.get_event_loop().run_in_executor(None, smtp_send, ld["email"], subj, _render(tpl["body"], ld), st.get("mid"))
    except Exception as e:
        log.warning("mail send %s: %s", ld["email"], e)
        MS["last_send"] = time.time(); MS["gap"] = 1800
        if "Username and Password not accepted" in str(e) or "535" in str(e):
            q["enabled"] = False
            await CTX["notify"]("🔴 Рассылка остановлена: Google не принял пароль приложения для alexey@fortex-uae.com. Пришли новый: /igdm mail <пароль>")
        ms_save()
        return
    st.update({"step": k + 1, "last_at": time.time(), "subject": st.get("subject") or subj, "mid": st.get("mid") or mid,
               "status": "active" if k + 1 < len(seq) else "done", "id": ld.get("id")})
    if k + 1 < len(seq):
        st["next_at"] = time.time() + float(seq[k + 1].get("after_days", 3)) * 86400
    MS["leads"][ld["email"].lower()] = st
    MS["sent_n"] += 1
    MS["last_send"] = time.time()
    MS["gap"] = random.randint(9, 18) * 60
    ms_save()


def _imap_fetch(since_uid_list):
    import imaplib, email, email.utils
    from email.header import decode_header, make_header
    out = []
    M = imaplib.IMAP4_SSL("imap.gmail.com", 993)
    M.login(MAIL_USER, mail_pass())
    M.select("INBOX", readonly=True)
    since = (datetime.now(DUBAI) - timedelta(days=3)).strftime("%d-%b-%Y")
    typ, data = M.uid("search", None, f"(SINCE {since})")
    for uid in (data[0].split() if data and data[0] else []):
        u = uid.decode()
        if u in since_uid_list:
            continue
        typ, msg = M.uid("fetch", uid, "(BODY.PEEK[])")
        if not msg or not msg[0]:
            continue
        e = email.message_from_bytes(msg[0][1])
        frm = email.utils.parseaddr(e.get("From", ""))[1].lower()
        subj = str(make_header(decode_header(e.get("Subject", ""))))
        body = ""
        for part in (e.walk() if e.is_multipart() else [e]):
            if part.get_content_type() == "text/plain":
                try:
                    body = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", "replace")
                except Exception:
                    pass
                break
        text = "\n".join(l for l in body.splitlines() if not l.startswith(">"))[:1500]
        out.append({"uid": u, "from": frm, "subject": subj, "text": text, "raw": body[:4000]})
    M.logout()
    return out


async def mail_imap_tick():
    if not mail_pass() or time.time() - MS["last_imap"] < 300:
        return
    MS["last_imap"] = time.time()
    try:
        msgs = await asyncio.get_event_loop().run_in_executor(None, _imap_fetch, list(MS["seen_uids"]))
    except Exception as e:
        log.warning("imap: %s", e); ms_save(); return
    import html as _h
    q = MS.get("queue") or {}
    by_mail = {ld["email"].lower(): ld for ld in q.get("leads", [])}
    for m in msgs:
        MS["seen_uids"].append(m["uid"])
        frm = m["from"]
        if frm.startswith(("mailer-daemon", "postmaster")) or "delivery status notification" in m["subject"].lower():
            for addr in by_mail:
                if addr in m["raw"].lower():
                    MS["leads"].setdefault(addr, {})["status"] = "bounced"
            continue
        if frm in by_mail or frm in MS["leads"]:
            st = MS["leads"].setdefault(frm, {})
            stop = any(w in m["text"].lower() for w in STOP_WORDS)
            st["status"] = "stopped" if stop else "replied"
            st["reply_at"] = time.time()
            ld = by_mail.get(frm, {})
            await CTX["notify"](
                f"<b>🔴 Ответ на письмо</b>\n\n• От: {_h.escape(frm)}" + (f" ({_h.escape(ld.get('company',''))})" if ld.get("company") else "")
                + f"\n• Тема: {_h.escape(m['subject'])}\n\n{_h.escape(m['text'][:900])}\n\n"
                + ("<i>Человек просит не писать: рассылку ему остановил.</i>" if stop else
                   "<i>Цепочка для него остановлена. Ответить можно из почты alexey@fortex-uae.com (Gmail).</i>"),
                parse_mode="html")
    MS["seen_uids"] = MS["seen_uids"][-2000:]
    ms_save()


async def mail_daily():
    """17:30 по Дубаю: короткий итог дня владельцу и копия состояния в репозиторий."""
    now = datetime.now(DUBAI)
    day = now.date().isoformat()
    if (now.hour, now.minute) < (17, 30) or MS["report_day"] == day:
        return
    MS["report_day"] = day
    q = MS.get("queue") or {}
    if not q.get("enabled"):
        ms_save(); return
    vals = list(MS["leads"].values())
    total = len(q.get("leads", []))
    started = sum(1 for v in vals if v.get("step", 0) > 0)
    rep = sum(1 for v in vals if v.get("status") == "replied")
    stop = sum(1 for v in vals if v.get("status") == "stopped")
    bnc = sum(1 for v in vals if v.get("status") == "bounced")
    today_rep = sum(1 for v in vals if v.get("reply_at", 0) > time.time() - 86400)
    if MS["sent_day"] == day and MS["sent_n"]:
        await CTX["notify"](f"<b>✉️ Рассылка за сегодня</b>\n\n• Отправлено: {MS['sent_n']}\n• Ответили сегодня: {today_rep}\n\n"
                            f"<b>Всего</b>\n• Начали цепочку: {started} из {total}\n• Ответили: {rep}, просили не писать: {stop}\n• Не доставлено: {bnc}",
                            parse_mode="html")
    try:
        import content
        raw, sha = await content.gh_get("mail/state.json")
        await content.gh_put("mail/state.json", json.dumps({"updated": now.isoformat(timespec="minutes"), "leads": MS["leads"]},
                             ensure_ascii=False, indent=1), sha, "Рассылка: состояние за день")
    except Exception as e:
        log.warning("mail state push: %s", e)
    ms_save()


async def mail_tick():
    if not MS:
        ms_load()
    for f in (mail_send_tick, mail_imap_tick, mail_daily):
        try:
            await f()
        except Exception:
            log.exception("mail %s", f.__name__)


async def loop():
    load()
    await asyncio.sleep(90)
    while True:
        try:
            await outbox()
        except Exception:
            log.exception("outbox")
        await mail_tick()
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
