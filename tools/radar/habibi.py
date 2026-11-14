"""Хабиби: бот «ранний доступ» для теста рекламы.
Знакомство из 3 вопросов -> человек в списке первых. Метка креатива: https://t.me/<бот>?start=c1 ... c5
Каждый новый человек приходит владельцу карточкой (владелец один раз жмёт /start в этом боте).
Команды владельца: /stats (сводка по креативам), /export (файл со всеми ответами).
Конфиг: /opt/radar/habibi.env (HABIBI_TOKEN=...)   Запуск: systemd habibi.service
"""
import asyncio, base64, csv, io, json, logging, os, time
import httpx

BASE = os.path.dirname(os.path.abspath(__file__))
OWNER_ID = 5887750248
CONTACT = "Fortex_Dubai"
GH_REPO = "fortexglobal/fortex-uae-site"
LOG = os.path.join(BASE, "habibi_leads.jsonl")
STATE_P = os.path.join(BASE, "habibi_state.json")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("habibi")


def token():
    for line in open(os.path.join(BASE, "habibi.env")):
        if line.startswith("HABIBI_TOKEN="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("no HABIBI_TOKEN in habibi.env")


API = f"https://api.telegram.org/bot{token()}/"

CREATIVE = {"c1": "Садик", "c2": "Первый месяц", "c3": "Жильё", "c4": "Проверенные контакты", "c5": "Свои люди"}
TOPICS = [("home", "🏠 Жильё"), ("kids", "👶 Садик и школа"), ("doc", "🩺 Врачи"), ("visa", "📄 Документы и виза"),
          ("beauty", "💅 Красота и мастера"), ("meet", "☕ Встречи и досуг")]
STAY = [("plan", "Ещё не переехал"), ("m1", "Меньше месяца"), ("m6", "1–6 месяцев"), ("y1", "Полгода–год"), ("y2", "Больше года")]
TL = dict(TOPICS)
SL = dict(STAY)

WELCOME = ("Привет! Я Хабиби 🐪\n\n"
           "Помогаю с жизнью в Дубае: проверенные садики, врачи, мастера, жильё и встречи, с оценками русскоязычного комьюнити.\n\n"
           "<b>Мы открываемся через 2 недели.</b> Вы в списке первых, и при запуске получите <b>20 кредитов</b> в подарок.\n\n"
           "Ответьте на 3 коротких вопроса, чтобы к открытию я подготовил то, что нужно именно вам.")
Q1 = "<b>Вопрос 1 из 3</b>\n\nЧто для вас сейчас важнее всего?"
Q2 = "<b>Вопрос 2 из 3</b>\n\nСколько вы уже в Дубае?"
Q3 = ("<b>Вопрос 3 из 3</b>\n\nНапишите своими словами, что сейчас ищете.\n\n"
      "<i>Например: садик в JLT для ребёнка 4 лет, до 4 000 AED в месяц</i>")
DONE = ("<b>Спасибо! Вы в списке первых ✅</b>\n\n"
        "Напишу, как только откроемся. 20 кредитов уже закреплены за вами.\n\n"
        "Если появится ещё вопрос, просто напишите его сюда, я всё сохраню.")
VISA_TIP = ("\n\nПо документам и визе можно не ждать открытия: наши коллеги из Fortex уже консультируют, "
            f"напишите @{CONTACT}.")

S = {}  # uid -> {"src","name","username","topic","stay","text","extra":[],"t0","step","done"}


def save():
    try:
        json.dump(S, open(STATE_P, "w"), ensure_ascii=False)
    except Exception:
        log.exception("state")


def load():
    global S
    try:
        S = {int(k): v for k, v in json.load(open(STATE_P)).items()}
    except Exception:
        S = {}


async def call(c, method, **data):
    for k, v in list(data.items()):
        if isinstance(v, (dict, list)):
            data[k] = json.dumps(v, ensure_ascii=False)
    r = await c.post(API + method, data=data)
    j = r.json()
    if not j.get("ok"):
        log.warning("%s %s", method, j)
    return j


def kb(rows):
    return {"inline_keyboard": rows}


def who(st, uid):
    return f"@{st['username']}" if st.get("username") else f'<a href="tg://user?id={uid}">{st.get("name") or uid}</a>'


async def finish(c, uid):
    st = S[uid]
    st["step"] = "done"
    text = DONE + (VISA_TIP if st.get("topic") == "visa" else "")
    await call(c, "sendMessage", chat_id=uid, text=text, parse_mode="HTML")
    if not st.get("sent"):
        st["sent"] = True
        st["done"] = time.time()
        rec = {"at": time.strftime("%Y-%m-%d %H:%M"), "uid": uid, "username": st.get("username"), "name": st.get("name"),
               "src": st.get("src"), "topic": st.get("topic"), "stay": st.get("stay"), "text": st.get("text", "")}
        open(LOG, "a").write(json.dumps(rec, ensure_ascii=False) + "\n")
        mark = "🔴 " if st.get("topic") == "visa" else "🧲 "
        await call(c, "sendMessage", chat_id=OWNER_ID, parse_mode="HTML", disable_web_page_preview="true",
                   text=f"{mark}<b>Хабиби: новый человек</b>\n{who(st, uid)}\n"
                        f"Креатив: {CREATIVE.get(st.get('src'), st.get('src') or 'без метки')}\n"
                        f"Важно: {TL.get(st.get('topic'), '—')}\nВ Дубае: {SL.get(st.get('stay'), '—')}\n"
                        f"Ищет: {st.get('text') or '—'}")
    save()


async def on_message(c, m):
    if m["chat"].get("type") != "private":
        return
    uid = m["chat"]["id"]
    text = (m.get("text") or "").strip()
    u = m.get("from", {})
    if text.startswith("/start"):
        src = text.split(" ", 1)[1].strip()[:20] if " " in text else "direct"
        old = S.get(uid)
        if old and old.get("sent"):
            await call(c, "sendMessage", chat_id=uid, parse_mode="HTML",
                       text="Вы уже в списке первых ✅ Напишу, как только откроемся. Вопрос можно написать прямо сюда.")
            return
        S[uid] = {"src": src, "t0": time.time(), "step": "welcome", "extra": [],
                  "name": " ".join(x for x in [u.get("first_name"), u.get("last_name")] if x), "username": u.get("username")}
        save()
        await call(c, "sendMessage", chat_id=uid, text=WELCOME, parse_mode="HTML",
                   reply_markup=kb([[{"text": "Ответить на 3 вопроса", "callback_data": "go"}]]))
        return
    if uid == OWNER_ID and text.startswith("/stats"):
        await call(c, "sendMessage", chat_id=uid, text=stats_text(), parse_mode="HTML")
        return
    if uid == OWNER_ID and text.startswith("/export"):
        await export(c)
        return
    st = S.get(uid)
    if not st:
        await call(c, "sendMessage", chat_id=uid, text="Нажмите /start, чтобы попасть в список первых 🐪")
        return
    if st.get("step") == "q3" and text:
        st["text"] = text[:1000]
        await finish(c, uid)
        return
    if text:
        st.setdefault("extra", []).append(text[:1000])
        save()
        await call(c, "sendMessage", chat_id=uid, text="Записал ✅ Вернусь с ответом к открытию." +
                   (f" По документам и визе можно сразу написать @{CONTACT}." if st.get("topic") == "visa" else ""))
        await call(c, "sendMessage", chat_id=OWNER_ID, parse_mode="HTML", disable_web_page_preview="true",
                   text=f"✉️ <b>Хабиби: вопрос</b> от {who(st, uid)}\n{text[:1000]}")


async def on_callback(c, q):
    uid = q["from"]["id"]
    data = q.get("data", "")
    msg_id = q["message"]["message_id"]
    await call(c, "answerCallbackQuery", callback_query_id=q["id"])
    st = S.setdefault(uid, {"src": "direct", "t0": time.time(), "extra": [], "name": q["from"].get("first_name"),
                            "username": q["from"].get("username")})
    if data == "go":
        st["step"] = "q1"
        await call(c, "editMessageReplyMarkup", chat_id=uid, message_id=msg_id, reply_markup=kb([]))
        rows = [[{"text": l, "callback_data": f"t:{k}"}] for k, l in TOPICS]
        await call(c, "sendMessage", chat_id=uid, text=Q1, parse_mode="HTML", reply_markup=kb(rows))
    elif data.startswith("t:"):
        st["topic"] = data[2:]
        st["step"] = "q2"
        rows = [[{"text": l, "callback_data": f"s:{k}"}] for k, l in STAY]
        await call(c, "editMessageText", chat_id=uid, message_id=msg_id, text=Q2, parse_mode="HTML", reply_markup=kb(rows))
    elif data.startswith("s:"):
        st["stay"] = data[2:]
        st["step"] = "q3"
        await call(c, "editMessageText", chat_id=uid, message_id=msg_id, text=Q3, parse_mode="HTML",
                   reply_markup=kb([[{"text": "Пропустить", "callback_data": "skip"}]]))
    elif data == "skip":
        await call(c, "editMessageReplyMarkup", chat_id=uid, message_id=msg_id, reply_markup=kb([]))
        await finish(c, uid)
    save()


def stats_text():
    rows = [json.loads(l) for l in open(LOG)] if os.path.exists(LOG) else []
    lines = ["<b>Хабиби: сводка</b>", ""]
    for code, name in list(CREATIVE.items()) + [("direct", "без метки")]:
        started = sum(1 for st in S.values() if st.get("src") == code)
        done = sum(1 for r in rows if r.get("src") == code)
        texted = sum(1 for r in rows if r.get("src") == code and r.get("text"))
        if started:
            lines.append(f"<b>{name}</b>: старт {started} · ответили {done} · написали своё {texted}")
    lines += ["", "<b>Что важнее всего</b>"]
    for k, l in TOPICS:
        n = sum(1 for r in rows if r.get("topic") == k)
        if n:
            lines.append(f"{l}: {n}")
    lines += ["", "<b>Сколько в Дубае</b>"]
    for k, l in STAY:
        n = sum(1 for r in rows if r.get("stay") == k)
        if n:
            lines.append(f"{l}: {n}")
    lines += ["", f"Всего стартов: {len(S)} · ответили на все вопросы: {len(rows)}"]
    return "\n".join(lines)


async def export(c):
    rows = [json.loads(l) for l in open(LOG)] if os.path.exists(LOG) else []
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["дата", "ник", "имя", "креатив", "важно", "в Дубае", "ищет", "доп. вопросы"])
    for r in rows:
        st = S.get(r["uid"], {})
        w.writerow([r["at"], r.get("username") or "", r.get("name") or "", CREATIVE.get(r.get("src"), r.get("src")),
                    TL.get(r.get("topic"), ""), SL.get(r.get("stay"), ""), r.get("text", ""), " | ".join(st.get("extra", []))])
    data = buf.getvalue().encode("utf-8-sig")
    await c.post(API + "sendDocument", data={"chat_id": OWNER_ID, "caption": f"Хабиби: {len(rows)} человек"},
                 files={"document": ("habibi.csv", data, "text/csv")})


