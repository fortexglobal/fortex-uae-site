"""Бот закрытого клуба (решение Александра 18.11): деловая мужская аудитория, первый вечер сигарный.
Человек отвечает на 6 вопросов -> владельцу приходит карточка с кнопками 1 / 2 / 3 (кого звать первым).
Каждая заявка и уровень пишутся в Google Таблицу (CRM, лист «Клуб: заявки») через веб-хук Apps Script (файл gcal_hook).
Метка рекламы: https://t.me/<бот>?start=<метка>.  Команды владельца: /club (сводка), /export (файл).
Конфиг: /opt/radar/club.env (CLUB_TOKEN=..., CLUB_NAME=...)   Запуск: systemd club.service
"""
import asyncio, csv, html, io, json, logging, os, time
import httpx

BASE = os.path.dirname(os.path.abspath(__file__))
OWNER_ID = 5887750248
STATE_P = os.path.join(BASE, "club_state.json")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("club")


def env():
    d = {}
    for line in open(os.path.join(BASE, "club.env")):
        if "=" in line:
            k, v = line.split("=", 1)
            d[k.strip()] = v.strip()
    return d


ENV = env()
API = f"https://api.telegram.org/bot{ENV['CLUB_TOKEN']}/"
NAME = ENV.get("CLUB_NAME") or "DXB Club"

JOB = [("own", "Свой бизнес"), ("inv", "Инвестиции"), ("top", "Топ-менеджмент"), ("oth", "Другое")]
SPHERE = [("re", "Недвижимость"), ("fin", "Крипта и финансы"), ("it", "IT"), ("trade", "Торговля и ВЭД"), ("oth", "Другое")]
TEAM = [("s", "До 10 человек"), ("m", "10–50"), ("l", "Больше 50"), ("solo", "Работаю один")]
SEEK = [("partners", "Партнёров"), ("invest", "Инвестиции"), ("clients", "Клиентов"), ("circle", "Круг общения")]
LIKES = [("cigar", "Сигары"), ("track", "Автодром"), ("golf", "Гольф"), ("padel", "Падел"), ("yacht", "Яхта")]
L = {k: v for lst in (JOB, SPHERE, TEAM, SEEK, LIKES) for k, v in lst}

WELCOME = (f"<b>{NAME}</b>\n\n"
           "Клуб международных предпринимателей и инвесторов в Дубае.\n\n"
           "Первая встреча: сигарный вечер в лаунже, 12–16 человек. Каждый платит за себя по меню.\n\n"
           "Вход по заявке. Дату пришлём, когда наберётся группа.")
STEPS = [("job", "<b>1 из 6.</b> Чем занимаетесь?", JOB), ("sphere", "<b>2 из 6.</b> Сфера?", SPHERE),
         ("team", "<b>3 из 6.</b> Размер команды?", TEAM), ("seek", "<b>4 из 6.</b> Что сейчас ищете?", SEEK)]
Q_LIKES = "<b>5 из 6.</b> Что ещё интересно? Можно несколько, потом «Готово»"
Q_ABOUT = ("<b>6 из 6.</b> Пара слов о себе или ссылка на Instagram, чтобы мы понимали, кого сажаем рядом.\n\n"
           "<i>Например: девелопмент в Дубае, 8 лет в ОАЭ</i>")
DONE = ("<b>Заявка принята ✅</b>\n\n"
        "Когда наберётся группа, пришлю дату и место. Места получают те, кто подтвердит первым.")

S = {}


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
    j = (await c.post(API + method, data=data)).json()
    if not j.get("ok"):
        log.warning("%s %s", method, j)
    return j


def kb(rows):
    return {"inline_keyboard": rows}


def esc(t):
    return html.escape(str(t or ""))


def tg(st, uid):
    return f"@{st['username']}" if st.get("username") else f'<a href="tg://user?id={uid}">{esc(st.get("name") or uid)}</a>'


def row(st, uid):
    return [st.get("level") or "", st.get("at", ""), st.get("name") or "", ("@" + st["username"]) if st.get("username") else "",
            L.get(st.get("job"), ""), L.get(st.get("sphere"), ""), L.get(st.get("team"), ""), L.get(st.get("seek"), ""),
            ", ".join(L.get(x, x) for x in st.get("likes", [])), st.get("about", ""), st.get("src", ""), str(uid)]


