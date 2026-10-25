"""Лид-магнит: бот «Проверка шансов на счёт в банке ОАЭ».
5–6 вопросов кнопками -> результат только подписчикам канала @fortex_uae -> кнопка «Написать @Fortex_Dubai» с готовым текстом.
Карточка лида приходит владельцу (он должен один раз нажать /start в этом боте).
Ссылки с источником: https://t.me/<бот>?start=ig | threads | site | reels | tg | partner ...
Конфиг: /opt/radar/leadbot.env  (LEAD_TOKEN=...)   Запуск: systemd leadbot.service
"""
import asyncio, json, logging, os, time, urllib.parse
import httpx

BASE = os.path.dirname(os.path.abspath(__file__))
CHANNEL = "@fortex_uae"
CONTACT = "Fortex_Dubai"
OWNER_ID = 5887750248
LOG = os.path.join(BASE, "leadbot_leads.jsonl")
STATE_P = os.path.join(BASE, "leadbot_state.json")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("leadbot")


def token():
    for line in open(os.path.join(BASE, "leadbot.env")):
        if line.startswith("LEAD_TOKEN="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("no LEAD_TOKEN in leadbot.env")


TOKEN = token()
API = f"https://api.telegram.org/bot{TOKEN}/"

# --- вопросы: (ключ, текст, [(код, подпись, баллы сложности)]) ---
Q = [
    ("type", "1/6. Какой счёт нужен?", [("corp", "Корпоративный", 0), ("pers", "Личный", 0), ("both", "Оба", 0)]),
    ("pass", "2/6. Какой у вас паспорт?", [("ru", "Только РФ", 1), ("ru2", "РФ + другой", 0), ("oth", "Другой", 0)]),
    ("ref", "3/6. Были отказы или закрытия счетов в банках ОАЭ?",
     [("no", "Нет", 0), ("one", "1 отказ", 2), ("many", "2 и больше", 3), ("closed", "Закрыли счёт", 4)]),
    ("act", "4/6. Чем занимаетесь, откуда деньги?",
     [("trade", "Торговля, ВЭД", 1), ("serv", "Услуги, IT", 0), ("crypto", "Крипта, трейдинг", 3), ("inv", "Инвестиции, другое", 1)]),
    ("res", "5/6. Есть резидентство ОАЭ (Emirates ID)?",
     [("work", "Да, рабочая виза", -1), ("other", "Да, другая виза", 0), ("none", "Нет", 1)]),
    ("comp", "6/6. Есть компания в ОАЭ?", [("yes", "Есть", 0), ("no", "Пока нет", 0), ("abroad", "Есть, но не в ОАЭ", 1)]),
]
QI = {k: i for i, (k, _, _) in enumerate(Q)}
LABEL = {k: {c: l for c, l, _ in opts} for k, _, opts in Q}
PTS = {k: {c: p for c, _, p in opts} for k, _, opts in Q}

ARTICLE = "https://fortex-uae.com/articles/bank-oae-otkazal-nastoyashchaya-prichina/"
GH_REPO = "fortexglobal/fortex-uae-site"
SRC = {"ig": "Instagram", "threads": "Threads", "site": "Сайт", "reels": "Reels", "tg": "Telegram-канал", "direct": "без метки"}
S = {}  # user_id -> {"src","ans":{}, "step", "name", "username"}


def save_state():
    try:
        json.dump(S, open(STATE_P, "w"), ensure_ascii=False)
    except Exception:
        log.exception("state")


def load_state():
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


def need_q(uid, key):
    a = S[uid]["ans"]
    if key == "comp":
        return a.get("type") in ("corp", "both")
    return True


def next_key(uid):
    for k, _, _ in Q:
        if k not in S[uid]["ans"] and need_q(uid, k):
            return k
    return None


async def ask(c, uid, key, msg_id=None):
    _, text, opts = Q[QI[key]]
    total = 5 if S[uid]["ans"].get("type") == "pers" else 6
    num, q = text.split(". ", 1)
    n = num.split("/")[0]
    bar = "●" * int(n) + "○" * (total - int(n))
    text = f"<b>Вопрос {n} из {total}</b>  {bar}\n\n{q}"
    rows = [[{"text": l, "callback_data": f"a:{key}:{code}"}] for code, l, _ in opts]
    if msg_id:
        await call(c, "editMessageText", chat_id=uid, message_id=msg_id, text=text, parse_mode="HTML", reply_markup=kb(rows))
    else:
        await call(c, "sendMessage", chat_id=uid, text=text, parse_mode="HTML", reply_markup=kb(rows))


def score(a):
    return sum(PTS[k].get(v, 0) for k, v in a.items() if k in PTS)


def verdict(a):
    s = score(a)
    if s <= 1:
        head = "🟢 Высокие шансы"
        sub = "Ваш случай банки ОАЭ обычно открывают. Главное: правильно выбрать банк и собрать пакет без лишнего."
    elif s <= 3:
        head = "🟡 Хорошие шансы"
        sub = "Открыть реально, но выбор банка решает. Подача «во все подряд» здесь может навредить."
    elif s <= 5:
        head = "🟠 Сложный случай, но решаемый"
        sub = "Такие счета открываются, но нужен банк, который берёт такие случаи, и аккуратная подготовка к комплаенсу."
    else:
        head = "🔴 Сложный случай: нужен разбор до подачи"
        sub = "Самому подаваться сейчас рискованно: новый отказ закроет ещё часть банков. Сначала разбор, потом подача."
    tips = []
    if a.get("ref") in ("one", "many", "closed"):
        tips.append("Не подавайтесь дальше сами: каждый отказ видят следующие банки.")
    if a.get("act") == "crypto":
        tips.append("Нужен банк, который работает с криптой и трейдингом, и понятное подтверждение источника средств.")
    if a.get("act") == "trade":
        tips.append("Для ВЭД важно, какие валюты и страны контрагентов. Для расчётов с Китаем есть банки со счетами в юанях.")
    if a.get("type") in ("corp", "both") and a.get("comp") in ("no", "abroad"):
        tips.append("Компанию в ОАЭ стоит открывать сразу под банк: фризона и вид деятельности влияют на одобрение.")
    if a.get("type") in ("pers", "both") and a.get("res") == "none":
        tips.append("Личный счёт можно открыть и без резидентства, в том числе удалённо (например, Emirates NBD, около 2 недель).")
    if a.get("res") == "none":
        tips.append("С рабочей визой ОАЭ банки работают охотнее всего, и становится доступна кредитная карта без депозита.")
    if a.get("res") == "work":
        tips.append("Рабочая виза: сильный плюс для банка, с ней открываются и личные, и корпоративные счета.")
    if not tips:
        tips.append("Подберём банк под ваши валюты и обороты, чтобы открыть с первого раза.")
    return head, sub, tips[:3]


def summary(a):
    names = {"type": "счёт", "pass": "паспорт", "ref": "отказы", "act": "деятельность", "res": "резидентство", "comp": "компания в ОАЭ"}
    return "; ".join(f"{names[k]}: {LABEL[k][v]}" for k, v in a.items() if k in LABEL)


async def is_member(c, uid):
    j = await call(c, "getChatMember", chat_id=CHANNEL, user_id=uid)
    return j.get("ok") and j["result"].get("status") in ("member", "administrator", "creator", "restricted")


async def gate(c, uid, msg_id=None):
    text = ("<b>✅ Ваш результат готов</b>\n\n"
            "Чтобы его открыть, подпишитесь на наш канал <b>Fortex UAE</b>.\n\n"
            "Там разборы банков ОАЭ, реальные кейсы и новости для владельцев российского паспорта.\n\n"
            "<i>Подпишитесь и нажмите «Я подписался».</i>")
    rows = [[{"text": "📢 Подписаться на канал", "url": f"https://t.me/{CHANNEL[1:]}"}],
            [{"text": "✅ Я подписался", "callback_data": "chk"}]]
    if msg_id:
        await call(c, "editMessageText", chat_id=uid, message_id=msg_id, text=text, parse_mode="HTML", reply_markup=kb(rows))
    else:
        await call(c, "sendMessage", chat_id=uid, text=text, parse_mode="HTML", reply_markup=kb(rows))


async def result(c, uid):
    st = S[uid]
    a = st["ans"]
    head, sub, tips = verdict(a)
    body = (f"<b>📋 Ваш результат</b>\n\n<b>{head}</b>\n{sub}\n\n"
            f"<b>Что важно в вашем случае</b>\n" + "\n\n".join(f"▪️ {t}" for t in tips))
    body += ("\n\n<b>🎁 Бесплатный разбор за 5 минут</b>\n"
             "Скажем, какие банки откроют именно вам, что подготовить и сколько это займёт.\n\n"
             "<i>Оплата по этапам. Если банк откажет, вернём деньги.</i>")
    pre = f"Здравствуйте! Прошёл проверку шансов в боте: {summary(a)}. Хочу бесплатный разбор."
    url = f"https://t.me/{CONTACT}?text=" + urllib.parse.quote(pre)
    await call(c, "sendMessage", chat_id=uid, text=body, parse_mode="HTML",
               reply_markup=kb([[{"text": "💬 Получить разбор", "url": url}]]
                               + ([[{"text": "📖 Почему банк отказал: разбор", "url": ARTICLE}]] if a.get("ref") in ("one", "many", "closed") else [])
                               + [[{"text": "🔄 Пройти заново", "callback_data": "restart"}]]))
    st.setdefault("done", time.time())
    if not st.get("sent"):
        st["sent"] = True
        rec = {"at": time.strftime("%Y-%m-%d %H:%M"), "uid": uid, "username": st.get("username"), "name": st.get("name"),
               "src": st.get("src"), "ans": a, "score": score(a), "verdict": head}
        open(LOG, "a").write(json.dumps(rec, ensure_ascii=False) + "\n")
        who = f"@{st['username']}" if st.get("username") else f'<a href="tg://user?id={uid}">{st.get("name") or uid}</a>'
        await call(c, "sendMessage", chat_id=OWNER_ID, parse_mode="HTML",
                   text=f"🧲 <b>Лид из бота-проверки</b>\n{who}\nИсточник: {SRC.get(st.get('src'), st.get('src') or '—')}\n"
                        f"{summary(a)}\nОценка: {head}\n\nПодписан на канал ✅")
    save_state()


async def on_message(c, m):
    uid = m["chat"]["id"]
    if m["chat"].get("type") != "private":
        return
    text = m.get("text") or ""
    u = m.get("from", {})
    if text.startswith("/start"):
        src = text.split(" ", 1)[1].strip()[:30] if " " in text else "direct"
        S[uid] = {"src": src, "ans": {}, "t0": time.time(), "name": " ".join(x for x in [u.get("first_name"), u.get("last_name")] if x),
                  "username": u.get("username")}
        save_state()
        if uid == OWNER_ID and src == "direct":
            await call(c, "sendMessage", chat_id=uid, text="Бот работает. Сюда будут приходить лиды. Команда /stats: сколько прошли проверку.")
        await call(c, "sendMessage", chat_id=uid,
                   text="<b>🇦🇪 Откроют ли вам счёт в банке ОАЭ?</b>\n\n"
                        "Проверим за минуту: <b>6 коротких вопросов</b> кнопками.\n\n"
                        "В конце вы получите:\n▪️ оценку шансов по вашему случаю\n▪️ что сделать, чтобы банк не отказал\n"
                        "▪️ бесплатный разбор от специалиста\n\n<i>Fortex UAE, Дубай</i>",
                   parse_mode="HTML", reply_markup=kb([[{"text": "▶️ Начать проверку", "callback_data": "go"}]]))
    elif text.startswith("/stats") and uid == OWNER_ID:
        rows = [json.loads(l) for l in open(LOG)] if os.path.exists(LOG) else []
        by = {}
        for r in rows:
            by[r.get("src") or "—"] = by.get(r.get("src") or "—", 0) + 1
        started = len(S)
        await call(c, "sendMessage", chat_id=uid, text=f"Начали: {started}\nДошли до результата (подписались): {len(rows)}\n"
                   + "\n".join(f"{k}: {v}" for k, v in sorted(by.items(), key=lambda x: -x[1])))
    else:
        await call(c, "sendMessage", chat_id=uid, text="Нажмите /start, чтобы пройти проверку. Вопрос человеку: @" + CONTACT)


async def on_callback(c, q):
    uid = q["from"]["id"]
    data = q.get("data", "")
    msg_id = q["message"]["message_id"]
    if data != "chk":
        await call(c, "answerCallbackQuery", callback_query_id=q["id"])
    if uid not in S:
        S[uid] = {"src": "direct", "ans": {}, "username": q["from"].get("username"), "name": q["from"].get("first_name")}
    if data in ("go", "restart"):
        S[uid]["ans"] = {}
        await ask(c, uid, Q[0][0], msg_id if data == "go" else None)
    elif data.startswith("a:"):
        _, key, code = data.split(":", 2)
        if key in PTS and code in PTS[key]:
            S[uid]["ans"][key] = code
        nk = next_key(uid)
        if nk:
            await ask(c, uid, nk, msg_id)
        elif await is_member(c, uid):
            await call(c, "editMessageText", chat_id=uid, message_id=msg_id, text="<b>Готово ✅</b> Считаем результат…", parse_mode="HTML")
            await result(c, uid)
        else:
            await gate(c, uid, msg_id)
    elif data == "stop":
        S[uid]["stop"] = True
        await call(c, "editMessageReplyMarkup", chat_id=uid, message_id=msg_id, reply_markup=kb([]))
        await call(c, "sendMessage", chat_id=uid, text="Хорошо, больше не пишу. Если появится вопрос, @" + CONTACT)
    elif data == "chk":
        if await is_member(c, uid):
            await call(c, "answerCallbackQuery", callback_query_id=q["id"])
            await call(c, "editMessageText", chat_id=uid, message_id=msg_id, text="<b>Спасибо за подписку ✅</b>", parse_mode="HTML")
            await result(c, uid)
        else:
            await call(c, "answerCallbackQuery", callback_query_id=q["id"], show_alert="true",
                       text="Пока не вижу подписку. Откройте канал, нажмите «Подписаться» и вернитесь сюда.")
    save_state()


FU1 = ("<b>Как ваш вопрос со счётом в ОАЭ?</b>\n\n"
       "Вчера вы проверяли шансы. Если ещё не разобрались, вот что обычно решает дело:\n\n"
       "▪️ правильный банк под ваш случай\n▪️ понятное описание бизнеса и источника денег\n▪️ одна подача вместо пяти\n\n"
       "{case}\n\nРазбор бесплатный и занимает 5 минут.")
FU2 = ("<b>«А если банк всё равно откажет?»</b>\n\n"
       "Самый частый вопрос перед стартом. Поэтому у нас так:\n\n"
       "▪️ оплата по этапам, всю сумму вперёд не берём\n"
       "▪️ откажет банк, предложим другой под вашу задачу\n"
       "▪️ замена не подойдёт, вернём деньги\n\n"
       "Напишите, разберём ваш случай.")
NF = ("<b>Вы не закончили проверку</b>\n\nОсталось пару вопросов, и вы увидите оценку своих шансов на счёт в ОАЭ.")


def case_for(a):
    if a.get("act") == "crypto":
        return "<i>Кейс: крипто-трейдинговая компания, отказы во всех банках. Открыли счёт за 3 недели, паспорт РФ.</i>"
    if a.get("act") == "trade":
        return "<i>Кейс: торговля электроникой с Гонконгом, платежи зависали до 5 дней. Открыли счёт с юанями за 2,5 недели.</i>"
    if a.get("type") == "pers":
        return "<i>Кейс: личный счёт Emirates NBD удалённо, без приезда в Дубай, за 2 недели.</i>"
    return "<i>Кейс: клиенту отказали несколько банков. Подготовили подачу заново и открыли счёт за 3 недели.</i>"


def fu_kb(uid):
    a = S[uid].get("ans", {})
    pre = f"Здравствуйте! Прошёл проверку шансов в боте: {summary(a)}. Хочу бесплатный разбор." if a else "Здравствуйте! Хочу разбор по счёту в ОАЭ."
    return kb([[{"text": "💬 Получить разбор", "url": f"https://t.me/{CONTACT}?text=" + urllib.parse.quote(pre)}],
               [{"text": "Больше не присылать", "callback_data": "stop"}]])


async def followups(c):
    now = time.time()
    for uid, st in list(S.items()):
        if st.get("stop") or uid == OWNER_ID:
            continue
        done = st.get("done")
        try:
            if done and st.get("fu", 0) == 0 and now - done > 24 * 3600:
                st["fu"] = 1
                await call(c, "sendMessage", chat_id=uid, parse_mode="HTML", text=FU1.format(case=case_for(st["ans"])), reply_markup=fu_kb(uid))
            elif done and st.get("fu", 0) == 1 and now - done > 72 * 3600:
                st["fu"] = 2
                await call(c, "sendMessage", chat_id=uid, parse_mode="HTML", text=FU2, reply_markup=fu_kb(uid))
            elif not done and st.get("t0") and not st.get("nf") and now - st["t0"] > 3 * 3600 and now - st["t0"] < 72 * 3600:
                st["nf"] = 1
                await call(c, "sendMessage", chat_id=uid, parse_mode="HTML", text=NF,
                           reply_markup=kb([[{"text": "▶️ Продолжить проверку", "callback_data": "go"}],
                                            [{"text": "Больше не присылать", "callback_data": "stop"}]]))
        except Exception:
            log.exception("followup")
    save_state()


async def push_stats(c):
    """Обезличенная статистика в репозиторий (без имён, ников и id): stats/leadbot.json."""
    try:
        tok = open(os.path.join(BASE, "github_token")).read().strip()
    except Exception:
        return
    rows = [json.loads(l) for l in open(LOG)] if os.path.exists(LOG) else []
    started, finished, verdicts, ans = {}, {}, {}, {}
    for st in S.values():
        k = SRC.get(st.get("src"), st.get("src") or "—")
        started[k] = started.get(k, 0) + 1
    for r in rows:
        k = SRC.get(r.get("src"), r.get("src") or "—")
        finished[k] = finished.get(k, 0) + 1
        verdicts[r["verdict"]] = verdicts.get(r["verdict"], 0) + 1
        for q, v in r.get("ans", {}).items():
            key = f"{q}:{LABEL.get(q, {}).get(v, v)}"
            ans[key] = ans.get(key, 0) + 1
    out = {"updated": time.strftime("%Y-%m-%d %H:%M"), "started_by_source": started, "finished_by_source": finished,
           "verdicts": verdicts, "answers": ans, "followups_sent": sum(st.get("fu", 0) for st in S.values()),
           "stopped": sum(1 for st in S.values() if st.get("stop"))}
    body = json.dumps(out, ensure_ascii=False, indent=1).encode()
    h = {"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json", "User-Agent": "fortex-leadbot"}
    url = f"https://api.github.com/repos/{GH_REPO}/contents/stats/leadbot.json"
    r = await c.get(url, headers=h, params={"ref": "main"})
    sha = r.json().get("sha") if r.status_code == 200 else None
    import base64
    data = {"message": "Lead bot stats", "content": base64.b64encode(body).decode(), "branch": "main"}
    if sha:
        data["sha"] = sha
    r = await c.put(url, headers=h, json=data)
    if r.status_code not in (200, 201):
        log.warning("stats push %s %s", r.status_code, r.text[:200])


async def background(c):
    last_push = 0
    while True:
        await asyncio.sleep(600)
        await followups(c)
        if time.time() - last_push > 6 * 3600:
            last_push = time.time()
            try:
                await push_stats(c)
            except Exception:
                log.exception("stats")


async def main():
    load_state()
    off = 0
    async with httpx.AsyncClient(timeout=70) as c:
        await call(c, "setMyCommands", commands=[{"command": "start", "description": "Проверить шансы на счёт в ОАЭ"}])
        await call(c, "setMyDescription",
                   description="Проверка шансов открыть счёт в банке ОАЭ для владельцев российского паспорта. 6 вопросов, результат за минуту. Fortex UAE, Дубай.")
        await call(c, "setMyShortDescription", short_description="Проверьте шансы открыть счёт в банке ОАЭ за минуту")
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