async def push_stats(c):
    """Обезличенная сводка в репозиторий (без имён, ников и id): stats/habibi.json."""
    try:
        tok = open(os.path.join(BASE, "github_token")).read().strip()
    except Exception:
        return
    rows = [json.loads(l) for l in open(LOG)] if os.path.exists(LOG) else []
    out = {"updated": time.strftime("%Y-%m-%d %H:%M"), "started": {}, "finished": {}, "with_text": {}, "topics": {}, "stay": {},
           "texts": [r["text"] for r in rows if r.get("text")][-200:]}
    for st in S.values():
        k = st.get("src") or "direct"
        out["started"][k] = out["started"].get(k, 0) + 1
    for r in rows:
        k = r.get("src") or "direct"
        out["finished"][k] = out["finished"].get(k, 0) + 1
        if r.get("text"):
            out["with_text"][k] = out["with_text"].get(k, 0) + 1
        out["topics"][r.get("topic")] = out["topics"].get(r.get("topic"), 0) + 1
        out["stay"][r.get("stay")] = out["stay"].get(r.get("stay"), 0) + 1
    body = json.dumps(out, ensure_ascii=False, indent=1).encode()
    h = {"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json", "User-Agent": "fortex-habibi"}
    url = f"https://api.github.com/repos/{GH_REPO}/contents/stats/habibi.json"
    r = await c.get(url, headers=h, params={"ref": "main"})
    sha = r.json().get("sha") if r.status_code == 200 else None
    d = {"message": "Habibi stats", "content": base64.b64encode(body).decode(), "branch": "main"}
    if sha:
        d["sha"] = sha
    r = await c.put(url, headers=h, json=d)
    if r.status_code not in (200, 201):
        log.warning("stats push %s %s", r.status_code, r.text[:200])


