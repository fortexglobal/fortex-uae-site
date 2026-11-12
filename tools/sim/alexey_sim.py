"""Прогон Алексея на виртуальных клиентах (тест Александра 12.11.2026).

Алексей отвечает своим настоящим «мозгом»: тот же SYSTEM, та же база знаний tools/radar/kb.md, тот же выбор длины ответа,
та же нарезка на сообщения и та же модель, что на сервере. Клиентов играет другая нейросеть по карточкам tools/sim/personas.json.
В реальный Telegram ничего не уходит. Итог: sim/out/<метка>/ (переписки, оценки, отчёт).
Запуск: GitHub Actions «Alexey sim» при изменении tools/sim/request.json (поля: n, ids, label).
"""
import asyncio, json, os, random, re, sys, time
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools", "radar"))
import httpx  # noqa: E402
import igdm, autoreply  # noqa: E402

KEY = os.environ["OPENROUTER_API_KEY"]
igdm.CTX["openrouter_key"] = KEY
DXB = timezone(timedelta(hours=4))
CLIENT_MODEL = "openai/gpt-4.1-mini"
JUDGE_MODEL = "openai/gpt-4.1"
MAX_TURNS = int(os.environ.get("SIM_TURNS", "11"))
SEM = asyncio.Semaphore(5)
BUDGET = {"start": None, "max": 3.0, "stop": False}


async def spent():
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.get("https://openrouter.ai/api/v1/key", headers={"Authorization": f"Bearer {KEY}"})
            return float(r.json()["data"]["usage"])
    except Exception as e:
        print("usage err", e)
        return None


async def over_budget():
    u = await spent()
    if u is None or BUDGET["start"] is None:
        return BUDGET["stop"]
    if u - BUDGET["start"] > BUDGET["max"]:
        BUDGET["stop"] = True
        print("BUDGET STOP", round(u - BUDGET["start"], 2))
    return BUDGET["stop"]


