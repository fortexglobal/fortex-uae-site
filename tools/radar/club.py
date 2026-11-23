"""Бот закрытого клуба (решение Александра 18.11): деловая мужская аудитория, первый вечер сигарный.
Человек отвечает на 7 вопросов, видит свою карточку-интро -> владельцу приходит карточка с кнопками 1 / 2 / 3 (кого звать первым).
Каждая заявка и уровень пишутся в Google Таблицу (CRM, лист «Клуб: заявки») через веб-хук Apps Script (файл gcal_hook).
Метка рекламы: https://t.me/<бот>?start=<метка>.  Команды владельца: /club (сводка), /export (файл).
Конфиг: /opt/radar/club.env (CLUB_TOKEN=..., CLUB_NAME=...)   Запуск: systemd club.service
"""
import asyncio, csv, html, io, json, logging, os, re, time
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
           "Закрытые встречи в небольшом кругу: сигарные вечера в DIFC, автодром, гольф, падел.\n\n"
           "🔐 Вход по заявке. Анкета займёт 2 минуты 👇")
COVER_GOLF_URL = "https://images.unsplash.com/photo-1629673120178-53a664eec9e8?fm=jpg&q=85&w=1600"
WELCOME_GOLF = (f"⛳️ <b>{NAME} · Гольф</b>\n"
                "<i>Клуб международных предпринимателей и инвесторов в Дубае</i>\n\n"
                "Собираем небольшую группу на гольф с тренером. Подойдёт и новичкам, и тем, кто уже играет. "
                "После игры общение в лаунже клуба.\n\n"
                "🔐 Вход по заявке. Анкета займёт 2 минуты 👇")
GO_KB = {"inline_keyboard": [[{"text": "Заполнить анкету →", "callback_data": "go", "style": "primary"}]]}
MULTI = "\n\n<i>Можно выбрать несколько, потом «Готово»</i>"
# ключ, вопрос, варианты, несколько ответов, кнопок в ряд
STEPS = [("job", head(1, "💼", "Чем занимаетесь?") + MULTI, JOB, True, 2),
         ("sphere", head(2, "🧭", "В каких сферах?") + MULTI, SPHERE, True, 2),
         ("team", head(3, "👥", "Размер команды или компании"), TEAM, False, 2),
         ("seek", head(4, "🤝", "Что сейчас ищете?") + MULTI, SEEK, True, 1),
         ("likes", head(5, "🎯", "Хобби и интересы") + "\n\nПод них подбираем встречи" + MULTI, LIKES, True, 2)]
Q_OTHER = {"job": "💼 <b>Чем именно занимаетесь?</b>\n\n<i>Коротко, в паре слов. Например: управляю семейным офисом</i>",
           "sphere": "🧭 <b>Какая именно сфера?</b>\n\n<i>Коротко, в паре слов. Например: судоходство</i>"}
Q_NAME = "👋 <b>Как к вам обращаться?</b>\n\nТак вас увидят другие участники клуба.\n<i>Напишите имя и фамилию, например: Иван Петров</i>"
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
DONE_CARD = ("✅ <b>Заявка принята</b>\n\n"
             "Это ваша карта участника <b>DXB Club</b>\n"
             "Личный код: <b>DXB · {code}</b>\n\n"
             "<b>Что дальше</b>\n"
             "<blockquote>📩 Пришлём приглашение на следующую встречу клуба\n"
             "📍 В нём будут дата, место и формат\n"
             "⏳ Места ограничены, их получают те, кто подтвердит первым</blockquote>\n\n"
             "<i>Приглашение придёт в этот чат</i>")
DONE = ("✅ <b>Заявка принята</b>\n\n"
        "<b>Что дальше</b>\n"
        "<blockquote>📩 Пришлём приглашение на следующую встречу клуба\n"
        "📍 В нём будут дата, место и формат\n"
        "⏳ Места ограничены, их получают те, кто подтвердит первым</blockquote>\n\n"
        "<i>Приглашение придёт в этот чат</i>")