def card_text(st, uid):
    lv = {"1": "1️⃣ звать в первую очередь", "2": "2️⃣ во вторую", "3": "3️⃣ в последнюю"}.get(st.get("level"), "не оценён")
    return (f"🎩 <b>{esc(NAME)}: новая заявка</b>\n\n"
            f"<b>{esc(st.get('name') or '—')}</b> {tg(st, uid)}\n"
            f"• Занятие: {esc(L.get(st.get('job'), '—'))}\n• Сфера: {esc(L.get(st.get('sphere'), '—'))}\n"
            f"• Команда: {esc(L.get(st.get('team'), '—'))}\n• Ищет: {esc(L.get(st.get('seek'), '—'))}\n"
            f"• Интересы: {esc(', '.join(L.get(x, x) for x in st.get('likes', [])) or '—')}\n"
            f"• О себе: {esc(st.get('about') or '—')}\n• Источник: {esc(st.get('src') or '—')}\n\n"
            f"Уровень: <b>{lv}</b>")


def card_kb(uid):
    return kb([[{"text": "1", "callback_data": f"lv:{uid}:1"}, {"text": "2", "callback_data": f"lv:{uid}:2"},
                {"text": "3", "callback_data": f"lv:{uid}:3"}]])


async def to_sheet(c, st, uid):
    try:
        hook = open(os.path.join(BASE, "gcal_hook")).read().strip()
    except Exception:
        log.warning("no gcal_hook")
        return
    try:
        r = await c.post(hook, content=json.dumps({"action": "club", "row": row(st, uid)}, ensure_ascii=False),
                         headers={"Content-Type": "text/plain"}, follow_redirects=True, timeout=60)
        if '"ok":true' not in r.text.replace(" ", ""):
            log.warning("sheet %s %s", r.status_code, r.text[:200])
    except Exception as e:
        log.warning("sheet: %s", e)


async def ask(c, uid, st, msg_id=None):
    step = st.get("step")
    for key, q, opts in STEPS:
        if step == key:
            m = kb([[{"text": l, "callback_data": f"{key}:{k}"}] for k, l in opts])
            if msg_id:
                return await call(c, "editMessageText", chat_id=uid, message_id=msg_id, text=q, parse_mode="HTML", reply_markup=m)
            return await call(c, "sendMessage", chat_id=uid, text=q, parse_mode="HTML", reply_markup=m)
    if step == "likes":
        rows = [[{"text": ("✅ " if k in st.get("likes", []) else "") + l, "callback_data": f"like:{k}"}] for k, l in LIKES]
        rows.append([{"text": "Готово", "callback_data": "likes_done"}])
        return await call(c, "editMessageText", chat_id=uid, message_id=msg_id, text=Q_LIKES, parse_mode="HTML", reply_markup=kb(rows))
    if step == "about":
        return await call(c, "editMessageText", chat_id=uid, message_id=msg_id, text=Q_ABOUT, parse_mode="HTML",
                          reply_markup=kb([[{"text": "Пропустить", "callback_data": "skip"}]]))


async def finish(c, uid):
    st = S[uid]
    st["step"] = "done"
    st["at"] = time.strftime("%Y-%m-%d %H:%M", time.gmtime(time.time() + 4 * 3600))
    save()
    await call(c, "sendMessage", chat_id=uid, text=DONE, parse_mode="HTML")
    if not st.get("sent"):
        st["sent"] = True
        j = await call(c, "sendMessage", chat_id=OWNER_ID, text=card_text(st, uid), parse_mode="HTML",
                       disable_web_page_preview="true", reply_markup=card_kb(uid))
        st["card"] = (j.get("result") or {}).get("message_id")
        save()
    await to_sheet(c, st, uid)


def stats_text():
    done = [s for s in S.values() if s.get("sent")]
    out = [f"<b>{esc(NAME)}: заявки</b>", "", f"• Начали: {len(S)}, заполнили: {len(done)}"]
    for lv in ("1", "2", "3"):
        out.append(f"• Уровень {lv}: {sum(1 for s in done if s.get('level') == lv)}")
    out.append(f"• Не оценены: {sum(1 for s in done if not s.get('level'))}")
    out += ["", "<b>Интересы</b>"]
    for k, l in LIKES:
        out.append(f"• {l}: {sum(1 for s in done if k in s.get('likes', []))}")
    srcs = {}
    for s in done:
        srcs[s.get("src") or "direct"] = srcs.get(s.get("src") or "direct", 0) + 1
    out += ["", "<b>Источники</b>"] + [f"• {esc(k)}: {v}" for k, v in sorted(srcs.items(), key=lambda x: -x[1])]
    return "\n".join(out)


