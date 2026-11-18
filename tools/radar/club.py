"""Бот закрытого клуба (решение Александра 18.11): деловая мужская аудитория, первый вечер сигарный.
Человек отвечает на 7 вопросов, видит свою карточку-интро -> владельцу приходит карточка с кнопками 1 / 2 / 3 (кого звать первым).
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

JOB = [("dxb", "Бизнес в Дубае"), ("ru", "Бизнес в РФ и СНГ"), ("world", "Бизнес в другой стране"),
       ("inv", "Инвестирую"), ("top", "Топ-менеджмент"), ("emp_dxb", "Найм в Дубае"),
       ("emp", "Найм в другой стране"), ("cons", "Консалтинг, эксперт"), ("oth", "Другое")]
SPHERE = [("re", "Недвижимость"), ("build", "Строительство"), ("crypto", "Крипта и финтех"), ("fin", "Финансы"),
          ("it", "IT"), ("trade", "Торговля и ВЭД"), ("log", "Логистика"), ("prod", "Производство"),
          ("ecom", "E-commerce"), ("mkt", "Маркетинг и медиа"), ("horeca", "Рестораны, HoReCa"), ("med", "Медицина, бьюти"),
          ("auto", "Авто"), ("law", "Право, консалтинг"), ("edu", "Образование"), ("oth", "Другое")]
TEAM = [("solo", "Работаю один"), ("s", "До 10 человек"), ("m", "10–50 человек"), ("l", "Больше 50 человек")]
SEEK = [("partners", "Партнёров для бизнеса"), ("invest", "Инвестиции в свой проект"), ("capital", "Куда вложить капитал"),
        ("clients", "Новых клиентов"), ("markets", "Выход на новые рынки"), ("circle", "Сильное окружение в Дубае"),
        ("exp", "Обмен опытом с предпринимателями"), ("people", "Интересные знакомства")]
LIKES = [("cigar", "Сигары"), ("track", "Автодром"), ("golf", "Гольф"), ("padel", "Падел"), ("yacht", "Яхты"),
         ("tennis", "Теннис"), ("run", "Бег, триатлон"), ("fight", "Единоборства"), ("travel", "Путешествия"),
         ("fish", "Рыбалка"), ("kite", "Кайт, сёрф"), ("chess", "Шахматы")]
L = {}
for _lst in (JOB, SPHERE, TEAM, SEEK, LIKES):
    for _k, _v in _lst:
        L.setdefault(_k, _v)
LBL = {"job": dict(JOB), "sphere": dict(SPHERE), "team": dict(TEAM), "seek": dict(SEEK), "likes": dict(LIKES)}
INTRO_MAX = 300

COVER_URL = "https://res-prod.buzzy.now/file-service/023aab67-60d0-481f-9c82-37d385f6997d.jpg"  # картинка над приветствием (ссылка на jpg), пусто = без картинки
TOTAL = 7


def head(n, emoji, title):
    return f"{emoji} <b>{n}/{TOTAL} · {title}</b>\n" + "▰" * n + "▱" * (TOTAL - n)


WELCOME = (f"🎩 <b>{NAME}</b>\n"
           "<i>Клуб международных предпринимателей и инвесторов в Дубае</i>\n\n"
           "<b>Ближайшая встреча</b>\n"
           "Сигарный вечер в лаунже DIFC · 12–16 человек\n"
           "Каждый платит за себя по меню\n\n"
           "<b>Форматы клуба</b>\n"
           "Сигары · автодром · гольф · падел\n\n"
           "🔐 Вход по заявке · анкета за 2 минуты")
GO_KB = {"inline_keyboard": [[{"text": "Заполнить анкету →", "callback_data": "go"}]]}
MULTI = "\n\n<i>Можно выбрать несколько, потом «Готово»</i>"
# ключ, вопрос, варианты, несколько ответов, кнопок в ряд
STEPS = [("job", head(1, "💼", "Чем занимаетесь?") + MULTI, JOB, True, 2),
         ("sphere", head(2, "🧭", "В каких сферах?") + MULTI, SPHERE, True, 2),
         ("team", head(3, "👥", "Размер команды или компании"), TEAM, False, 2),
         ("seek", head(4, "🤝", "Что сейчас ищете?") + MULTI, SEEK, True, 1),
         ("likes", head(5, "🎯", "Хобби и интересы") + "\n\nПод них подбираем встречи" + MULTI, LIKES, True, 2)]
Q_NAME = "👋 <b>Как к вам обращаться?</b>\n\n<i>Напишите имя и фамилию, например: Иван Петров</i>"
Q_INTRO = (head(6, "✍️", "Ваше интро") + "\n\n"
           "Пара строк о себе:\n"
           "• чем занимаетесь\n"
           "• чем можете быть полезны\n"
           "• чем увлекаетесь\n\n"
           f"<i>До {INTRO_MAX} знаков. Пример:</i>\n"
           "<blockquote>Вожу промышленное оборудование из Китая в Россию и Казахстан. 6 лет в Дубае, "
           "вложился в два офисных проекта. Помогу с логистикой и таможней. Играю в падел, люблю автодром.</blockquote>")
Q_IG = (head(7, "📷", "Ваш Instagram") + "\n\n"
        "Так нам проще понять, кого с кем познакомить и на какую встречу позвать.\n"
        "<i>Видят только организаторы</i>\n\n"
        "Пришлите ник, например <b>@ivan.petrov</b>")
DONE = ("✅ <b>Заявка принята</b>\n\n"
        "Когда соберётся группа, пришлю дату и место.\n"
        "Места получают те, кто подтвердит первым.")


def good_name(n):
    return sum(ch.isalpha() for ch in (n or "")) >= 2


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


def lst(v):
    return v if isinstance(v, list) else ([v] if v else [])


def names(st, key, low=False):
    out = [L.get(x, x) for x in lst(st.get(key))]
    if low:
        out = [x[:1].lower() + x[1:] if not x[:2].isupper() else x for x in out]
    return out


def about_full(st):
    parts = [st.get("intro") or st.get("about") or ""]
    if st.get("ig"):
        parts.append("Instagram: " + st["ig"])
    return "\n".join(p for p in parts if p)


def row(st, uid):
    return [st.get("level") or "", st.get("at", ""), st.get("name") or "", ("@" + st["username"]) if st.get("username") else "",
            ", ".join(names(st, "job")), ", ".join(names(st, "sphere")), ", ".join(names(st, "team")),
            ", ".join(names(st, "seek")), ", ".join(names(st, "likes")), about_full(st), st.get("src", ""), str(uid)]


LINE = "━━━━━━━━━━━━━━"


def member_card(st):
    out = [LINE, f"<b>{esc(NAME)} · Интро</b>", "", f"<b>{esc(st.get('name') or 'Участник')}</b>"]
    if names(st, "job"):
        out.append(esc(" · ".join(names(st, "job"))))
    if names(st, "sphere"):
        out.append(esc(" · ".join(names(st, "sphere"))))
    if st.get("intro"):
        out += ["", f"<blockquote>{esc(st['intro'])}</blockquote>"]
    out.append("")
    if names(st, "seek"):
        out.append("🤝 Ищу: " + esc(", ".join(names(st, "seek", True))))
    if names(st, "likes"):
        out.append("🎯 Интересы: " + esc(", ".join(names(st, "likes", True))))
    if st.get("ig"):
        out.append("📷 Instagram: " + esc(st["ig"]))
    out.append(LINE)
    return "\n".join(out)


def card_text(st, uid):
    lv = {"1": "1️⃣ звать в первую очередь", "2": "2️⃣ во вторую", "3": "3️⃣ в последнюю"}.get(st.get("level"), "не оценён")
    head = "обновил анкету" if st.get("updated") else "новая заявка"
    return (f"🎩 <b>{esc(NAME)}: {head}</b>\n{tg(st, uid)}\n\n{member_card(st)}\n\n"
            f"• Команда: {esc(', '.join(names(st, 'team')) or '—')}\n• Источник: {esc(st.get('src') or '—')}\n\n"
            f"Уровень: <b>{lv}</b>")


def card_kb(uid):
    return kb([[{"text": "1", "callback_data": f"lv:{uid}:1"}, {"text": "2", "callback_data": f"lv:{uid}:2"},
                {"text": "3", "callback_data": f"lv:{uid}:3"}]])


PREVIEW_KB = kb([[{"text": "✅ Всё верно, отправить", "callback_data": "ok"}],
                 [{"text": "✏️ Изменить интро", "callback_data": "edit_intro"}],
                 [{"text": "↩️ Заполнить заново", "callback_data": "restart"}]])


def cut(t, n):
    t = " ".join(t.split()) if "\n" not in t else "\n".join(" ".join(l.split()) for l in t.splitlines() if l.strip())
    if len(t) <= n:
        return t
    t = t[:n]
    sp = max(t.rfind(" "), t.rfind("\n"))
    return (t[:sp] if sp > n * 0.6 else t).rstrip(" ,.;:-") + "…"


def norm_ig(t):
    t = t.strip().split()[0] if t.strip() else ""
    if "instagram.com/" in t:
        t = t.split("instagram.com/", 1)[1].split("?")[0].strip("/").split("/")[0]
    t = t.lstrip("@").strip()
    return ("@" + t)[:40] if t else ""


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


async def show(c, uid, text, markup, msg_id=None):
    markup = markup or kb([])
    if msg_id:
        return await call(c, "editMessageText", chat_id=uid, message_id=msg_id, text=text, parse_mode="HTML",
                          disable_web_page_preview="true", reply_markup=markup)
    return await call(c, "sendMessage", chat_id=uid, text=text, parse_mode="HTML",
                      disable_web_page_preview="true", reply_markup=markup)


async def ask(c, uid, st, msg_id=None):
    step = st.get("step")
    for key, q, opts, multi, cols in STEPS:
        if step == key:
            chosen = lst(st.get(key))
            btns = [{"text": ("✅ " if k in chosen else "") + l, "callback_data": f"{'t' if multi else 'o'}:{key}:{k}"}
                    for k, l in opts]
            rows = [btns[i:i + cols] for i in range(0, len(btns), cols)]
            if multi:
                rows.append([{"text": "Готово →", "callback_data": f"d:{key}"}])
            return await show(c, uid, q, kb(rows), msg_id)
    if step == "name":
        return await show(c, uid, Q_NAME, None, msg_id)
    if step == "intro":
        return await show(c, uid, Q_INTRO, None, msg_id)
    if step == "ig":
        return await show(c, uid, Q_IG, kb([[{"text": "Пропустить", "callback_data": "skip"}]]), msg_id)
    if step == "preview":
        return await show(c, uid, "👇 <b>Ваша карточка участника</b>\n<i>Проверьте, всё ли верно</i>\n\n" + member_card(st), PREVIEW_KB, msg_id)


async def finish(c, uid):
    st = S[uid]
    st["step"] = "done"
    st["at"] = time.strftime("%Y-%m-%d %H:%M", time.gmtime(time.time() + 4 * 3600))
    save()
    await call(c, "sendMessage", chat_id=uid, text=DONE, parse_mode="HTML")
    if not st.get("sent") or st.get("updated"):
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
        n = sum(1 for s in done if k in lst(s.get('likes')))
        if n:
            out.append(f"• {l}: {n}")
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
        src_tag = text.split(" ", 1)[1].strip()[:30] if " " in text else "direct"
        old = S.get(uid, {})
        if old.get("sent"):
            return await call(c, "sendMessage", chat_id=uid, parse_mode="HTML", disable_web_page_preview="true",
                              text="Ваша заявка уже у нас ✅ Пришлю дату, когда наберётся группа.\n\n" + member_card(old),
                              reply_markup=kb([[{"text": "↩️ Обновить анкету", "callback_data": "restart"}]]))
        nm = " ".join(x for x in [u.get("first_name"), u.get("last_name")] if x)
        S[uid] = {"src": src_tag, "t0": time.time(), "step": "welcome", "username": u.get("username"), "name": nm}
        save()
        if COVER_URL:
            fid_p = os.path.join(BASE, "club_cover_id.json")
            try:
                fid = json.load(open(fid_p)).get(COVER_URL)
            except Exception:
                fid = None
            j = await call(c, "sendPhoto", chat_id=uid, photo=fid or COVER_URL, caption=WELCOME, parse_mode="HTML", reply_markup=GO_KB)
            if j.get("ok"):
                if not fid:
                    try:
                        json.dump({COVER_URL: j["result"]["photo"][-1]["file_id"]}, open(fid_p, "w"))
                    except Exception:
                        pass
                return j
        return await call(c, "sendMessage", chat_id=uid, text=WELCOME, parse_mode="HTML", reply_markup=GO_KB)
    st = S.get(uid)
    if not st:
        return await call(c, "sendMessage", chat_id=uid, text="Нажмите /start, чтобы оставить заявку")
    if st.get("step") == "name" and text:
        st["name"] = cut(text, 40)
        st["step"] = "job"
        save()
        return await ask(c, uid, st)
    if st.get("step") == "intro" and text:
        st["intro"] = cut(text, INTRO_MAX)
        st["step"] = "preview" if st.pop("back", None) else "ig"
        save()
        return await ask(c, uid, st)
    if st.get("step") == "ig" and text:
        st["ig"] = norm_ig(text)
        st["step"] = "preview"
        save()
        return await ask(c, uid, st)
    if text:
        st.setdefault("extra", []).append(text[:500])
        save()
        await call(c, "sendMessage", chat_id=OWNER_ID, parse_mode="HTML",
                   text=f"✉️ <b>{esc(NAME)}: сообщение</b> от {tg(st, uid)}\n{esc(text[:1000])}")


async def on_callback(c, q):
    uid = q["from"]["id"]
    data = q.get("data", "")
    msg_id = q["message"]["message_id"]
    if not data.startswith("d:") or S.get(uid, {}).get("step") != data[2:]:
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
    kind, _, rest = data.partition(":")
    key, _, val = rest.partition(":")
    order = [s[0] for s in STEPS]
    nxt = lambda k: order[order.index(k) + 1] if order.index(k) + 1 < len(order) else "intro"
    if kind == "o" and st.get("step") == key:
        st[key] = val
        st["step"] = nxt(key)
        save()
        return await ask(c, uid, st, msg_id)
    if kind == "t" and st.get("step") == key:
        ch = lst(st.get(key))
        ch.remove(val) if val in ch else ch.append(val)
        st[key] = ch
        save()
        return await ask(c, uid, st, msg_id)
    if kind == "d" and st.get("step") == key:
        if not lst(st.get(key)):
            return await call(c, "answerCallbackQuery", callback_query_id=q["id"], text="Выберите хотя бы один вариант")
        await call(c, "answerCallbackQuery", callback_query_id=q["id"])
        st["step"] = nxt(key)
        save()
        return await ask(c, uid, st, msg_id)
    if data == "go" and st.get("step") == "welcome":
        st["step"] = "job" if good_name(st.get("name")) else "name"
        save()
        await call(c, "editMessageReplyMarkup", chat_id=uid, message_id=msg_id, reply_markup=kb([]))
        return await ask(c, uid, st)
    if data == "skip" and st.get("step") == "ig":
        st["ig"] = ""
        st["step"] = "preview"
        save()
        return await ask(c, uid, st, msg_id)
    if data == "edit_intro" and st.get("step") == "preview":
        st["step"], st["back"] = "intro", True
        save()
        await call(c, "editMessageReplyMarkup", chat_id=uid, message_id=msg_id, reply_markup=kb([]))
        return await ask(c, uid, st)
    if data == "restart":
        keep = {k: st[k] for k in ("src", "t0", "username", "name", "level", "sent", "card") if k in st}
        if st.get("sent"):
            keep["updated"] = True
        S[uid] = st = dict(keep, step="job" if good_name(keep.get("name")) else "name")
        save()
        await call(c, "editMessageReplyMarkup", chat_id=uid, message_id=msg_id, reply_markup=kb([]))
        return await ask(c, uid, st)
    if data == "ok" and st.get("step") == "preview":
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