def good_name(n):
    return sum(ch.isalpha() for ch in (n or "")) >= 2


S = {}
EMO_P = os.path.join(BASE, "club_emoji.json")
try:
    EMO = json.load(open(EMO_P))  # обычный эмодзи -> id премиум-эмодзи из пака владельца
except Exception:
    EMO = {}


EMO_LIST = [("🎩", "название клуба"), ("🔐", "вход по заявке"), ("👋", "вопрос про имя"), ("💼", "чем занимаетесь"),
            ("🧭", "сферы"), ("👥", "команда"), ("🤝", "что ищете"), ("🎯", "хобби и интересы"), ("✍️", "интро"),
            ("📷", "Instagram"), ("👇", "карточка участника"), ("✅", "заявка принята")]
EMO_Q = []


def premium(t):
    for e, cid in EMO.items():
        if e in t:
            t = t.replace(e, f'<tg-emoji emoji-id="{cid}">{e}</tg-emoji>')
    return t


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
    if EMO and data.get("parse_mode") == "HTML":
        for f in ("text", "caption"):
            if f in data:
                data[f] = premium(data[f])
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
    out = [(st.get(key + "_other") if x == "oth" and st.get(key + "_other") else L.get(x, x)) for x in lst(st.get(key))]
    if low:
        out = [x[:1].lower() + x[1:] if not x[:2].isupper() else x for x in out]
    return out


def about_full(st):
    parts = [st.get("intro") or st.get("about") or ""]
    if st.get("ig"):
        parts.append("Instagram: https://instagram.com/" + st["ig"].lstrip("@"))
    return "\n".join(p for p in parts if p)


def row(st, uid):
    return [st.get("level") or "", st.get("at", ""), st.get("name") or "", ("@" + st["username"]) if st.get("username") else "",
            ", ".join(names(st, "job")), ", ".join(names(st, "sphere")), ", ".join(names(st, "team")),
            ", ".join(names(st, "seek")), ", ".join(names(st, "likes")), about_full(st), st.get("src", ""), str(uid)]


LINE = "━━━━━━━━━━━━━━"


def member_card(st, owner=False):
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
        ig = esc(st["ig"])
        out.append("📷 Instagram: " + (f'<a href="https://instagram.com/{ig[1:]}">instagram.com/{ig[1:]}</a>' if owner else ig))
    out.append(LINE)
    return "\n".join(out)


def card_text(st, uid):
    lv = {"1": "1️⃣ звать в первую очередь", "2": "2️⃣ во вторую", "3": "3️⃣ в последнюю"}.get(st.get("level"), "не оценён")
    head = "обновил анкету" if st.get("updated") else "новая заявка"
    return (f"🎩 <b>{esc(NAME)}: {head}</b>\n{tg(st, uid)}\n\n{member_card(st, owner=True)}\n\n"
            f"• Команда: {esc(', '.join(names(st, 'team')) or '—')}\n• Источник: {esc(st.get('src') or '—')}\n\n"
            f"Уровень: <b>{lv}</b>")


def card_kb(uid):
    return kb([[{"text": "1", "callback_data": f"lv:{uid}:1", "style": "success"},
                {"text": "2", "callback_data": f"lv:{uid}:2", "style": "primary"},
                {"text": "3", "callback_data": f"lv:{uid}:3", "style": "danger"}]])


PREVIEW_KB = kb([[{"text": "Всё верно, отправить", "callback_data": "ok", "style": "success"}],
                 [{"text": "✏️ Изменить интро", "callback_data": "edit_intro"}],
                 [{"text": "↩️ Заполнить заново", "callback_data": "restart"}]])


def cut(t, n):
    t = " ".join(t.split()) if "\n" not in t else "\n".join(" ".join(l.split()) for l in t.splitlines() if l.strip())
    if len(t) <= n:
        return t
    t = t[:n]
    sp = max(t.rfind(" "), t.rfind("\n"))
    return (t[:sp] if sp > n * 0.6 else t).rstrip(" ,.;:-") + "…"