async def export(c):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Уровень", "Дата", "Имя", "Telegram", "Занятие", "Сфера", "Команда", "Ищет", "Интересы", "О себе", "Источник", "uid"])
    for uid, st in sorted(S.items(), key=lambda x: (x[1].get("level") or "9", x[1].get("at", ""))):
        if st.get("sent"):
            w.writerow(row(st, uid))
    await c.post(API + "sendDocument", data={"chat_id": OWNER_ID, "caption": f"{NAME}: заявки"},
                 files={"document": ("club.csv", buf.getvalue().encode("utf-8-sig"), "text/csv")})


async def on_message(c, m):
    if m["chat"].get("type") != "private":
        return
    uid = m["chat"]["id"]
    text = (m.get("text") or "").strip()
    u = m.get("from", {})
    if uid == OWNER_ID and text.startswith("/club"):
        return await call(c, "sendMessage", chat_id=uid, text=stats_text(), parse_mode="HTML")
    if uid == OWNER_ID and text.startswith("/export"):
        return await export(c)
    if text.startswith("/start"):
        src = text.split(" ", 1)[1].strip()[:30] if " " in text else "direct"
        if S.get(uid, {}).get("sent"):
            return await call(c, "sendMessage", chat_id=uid, text="Ваша заявка уже у нас ✅ Пришлю дату, когда наберётся группа.")
        S[uid] = {"src": src, "t0": time.time(), "step": "job", "likes": [], "username": u.get("username"),
                  "name": " ".join(x for x in [u.get("first_name"), u.get("last_name")] if x)}
        save()
        await call(c, "sendMessage", chat_id=uid, text=WELCOME, parse_mode="HTML")
        return await ask(c, uid, S[uid])
    st = S.get(uid)
    if not st:
        return await call(c, "sendMessage", chat_id=uid, text="Нажмите /start, чтобы оставить заявку")
    if st.get("step") == "about" and text:
        st["about"] = text[:500]
        return await finish(c, uid)
    if text:
        st.setdefault("extra", []).append(text[:500])
        save()
        await call(c, "sendMessage", chat_id=OWNER_ID, parse_mode="HTML",
                   text=f"✉️ <b>{esc(NAME)}: сообщение</b> от {tg(st, uid)}\n{esc(text[:1000])}")


async def on_callback(c, q):
    uid = q["from"]["id"]
    data = q.get("data", "")
    msg_id = q["message"]["message_id"]
    await call(c, "answerCallbackQuery", callback_query_id=q["id"])
    if data.startswith("lv:") and uid == OWNER_ID:
        _, who, lv = data.split(":")
        st = S.get(int(who))
        if not st:
            return
        st["level"] = lv
        save()
        await call(c, "editMessageText", chat_id=OWNER_ID, message_id=msg_id, text=card_text(st, int(who)), parse_mode="HTML",
                   disable_web_page_preview="true", reply_markup=card_kb(int(who)))
        return await to_sheet(c, st, int(who))
    st = S.get(uid)
    if not st:
        return
    key, _, val = data.partition(":")
    order = [s[0] for s in STEPS]
    if key in order and st.get("step") == key:
        st[key] = val
        i = order.index(key)
        st["step"] = order[i + 1] if i + 1 < len(order) else "likes"
        save()
        return await ask(c, uid, st, msg_id)
    if key == "like" and st.get("step") == "likes":
        lk = st.setdefault("likes", [])
        lk.remove(val) if val in lk else lk.append(val)
        save()
        return await ask(c, uid, st, msg_id)
    if data == "likes_done" and st.get("step") == "likes":
        st["step"] = "about"
        save()
        return await ask(c, uid, st, msg_id)
    if data == "skip" and st.get("step") == "about":
        await call(c, "editMessageReplyMarkup", chat_id=uid, message_id=msg_id, reply_markup=kb([]))
        return await finish(c, uid)


async def main():
    load()
    off = 0
    async with httpx.AsyncClient(timeout=70) as c:
        await call(c, "setMyCommands", commands=[{"command": "start", "description": "Оставить заявку"}])
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