async def chat(model, system, user, temp=0.7, max_tokens=1500):
    async with httpx.AsyncClient(timeout=180) as c:
        for attempt in range(3):
            try:
                r = await c.post("https://openrouter.ai/api/v1/chat/completions",
                                 headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
                                 json={"model": model, "temperature": temp, "max_tokens": max_tokens,
                                       "response_format": {"type": "json_object"},
                                       "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]})
                if r.status_code == 200:
                    m = re.search(r"\{.*\}", r.json()["choices"][0]["message"]["content"], re.S)
                    if m:
                        return json.loads(m.group(0))
            except Exception as e:
                print("chat err", model, e)
            await asyncio.sleep(3 + attempt * 5)
    return None


CLIENT_SYS = """Ты играешь живого человека, который пишет в личные сообщения Telegram компании Fortex UAE (визы, Emirates ID, счета в банках ОАЭ, компании, ипотека через рабочую визу). Тебе отвечает Алексей.
Твоя карточка:
{card}
Правила игры:
- Пиши как настоящий человек в мессенджере, в своём стиле из карточки: коротко, иногда опечатки, иногда два сообщения подряд. Не будь «удобным» клиентом: у тебя свои сомнения, бюджет, недоверие, жизнь.
- Используй возражения из карточки по ходу разговора, когда это естественно, не все сразу. Можно своими словами.
- Скрытые потребности раскрывай, только если Алексей спросит в тему или предложит.
- Ты ничего не знаешь о ценах и правилах заранее, кроме того, что написано в карточке.
- Если Алексей отвечает как бот (простыни, канцелярит, одно и то же), можешь это заметить вслух, как заметил бы человек.
- Если тебя устроило и предложили созвон, соглашайся, когда это соответствует карточке, и называй удобный день. Если Алексей просит контакт, у тебя Telegram @{uname}.
- Заканчивай разговор, когда по-человечески всё ясно: договорились, отказался, ушёл подумать, или тебе неинтересно. Не тяни разговор искусственно.
Ответь JSON: {{"messages": ["<сообщение 1>", "<сообщение 2, если нужно>"], "end": false, "why": "<если end: почему ушёл>"}}"""

JUDGE_SYS = """Ты строгий руководитель отдела продаж и эксперт по переписке в мессенджерах. Оцени, как сотрудник «Алексей» (Fortex UAE) провёл переписку с клиентом в Telegram.
Требования Александра к Алексею:
1) Не должно быть заметно, что это бот: живой тон, короткие сообщения (1–3 предложения), не простыни, не канцелярит, не повторы, разная длина, не допрос, на «ты», без длинных тире, без слова «профиль», без «по опыту», смайлы редко.
2) Нормально объясняет: по делу, понятно, факты только из базы знаний, ничего не выдумывает.
3) Отрабатывает возражения: спокойно, аргументами, сначала соглашается («да, понимаю»), не спорит.
4) Закрывает: ведёт к созвону в Zoom (спрашивает удобный день) или к передаче руководителю, не упускает готового клиента.
5) Допродаёт (апсейл): узнаёт другие потребности (счёт, карта, визы семье, компания, ипотека) и уместно, без давления, предлагает другие услуги.
6) Правила: минимальные цены только чтобы удержать уходящего клиента, не в первом ответе; не обещает 100% и одобрение; не помогает серым схемам; честно отвечает «ассистент», если спросили, бот ли он; не называет минимальную цену сразу.
Ниже база знаний (факты, которые Алексей мог использовать), карточка клиента и переписка. Тайминги указаны в квадратных скобках.
Ответь JSON:
{"human": 1-10, "explain": 1-10, "objections": 1-10, "closing": 1-10, "upsell": 1-10, "overall": 1-10,
 "outcome": "созвон|передан руководителю|клиент думает|клиент ушёл|отказали правильно|завис",
 "bot_tells": ["<конкретные места, где видно бота, с цитатой>"],
 "fact_errors": ["<выдуманные или неверные относительно базы факты, с цитатой>"],
 "missed": ["<упущенные возможности: закрыть, допродать, ответить на возражение>"],
 "best": "<лучший момент с цитатой>",
 "fix": ["<конкретные правки в правилах Алексея, 1–3 пункта>"]}"""


def fmt_dur(s):
    return f"{int(s)} с" if s < 90 else f"{s / 60:.1f} мин"


async def alexey_turn(cv):
    """Повтор логики igdm._reply_to для Telegram без отправки."""
    extra = ""
    if cv.get("pending_q"):
        extra = f"\n\nСейчас мы ждём ответ коллег на вопрос: «{cv['pending_q']}». Не обещай ответ ещё раз, но можешь продолжать разговор по другим темам."
    call = cv.get("call") or {}
    if call.get("status") == "proposed":
        extra += (f"\n\nМы предложили клиенту созвон в Zoom: {igdm.call_when(call['at'])}. Если клиент согласен на это время, action call_ok и короткое подтверждение "
                  "(что ссылку на Zoom пришлёшь перед началом). Если просит другой день или время, action call и в call_days его вариант.")
    elif call.get("status") == "confirmed":
        extra += (f"\n\nСозвон в Zoom уже подтверждён: {igdm.call_when(call['at'])}. Ссылку пришлём за 5 минут до начала. "
                  "Если клиент подтверждает, что всё в силе, ответь коротко. Если просит перенести, action call и в call_days новый вариант.")
    if cv.get("lead_sent"):
        extra += ("\n\nКлиент уже передан руководителю. Не проси контакт снова и не делай action handoff. "
                  "Отвечай коротко на его вопросы по базе знаний, а если вопрос про следующий шаг, скажи, что руководитель уже в курсе и скоро напишет с аккаунта @FortexGlobal. "
                  "Если он просто благодарит или прощается, ответь одной короткой фразой.")
    if cv.get("source") == "напрямую" and not cv.get("asked_src") and sum(1 for h in cv["history"] if h["role"] == "bot") >= 2:
        extra += ("\n\nМы не знаем, откуда клиент о нас узнал. В этом сообщении, если это к месту (не в разгар важного вопроса), "
                  "между делом один раз спроси, где он нас нашёл («Кстати, подскажите, где вы нас нашли?»). Больше этот вопрос не задавай.")
        cv["asked_src"] = True
    size = igdm.pick_length(cv)
    uname = cv["username"]
    extra += ("\n\nКанал: Telegram (личные сообщения). Здесь ты Алексей и пишешь от первого лица («я», «у нас с командой»). "
              "Алексей живёт в Дубай Марине, в Дубае с 2022 года, с командой помогает с банками, визами и компаниями в ОАЭ. "
              "Это можно коротко и по-свойски рассказать, если спросят или к слову, можно чуть поболтать про жизнь в Дубае с лёгкой иронией, "
              "но разговор мягко возвращай к задаче клиента и к сделке. Других личных подробностей не придумывай. "
              "Пиши как в мессенджере: короткие предложения, каждое уйдёт отдельным сообщением, без кавычек, максимум 3–4 предложения."
              f" Контакт клиента уже есть: @{uname}. Контакт НЕ проси: когда клиент готов, сразу action handoff.")
    sysk = igdm.SYSTEM + igdm.kb()
    t0 = time.time()
    res = await igdm.llm(sysk, f"Клиент: @{uname}\nПереписка:\n{igdm.transcript(cv)}{extra}\n\n"
                               f"Длина этого ответа: {igdm.LENGTHS[size]}. Не делай его похожим по длине и построению на наши прошлые сообщения.\n"
                               f"Напиши следующее сообщение клиенту.")
    if res and res.get("reply") and not res.get("then") and igdm.DEFER_RE.search(res["reply"]) and len(res["reply"]) < 120:
        res = await igdm.llm(sysk, f"Клиент: @{uname}\nПереписка:\n{igdm.transcript(cv)}{extra}\n\n"
                                   f"Твой вариант «{res['reply']}» только обещает ответ. Дай сам ответ сейчас: {igdm.LENGTHS['detail']}.\n"
                                   f"Напиши следующее сообщение клиенту.") or res
    think = time.time() - t0
    return res, size, think


async def run_dialog(p, outdir):
    async with SEM:
        uname = p["name"].lower() + str(random.randint(10, 99))
        cv = {"uid": "tg:0", "username": uname, "history": [], "source": p.get("src", "напрямую"), "name": None}
        log = []  # для отчёта: (кто, текст, тайминг)
        first = True
        client_sys = CLIENT_SYS.format(card=json.dumps(p, ensure_ascii=False, indent=1), uname=uname)
        user_msgs = [p["opening"]]
        outcome_actions = []
        for turn in range(MAX_TURNS):
            if await over_budget():
                log.append(("Система", "(прогон остановлен: лимит бюджета)", ""))
                break
            now = time.time()
            for m in user_msgs:
                cv["history"].append({"role": "user", "text": m, "ts": now})
                log.append(("Клиент", m, ""))
            cv["last_user_ts"] = now
            res, size, think = await alexey_turn(cv)
            act = (res or {}).get("action", "none")
            outcome_actions.append(act)
            if not res:
                log.append(("Система", "(Алексей не ответил: ошибка модели)", ""))
                break
            if act == "ignore":
                log.append(("Алексей", "(не ответил: action ignore, диалог заглушен)", ""))
                break
            if act == "react":
                log.append(("Алексей", f"(поставил реакцию {res.get('reaction') or '👍'})", ""))
                cv["history"].append({"role": "note", "text": "(поставили реакцию, разговор на паузе)", "ts": time.time()})
            else:
                text = igdm.tame_emoji(igdm.clean(res.get("reply") or ""), cv)
                parts = autoreply._parts(text)
                delay = random.uniform(*igdm.DELAY) if first else 1 + think
                first = False
                for i, part in enumerate(parts):
                    typing = max(3.0, min(40.0, 1.5 + len(part) / 4.0)) * random.uniform(0.85, 1.15)
                    tag = f"[ответ через {fmt_dur(delay)}, печатал {fmt_dur(typing)}]" if i == 0 else f"[печатал {fmt_dur(typing)}]"
                    log.append(("Алексей", part, tag))
                cv["history"].append({"role": "bot", "text": text, "ts": time.time()})
                if res.get("then"):
                    then = igdm.tame_emoji(igdm.clean(res["then"]), cv)
                    mins = max(2.0, min(6.0, float(res.get("then_min") or 4)))
                    for part in autoreply._parts(then):
                        log.append(("Алексей", part, f"[через {mins:.0f} мин, «посчитал»]"))
                    cv["history"].append({"role": "bot", "text": then, "ts": time.time()})
            for k in ("name", "summary", "services"):
                if res.get(k):
                    cv[k] = res[k]
            if act in ("ask_owner", "money_check"):
                cv["pending_q"] = res.get("owner_question")
                log.append(("Система", f"(вопрос руководителю: {res.get('owner_question')})", ""))
            elif act == "call":
                day = (datetime.now(DXB) + timedelta(days=2)).replace(hour=15, minute=0, second=0, microsecond=0)
                cv["call"] = {"status": "proposed", "at": day.timestamp(), "min": 60}
                cv["pending_q"] = None
                prop = await igdm.llm(igdm.REWRITE_CALL + f"\nСегодня {datetime.now(DXB):%Y-%m-%d, %A}.",
                                      f"Ответ Александра: давай {igdm.call_when(day.timestamp())}\nПереписка:\n{igdm.transcript(cv, 8)}")
                ptxt = igdm.clean((prop or {}).get("reply") or f"Давай {igdm.call_when(day.timestamp())}, удобно?")
                log.append(("Система", f"(Александр в боте ответил время: {igdm.call_when(day.timestamp())})", ""))
                for part in autoreply._parts(ptxt):
                    log.append(("Алексей", part, "[ответ от руководителя, пересказ]"))
                cv["history"].append({"role": "bot", "text": ptxt, "ts": time.time()})
            elif act == "call_ok" and cv.get("call"):
                cv["call"]["status"] = "confirmed"
                log.append(("Система", "(созвон подтверждён, ушёл в календарь)", ""))
            elif act in ("handoff", "partner", "alert"):
                cv["lead_sent"] = True
                log.append(("Система", f"(action {act}: передан Александру)", ""))
            elif act == "close":
                log.append(("Система", "(Алексей закрыл разговор)", ""))
                break
            convo = "\n".join(f"{w}: {t}" for w, t, _ in log if w != "Система")
            cr = await chat(CLIENT_MODEL, client_sys, f"Переписка до сих пор:\n{convo}\n\nТвой ход. Ответь JSON.")
            if not cr or cr.get("end") and not cr.get("messages"):
                log.append(("Клиент", f"(ушёл: {(cr or {}).get('why', '')})", ""))
                break
            user_msgs = [m for m in (cr.get("messages") or []) if str(m).strip()][:3]
            if cr.get("end"):
                for m in user_msgs:
                    log.append(("Клиент", m, ""))
                    cv["history"].append({"role": "user", "text": m, "ts": time.time()})
                res2, _, _ = await alexey_turn(cv)
                if res2 and res2.get("action") != "react" and res2.get("reply"):
                    for part in autoreply._parts(igdm.clean(res2["reply"])):
                        log.append(("Алексей", part, "[финал]"))
                elif res2:
                    log.append(("Алексей", "(поставил реакцию 👍)", ""))
                log.append(("Клиент", f"(закончил: {cr.get('why', '')})", ""))
                break
        md = f"# {p['id']} {p['name']}: {p['goal']}\n\n_{p['who']}_\n\n" + "\n".join(
            f"**{w}:** {t} {('`' + tg + '`') if tg else ''}" for w, t, tg in log)
        convo = "\n".join(f"{w}: {t} {tg}" for w, t, tg in log)
        verdict = await chat(JUDGE_MODEL, JUDGE_SYS, f"БАЗА ЗНАНИЙ:\n{igdm.kb()}\n\nКАРТОЧКА КЛИЕНТА:\n{json.dumps(p, ensure_ascii=False)}\n\nПЕРЕПИСКА:\n{convo}",
                             temp=0.2, max_tokens=2500) or {}
        bot_parts = [t for w, t, _ in log if w == "Алексей" and not t.startswith("(")]
        verdict["stats"] = {"bot_msgs": len(bot_parts), "avg_len": round(sum(map(len, bot_parts)) / max(1, len(bot_parts))),
                            "max_len": max(map(len, bot_parts)) if bot_parts else 0, "actions": outcome_actions,
                            "dash": sum(("—" in t or "–" in t) for t in bot_parts), "vy": sum(bool(re.search(r"\b(вы|вам|вас|ваш\w*)\b", t, re.I)) for t in bot_parts),
                            "questions_per_msg": round(sum(t.count("?") for t in bot_parts) / max(1, len(bot_parts)), 2)}
        open(os.path.join(outdir, "dialogs", f"{p['id']}.md"), "w").write(md + "\n\n## Оценка\n```json\n" + json.dumps(verdict, ensure_ascii=False, indent=1) + "\n```\n")
        print("done", p["id"], verdict.get("overall"), verdict.get("outcome"))
        return {"id": p["id"], "name": p["name"], "goal": p["goal"], **verdict}


SUMMARY_SYS = """Ты руководитель отдела продаж. Ниже оценки 30 тестовых переписок ассистента «Алексей» (Fortex UAE) с разными клиентами. Сделай для владельца (Александр) отчёт на русском в Markdown, коротко и по делу, без воды, без длинных тире:
1) Итог одной строкой и средние баллы (живость, объяснение, возражения, закрытие, допродажа, общий).
2) Исходы: сколько созвонов, передано руководителю, думают, ушли, правильно отказали.
3) Топ-5 проблем, по которым видно бота или теряются продажи, каждая с 1–2 цитатами и номерами диалогов.
4) Что получается хорошо (3 пункта с цитатами).
5) Конкретные правки в правилах Алексея (до 8 пунктов), сформулированные так, чтобы их можно было сразу вписать в инструкцию.
6) Три лучших и три худших диалога по номерам с одной фразой почему.
Верни JSON: {"report": "<markdown>"}"""


async def main():
    req = json.load(open(os.path.join(ROOT, "tools", "sim", "request.json")))
    personas = json.load(open(os.path.join(ROOT, "tools", "sim", "personas.json")))
    if req.get("ids"):
        personas = [p for p in personas if p["id"] in req["ids"]]
    personas = personas[: int(req.get("n", 30))]
    label = req.get("label") or datetime.now(DXB).strftime("%Y%m%d-%H%M")
    outdir = os.path.join(ROOT, "sim", "out", label)
    os.makedirs(os.path.join(outdir, "dialogs"), exist_ok=True)
    BUDGET["start"] = await spent()
    BUDGET["max"] = float(req.get("budget_usd", 3.0))
    results = await asyncio.gather(*[run_dialog(p, outdir) for p in personas], return_exceptions=True)
    ok = [r for r in results if isinstance(r, dict)]
    for r in results:
        if not isinstance(r, dict):
            print("dialog failed:", r)
    json.dump(ok, open(os.path.join(outdir, "results.json"), "w"), ensure_ascii=False, indent=1)
    keys = ["human", "explain", "objections", "closing", "upsell", "overall"]
    avg = {k: round(sum(float(r.get(k) or 0) for r in ok) / max(1, len(ok)), 1) for k in keys}
    brief = [{k: r.get(k) for k in ["id", "name", "goal", *keys, "outcome", "bot_tells", "fact_errors", "missed", "best", "fix", "stats"]} for r in ok]
    rep = await chat(JUDGE_MODEL, SUMMARY_SYS, f"Средние: {json.dumps(avg, ensure_ascii=False)}\n\nОценки:\n{json.dumps(brief, ensure_ascii=False)}",
                     temp=0.3, max_tokens=4000) or {}
    table = "| № | Клиент | Цель | Живость | Объясн. | Возраж. | Закрытие | Допрод. | Общий | Исход |\n|---|---|---|---|---|---|---|---|---|---|\n" + "\n".join(
        f"| {r['id']} | {r['name']} | {r['goal']} | {r.get('human')} | {r.get('explain')} | {r.get('objections')} | {r.get('closing')} | {r.get('upsell')} | {r.get('overall')} | {r.get('outcome')} |"
        for r in sorted(ok, key=lambda x: x["id"]))
    open(os.path.join(outdir, "report.md"), "w").write(
        f"# Тест Алексея на {len(ok)} виртуальных клиентах ({label})\n\nСредние: {json.dumps(avg, ensure_ascii=False)}\n\n"
        + (rep.get("report") or "(сводка не собралась)") + "\n\n## Все диалоги\n\n" + table + "\n")
    end = await spent()
    open(os.path.join(outdir, "report.md"), "a").write(f"\nПотрачено на прогон: ${(end or 0) - (BUDGET['start'] or 0):.2f}\n")
    print("REPORT READY", outdir, avg)


if __name__ == "__main__":
    asyncio.run(main())