IG_SKIP = {"нет", "не веду", "нету", "no", "none", "-", "—", "пропустить", "не", "нет инстаграма", "нет инсты", "skip"}


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
    if not msg_id:
        await call(c, "sendChatAction", chat_id=uid, action="typing")
        await asyncio.sleep(0.7)
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
            btns = [dict({"text": ("✓ " if k in chosen else "") + l, "callback_data": f"{'t' if multi else 'o'}:{key}:{k}"},
                         **({"style": "success"} if k in chosen else {})) for k, l in opts]
            rows = [btns[i:i + cols] for i in range(0, len(btns), cols)]
            if multi:
                rows.append([{"text": "Готово →", "callback_data": f"d:{key}", "style": "primary"}])
            return await show(c, uid, q, kb(rows), msg_id)
    if step and step.endswith("_other"):
        return await show(c, uid, Q_OTHER[step[:-6]], None, msg_id)
    if step == "name":
        nm = st.get("tg_name") or ""
        m = kb([[{"text": f"Оставить: {nm[:30]}", "callback_data": "keep_name"}]]) if good_name(nm) else None
        return await show(c, uid, Q_NAME, m, msg_id)
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
    await call(c, "sendChatAction", chat_id=uid, action="upload_photo")
    if not await send_card(c, uid, st, uid, DONE_CARD.format(code=member_code(uid))):
        await call(c, "sendMessage", chat_id=uid, text=DONE, parse_mode="HTML")
    if not st.get("sent") or st.get("updated"):
        st["sent"] = True
        j = await call(c, "sendMessage", chat_id=OWNER_ID, text=card_text(st, uid), parse_mode="HTML",
                       disable_web_page_preview="true", reply_markup=card_kb(uid))
        st["card"] = (j.get("result") or {}).get("message_id")
        save()
    await to_sheet(c, st, uid)


# ---------- Карта участника (картинка) ----------
FONT_URL = "https://raw.githubusercontent.com/google/fonts/main/ofl/"
FONTS = {"cin": "cinzel/Cinzel%5Bwght%5D.ttf", "cor": "cormorantgaramond/CormorantGaramond%5Bwght%5D.ttf",
         "mon": "montserrat/Montserrat%5Bwght%5D.ttf"}
FONT_DIR = os.path.join(BASE, "club_fonts")


def ensure_card_deps():
    import subprocess, sys, urllib.request
    try:
        import PIL  # noqa
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "pillow"], timeout=300)
    os.makedirs(FONT_DIR, exist_ok=True)
    for k, p in FONTS.items():
        fp = os.path.join(FONT_DIR, k + ".ttf")
        if not os.path.exists(fp) or os.path.getsize(fp) < 10000:
            urllib.request.urlretrieve(FONT_URL + p, fp)


def member_code(uid):
    import hashlib
    h = hashlib.sha1(f"dxb{uid}".encode()).hexdigest().upper()
    alpha = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
    return "".join(alpha[int(h[i:i + 2], 16) % len(alpha)] for i in range(0, 8, 2))