async def background(c):
    last_push, last_day = 0, ""
    while True:
        await asyncio.sleep(600)
        if time.time() - last_push > 3 * 3600:
            last_push = time.time()
            try:
                await push_stats(c)
            except Exception:
                log.exception("stats")
        day = time.strftime("%Y-%m-%d", time.gmtime(time.time() + 4 * 3600))
        hour = time.gmtime(time.time() + 4 * 3600).tm_hour
        if hour >= 21 and day != last_day and S:
            last_day = day
            try:
                await call(c, "sendMessage", chat_id=OWNER_ID, text=stats_text(), parse_mode="HTML")
            except Exception:
                log.exception("daily")


async def main():
    load()
    off = 0
    async with httpx.AsyncClient(timeout=70) as c:
        await call(c, "setMyCommands", commands=[{"command": "start", "description": "Попасть в список первых"}])
        asyncio.get_event_loop().create_task(background(c))
        while True:
            try:
                r = await c.get(API + "getUpdates", params={"offset": off, "timeout": 50,
                                                           "allowed_updates": json.dumps(["message", "callback_query"])})
                for u in r.json().get("result", []):
                    off = u["update_id"] + 1
                    try:
                        if "message" in u:
                            await on_message(c, u["message"])
                        elif "callback_query" in u:
                            await on_callback(c, u["callback_query"])
                    except Exception:
                        log.exception("update")
            except Exception:
                log.exception("poll")
                await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(main())