def render_card(st, uid):
    ensure_card_deps()
    from PIL import Image, ImageDraw, ImageFont, ImageOps

    def F(k, size, w):
        f = ImageFont.truetype(os.path.join(FONT_DIR, k + ".ttf"), size)
        try:
            f.set_variation_by_axes([w])
        except Exception:
            pass
        return f

    W, H = 1600, 1000
    g = ImageOps.invert(Image.radial_gradient("L")).resize((W * 2, W * 2))
    g = g.crop((int(W * 0.2), int(W * 0.85), int(W * 0.2) + W, int(W * 0.85) + H))
    img = ImageOps.colorize(g, black=(10, 8, 6), white=(52, 44, 30)).convert("RGBA")
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(ov)
    for i in range(-H, W, 14):
        od.line([(i, 0), (i + H, H)], fill=(212, 175, 105, 9), width=1)
    for k in range(9):
        r = 260 + k * 55
        od.ellipse([W * 0.8 - r, H * 0.12 - r, W * 0.8 + r, H * 0.12 + r], outline=(212, 175, 105, 14), width=2)
    img = Image.alpha_composite(img, ov)
    d = ImageDraw.Draw(img)
    gold, soft, white = (232, 196, 122), (214, 190, 146), (248, 242, 230)
    d.rounded_rectangle([28, 28, W - 28, H - 28], radius=46, outline=(176, 144, 86), width=4)
    d.rounded_rectangle([46, 46, W - 46, H - 46], radius=36, outline=(100, 82, 50), width=2)
    d.text((100, 84), "DXB", font=F("cin", 150, 800), fill=gold)
    lw = d.textlength("DXB", font=F("cin", 150, 800))
    d.text((100 + lw + 26, 146), "CLUB", font=F("cin", 66, 700), fill=gold)
    d.text((W - 100, 104), "MEMBER", font=F("mon", 40, 700), fill=gold, anchor="ra")
    d.text((W - 100, 156), "Участник клуба", font=F("cor", 48, 700), fill=soft, anchor="ra")
    cx, cy = 104, 300
    d.rounded_rectangle([cx, cy, cx + 120, cy + 92], radius=16, fill=(196, 160, 96))
    for yy in (cy + 30, cy + 61):
        d.line([(cx, yy), (cx + 120, yy)], fill=(140, 110, 62), width=3)
    d.line([(cx + 60, cy), (cx + 60, cy + 92)], fill=(140, 110, 62), width=3)

    def fit(text, k, size, w, maxw):
        while size > 24 and d.textlength(text, font=F(k, size, w)) > maxw:
            size -= 2
        return F(k, size, w)

    name = st.get("name") or "Участник"
    maxw = W - 200
    one = 168
    while one > 140 and d.textlength(name, font=F("cor", one, 700)) > maxw:
        one -= 4
    nf = F("cor", one, 700)
    if d.textlength(name, font=nf) <= maxw:
        d.text((100, 612), name, font=nf, fill=white, anchor="ls")
    else:
        parts = name.split()
        if len(parts) > 1:
            best = min(range(1, len(parts)), key=lambda i: abs(len(" ".join(parts[:i])) - len(" ".join(parts[i:]))))
            a, b = " ".join(parts[:best]), " ".join(parts[best:])
            sz = 120
            while sz > 60 and max(d.textlength(a, font=F("cor", sz, 700)), d.textlength(b, font=F("cor", sz, 700))) > maxw:
                sz -= 4
            nf = F("cor", sz, 700)
            d.text((100, 612 - int(sz * 0.95)), a, font=nf, fill=white, anchor="ls")
            d.text((100, 612), b, font=nf, fill=white, anchor="ls")
        else:
            d.text((100, 612), name, font=fit(name, "cor", 168, 700, maxw), fill=white, anchor="ls")
    sph = names(st, "sphere") or names(st, "job")
    l1 = ""
    for n in range(min(3, len(sph)), 0, -1):
        l1 = " · ".join(sph[:n])
        if d.textlength(l1, font=F("mon", 52, 600)) <= maxw:
            break
    seek = ["Ищу " + x for x in names(st, "seek", True)[:1]]
    likes = names(st, "likes", True)
    l2 = ""
    for n in range(min(3, len(likes)), -1, -1):
        cand = " · ".join(x for x in [seek[0] if seek else "", ", ".join(likes[:n]).capitalize() if n else ""] if x)
        l2 = cand
        if d.textlength(cand, font=F("mon", 42, 500)) <= maxw:
            break
    if l1:
        d.text((104, 650), l1, font=fit(l1, "mon", 52, 600, maxw), fill=gold)
    if l2:
        d.text((104, 728), l2, font=fit(l2, "mon", 42, 500, maxw), fill=soft)
    d.line([(100, 820), (W - 100, 820)], fill=(120, 98, 60), width=2)
    d.text((100, 848), "DXB · " + member_code(uid), font=F("mon", 50, 700), fill=gold)
    d.text((W - 100, 848), "DUBAI · " + time.strftime("%Y"), font=F("mon", 50, 700), fill=gold, anchor="ra")
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=92)
    return buf.getvalue()


async def send_card(c, chat_id, st, uid, caption):
    try:
        jpg = await asyncio.to_thread(render_card, st, uid)
    except Exception as e:
        log.warning("card: %s", e)
        return False
    cap = premium(caption) if EMO else caption
    r = await c.post(API + "sendPhoto", data={"chat_id": chat_id, "caption": cap, "parse_mode": "HTML"},
                     files={"photo": ("card.jpg", jpg, "image/jpeg")})
    return r.json().get("ok", False)


def stats_text():
    done = [s for s in S.values() if s.get("sent")]
    out = [f"<b>{esc(NAME)}: заявки</b>", "", f"• Начали: {len(S)}, заполнили: {len(done)}"]
    for lv in ("1", "2", "3"):
        out.append(f"• Уровень {lv}: {sum(1 for s in done if s.get('level') == lv)}")
    out.append(f"• Не оценены: {sum(1 for s in done if not s.get('level'))}")
    STEP_RU = {"welcome": "приветствие", "name": "имя", "job": "чем занимается", "job_other": "чем занимается (другое)",
               "sphere": "сфера", "sphere_other": "сфера (другое)", "team": "команда", "seek": "что ищет",
               "likes": "хобби", "intro": "интро", "ig": "Instagram", "preview": "карточка, не нажал отправить"}
    stuck = {}
    for s_ in S.values():
        if not s_.get("sent") and s_.get("step") in STEP_RU:
            stuck[s_["step"]] = stuck.get(s_["step"], 0) + 1
    if stuck:
        out += ["", "<b>Где бросили анкету</b>"]
        for k in STEP_RU:
            if stuck.get(k):
                out.append(f"• {STEP_RU[k]}: {stuck[k]}")
        out.append(f"• напоминание получили: {sum(1 for s_ in S.values() if s_.get('reminded') and not s_.get('sent'))}, "
                   f"вернулись и дошли до конца: {sum(1 for s_ in S.values() if s_.get('reminded') and s_.get('sent'))}")
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


async def ask_emoji(c, uid):
    if not EMO_Q:
        return await call(c, "sendMessage", chat_id=uid, parse_mode="HTML",
                          text="✅ <b>Эмодзи настроены</b>\n\nНажми /start, чтобы посмотреть анкету. Заново: /emoji")
    e = EMO_Q[0]
    n = len(EMO_LIST) - len(EMO_Q) + 1
    what = dict(EMO_LIST)[e]
    now = e
    return await call(c, "sendMessage", chat_id=uid, parse_mode="HTML",
                      text=f"<b>{n}/{len(EMO_LIST)} · {what}</b>\nСейчас: {now}\n\nОтправь одно эмодзи из своего пака на замену",
                      reply_markup=kb([[{"text": "Пропустить", "callback_data": "emo_skip"}]]))


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
    if uid == OWNER_ID and text.startswith("/preview"):
        golf = "golf" in text.lower()
        cover_url, welcome = (COVER_GOLF_URL, WELCOME_GOLF) if golf else (COVER_URL, WELCOME)
        await call(c, "sendMessage", chat_id=uid, text="👀 Так видит бота новый человек" + (" с гольф-рекламы" if golf else "") + ":")
        j = await call(c, "sendPhoto", chat_id=uid, photo=cover_url, caption=welcome, parse_mode="HTML") if cover_url else {}
        if not j.get("ok"):
            await call(c, "sendMessage", chat_id=uid, text=welcome, parse_mode="HTML")
        return await call(c, "sendMessage", chat_id=uid, text=Q_NAME, parse_mode="HTML",
                          reply_markup=kb([[{"text": "Оставить: Иван Петров", "callback_data": "noop"}]]))
    if uid == OWNER_ID and text.startswith("/resync"):
        done = [(k, v) for k, v in S.items() if v.get("sent")]
        for k, v in done:
            await to_sheet(c, v, k)
        return await call(c, "sendMessage", chat_id=uid, text=f"Отправил в таблицу анкет: {len(done)}")
    rep = m.get("reply_to_message") or {}
    mt = re.search(r"#u(\d+)", rep.get("text") or "")
    if uid == OWNER_ID and mt and text:
        to = int(mt.group(1))
        j = await call(c, "sendMessage", chat_id=to, parse_mode="HTML",
                       text=f"💬 <b>{esc(NAME)}</b>\n\n{esc(text)}")
        return await call(c, "sendMessage", chat_id=uid, text="Отправил ✅" if j.get("ok") else "Не дошло: человек заблокировал бота")
    if uid == OWNER_ID and text.startswith("/card"):
        mine = S.get(uid) or {"name": " ".join(x for x in [u.get("first_name"), u.get("last_name")] if x)}
        await call(c, "sendChatAction", chat_id=uid, action="upload_photo")
        if not await send_card(c, uid, mine, uid, DONE_CARD.format(code=member_code(uid))):
            await call(c, "sendMessage", chat_id=uid, text="Не получилось нарисовать карту, проверяю")
        return
    if uid == OWNER_ID and text.startswith("/emoji") and not text.startswith("/emoji_reset"):
        EMO_Q[:] = [e for e, _ in EMO_LIST]
        return await ask_emoji(c, uid)
    if uid == OWNER_ID and EMO_Q:
        ids = [e["custom_emoji_id"] for e in m.get("entities", []) if e.get("type") == "custom_emoji"]
        if ids:
            EMO[EMO_Q[0]] = ids[0]
            json.dump(EMO, open(EMO_P, "w"), ensure_ascii=False)
            EMO_Q.pop(0)
            return await ask_emoji(c, uid)
        if text in ("-", "пропустить", "Пропустить"):
            EMO_Q.pop(0)
            return await ask_emoji(c, uid)
    if uid == OWNER_ID and ("addemoji/" in text or "addstickers/" in text):
        name = text.split("/add", 1)[1].split("/", 1)[1].split()[0].split("?")[0].strip()
        j = await call(c, "getStickerSet", name=name)
        if not j.get("ok"):
            return await call(c, "sendMessage", chat_id=uid, text=f"Не нашёл пак {name}. Проверь ссылку")
        used = WELCOME + Q_NAME + Q_INTRO + Q_IG + DONE + "".join(q for _, q, *_ in STEPS) + "🤝🎯📷👇🎩✅"
        got = []
        for st_ in j["result"].get("stickers", []):
            base, cid = st_.get("emoji"), st_.get("custom_emoji_id")
            if base and cid and base not in EMO and (base in used or base.rstrip("\ufe0f") in used):
                EMO[base] = cid
                got.append(base)
        json.dump(EMO, open(EMO_P, "w"), ensure_ascii=False)
        allb = " ".join(sorted({s_.get("emoji", "") for s_ in j["result"].get("stickers", [])}))
        return await call(c, "sendMessage", chat_id=uid, parse_mode="HTML",
                          text=f"Пак <b>{esc(j['result'].get('title') or name)}</b>\n\n"
                               f"Подставил в тексты бота: {' '.join(got) or 'ничего не совпало'}\n\n"
                               f"Всего в паке: {esc(allb)}\n\n"
                               "Можно добавить вручную: просто отправь мне нужные эмодзи из пака. Сброс: /emoji_reset")
    ids = [e["custom_emoji_id"] for e in m.get("entities", []) if e.get("type") == "custom_emoji"]
    if uid == OWNER_ID and ids and (S.get(uid, {}).get("step") or "done") in ("done", "welcome"):
        j = await call(c, "getCustomEmojiStickers", custom_emoji_ids=ids)
        got = []
        for st_ in j.get("result", []):
            base = st_.get("emoji")
            if base:
                EMO[base] = st_["custom_emoji_id"]
                got.append(base)
        json.dump(EMO, open(EMO_P, "w"), ensure_ascii=False)
        return await call(c, "sendMessage", chat_id=uid, parse_mode="HTML",
                          text=f"Сохранил эмодзи: {' '.join(got) or 'ничего'}\nТеперь они заменяют обычные в текстах бота.\n"
                               "Чтобы сбросить: /emoji_reset")
    if uid == OWNER_ID and text.startswith("/emoji_reset"):
        EMO.clear()
        json.dump(EMO, open(EMO_P, "w"))
        return await call(c, "sendMessage", chat_id=uid, text="Премиум-эмодзи сброшены")
    if text.startswith("/start"):
        src_tag = text.split(" ", 1)[1].strip()[:30] if " " in text else "direct"
        old = S.get(uid, {})
        if old.get("sent"):
            return await call(c, "sendMessage", chat_id=uid, parse_mode="HTML", disable_web_page_preview="true",
                              text="Ваша заявка уже у нас ✅ Пришлю приглашение на следующую встречу клуба.\n\n" + member_card(old),
                              reply_markup=kb([[{"text": "↩️ Обновить анкету", "callback_data": "restart"}]]))
        nm = " ".join(x for x in [u.get("first_name"), u.get("last_name")] if x)
        S[uid] = {"src": src_tag, "t0": time.time(), "ts": time.time(), "step": "name", "username": u.get("username"),
                  "name": nm, "tg_name": nm}
        save()
        sent_cover = False
        golf = src_tag.lower().startswith("golf")
        cover_url, welcome = (COVER_GOLF_URL, WELCOME_GOLF) if golf else (COVER_URL, WELCOME)
        if cover_url:
            fid_p = os.path.join(BASE, "club_cover_id.json")
            try:
                fids = json.load(open(fid_p))
            except Exception:
                fids = {}
            fid = fids.get(cover_url)
            j = await call(c, "sendPhoto", chat_id=uid, photo=fid or cover_url, caption=welcome, parse_mode="HTML")
            if j.get("ok"):
                sent_cover = True
                if not fid:
                    try:
                        fids[cover_url] = j["result"]["photo"][-1]["file_id"]
                        json.dump(fids, open(fid_p, "w"))
                    except Exception:
                        pass
        if not sent_cover:
            await call(c, "sendMessage", chat_id=uid, text=welcome, parse_mode="HTML")
        return await ask(c, uid, S[uid])
    st = S.get(uid)
    if not st:
        return await call(c, "sendMessage", chat_id=uid, text="Нажмите /start, чтобы оставить заявку")
    st["ts"] = time.time()
    if (st.get("step") or "").endswith("_other") and text:
        key = st["step"][:-6]
        st[key + "_other"] = cut(text, 40)
        order = [x[0] for x in STEPS]
        st["step"] = order[order.index(key) + 1]
        save()
        return await ask(c, uid, st)
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
        if text.strip().lower().strip(".!") in IG_SKIP:
            st["ig"] = ""
        else:
            ig = norm_ig(text)
            if not re.fullmatch(r"@[A-Za-z0-9._]{1,30}", ig or ""):
                return await call(c, "sendMessage", chat_id=uid, parse_mode="HTML",
                                  text="Не похоже на ник Instagram 🤔\n\nПришлите ник латиницей, например <b>@ivan.petrov</b>, или нажмите «Пропустить»",
                                  reply_markup=kb([[{"text": "Пропустить", "callback_data": "skip"}]]))
            st["ig"] = ig
        st["step"] = "preview"
        save()
        return await ask(c, uid, st)
    step = st.get("step") or ""
    if step in ("name", "intro", "ig") or step.endswith("_other"):
        return await call(c, "sendMessage", chat_id=uid, text="Пришлите, пожалуйста, ответ текстом 🙏")
    if step in [x[0] for x in STEPS] + ["welcome", "preview"]:
        return await call(c, "sendMessage", chat_id=uid, text="Выберите вариант кнопками в сообщении выше 👆")
    body = text or m.get("caption") or "[вложение]"
    st.setdefault("extra", []).append(body[:500])
    save()
    await call(c, "sendMessage", chat_id=OWNER_ID, parse_mode="HTML",
               text=f"✉️ <b>{esc(NAME)}: сообщение</b> от {tg(st, uid)} #u{uid}\n{esc(body[:1000])}\n\n<i>Ответь реплаем на это сообщение, и ответ уйдёт человеку</i>")
    await call(c, "sendMessage", chat_id=uid, text="Передал организатору, ответим здесь 🤝")


async def on_callback(c, q):
    uid = q["from"]["id"]
    data = q.get("data", "")
    msg_id = q["message"]["message_id"]
    if not data.startswith("d:") or S.get(uid, {}).get("step") != data[2:]:
        await call(c, "answerCallbackQuery", callback_query_id=q["id"])
    if data == "emo_skip" and uid == OWNER_ID and EMO_Q:
        EMO_Q.pop(0)
        await call(c, "editMessageReplyMarkup", chat_id=uid, message_id=msg_id, reply_markup=kb([]))
        return await ask_emoji(c, uid)
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
    st["ts"] = time.time()
    if data == "resume" and st.get("step") not in ("done", None):
        await call(c, "editMessageReplyMarkup", chat_id=uid, message_id=msg_id, reply_markup=kb([]))
        if st["step"] == "welcome":
            st["tg_name"] = st.get("tg_name") or st.get("name")
            st["step"] = "name"
        save()
        return await ask(c, uid, st)
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
        st["step"] = f"{key}_other" if key in ("job", "sphere") and "oth" in lst(st.get(key)) else nxt(key)
        save()
        return await ask(c, uid, st, msg_id)
    if data == "go" and st.get("step") == "welcome":
        st["tg_name"] = st.get("tg_name") or st.get("name")
        st["step"] = "name"
        save()
        await call(c, "editMessageReplyMarkup", chat_id=uid, message_id=msg_id, reply_markup=kb([]))
        return await ask(c, uid, st)
    if data == "keep_name" and st.get("step") == "name":
        st["name"] = st.get("tg_name") or st.get("name")
        st["step"] = "job"
        save()
        return await ask(c, uid, st, msg_id)
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
        S[uid] = st = dict(keep, step="name", tg_name=keep.get("name"))
        save()
        await call(c, "editMessageReplyMarkup", chat_id=uid, message_id=msg_id, reply_markup=kb([]))
        return await ask(c, uid, st)
    if data == "ok" and st.get("step") == "preview":
        await call(c, "editMessageReplyMarkup", chat_id=uid, message_id=msg_id, reply_markup=kb([]))
        return await finish(c, uid)


REMIND = ("👋 <b>Вы не закончили анкету в {name}</b>\n\n"
          "Осталась пара вопросов. После неё пришлём приглашение на следующую встречу клуба.\n"
          "Места ограничены.")


async def reminders(c):
    while True:
        await asyncio.sleep(300)
        try:
            hour = time.gmtime(time.time() + 4 * 3600).tm_hour
            if not 10 <= hour < 22:
                continue
            for uid, st in list(S.items()):
                if st.get("sent") or st.get("reminded") or st.get("step") in ("done", None):
                    continue
                last = st.get("ts") or st.get("t0") or 0
                if time.time() - last < 2 * 3600 or time.time() - last > 3 * 86400:
                    continue
                st["reminded"] = time.time()
                save()
                await call(c, "sendMessage", chat_id=uid, parse_mode="HTML", text=REMIND.format(name=esc(NAME)),
                           reply_markup=kb([[{"text": "Продолжить анкету →", "callback_data": "resume", "style": "primary"}]]))
        except Exception:
            log.exception("reminders")


async def main():
    load()
    off = 0
    async with httpx.AsyncClient(timeout=70) as c:
        await call(c, "setMyCommands", commands=[{"command": "start", "description": "Оставить заявку"}])
        asyncio.create_task(reminders(c))
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
