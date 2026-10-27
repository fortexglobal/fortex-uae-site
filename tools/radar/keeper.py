"""Смотритель Fortex на сервере (systemd: keeper). Раз в минуту:
1. Публикации минута в минуту: если пост Threads или Instagram пора выпускать, запускает GitHub-workflow сразу,
   не дожидаясь опаздывающего расписания GitHub.
2. Ответы в Threads: каждые 5 минут днём (08:00–01:00 Дубай), ночью раз в 20 минут.
3. Балансы: OpenRouter (и Apify, если задан токен). Меньше порога: сообщение в Telegram.
4. Работоспособность: сайт, сервисы radar и leadbot, упавшие запуски GitHub, посты, которые не вышли вовремя.
Сообщения: бот радара → владельцу. Одна и та же проблема не чаще раза в 6 часов, о восстановлении пишет отдельно.
Настройки: /opt/keeper/keeper.env (KEY=VALUE), состояние: /opt/keeper/state.json.
"""
import glob, json, os, subprocess, time, traceback, urllib.request, urllib.error
from datetime import datetime, timedelta, timezone

DUBAI = timezone(timedelta(hours=4))
HOME = "/opt/keeper"
SITE = os.path.join(HOME, "site")
REPO = "fortexglobal/fortex-uae-site"
ENV = {}
for line in open(os.path.join(HOME, "keeper.env")):
    if "=" in line and not line.startswith("#"):
        k, v = line.strip().split("=", 1)
        ENV[k] = v
GH = open("/opt/radar/github_token").read().strip()
LOW = float(ENV.get("LOW_BALANCE", "5"))
SP = os.path.join(HOME, "state.json")
S = json.load(open(SP)) if os.path.exists(SP) else {}
S.setdefault("alerts", {}); S.setdefault("last", {}); S.setdefault("seen_fail", [])


def save():
    json.dump(S, open(SP, "w"), ensure_ascii=False, indent=1)


def http(url, data=None, headers=None, method=None, timeout=30):
    req = urllib.request.Request(url, data=json.dumps(data).encode() if data is not None else None,
                                 headers={"User-Agent": "fortex-keeper", **(headers or {})}, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode()
            return r.status, (json.loads(body) if body.strip().startswith(("{", "[")) else body)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:300]
    except Exception as e:
        return 0, str(e)[:300]


def tg(text):
    http(f"https://api.telegram.org/bot{ENV['BOT_TOKEN']}/sendMessage",
         {"chat_id": ENV.get("OWNER_ID", "5887750248"), "text": text, "disable_web_page_preview": True})


def alert(key, text, every_h=6):
    """Проблема: пишем сразу, потом не чаще раза в every_h часов."""
    a = S["alerts"].get(key)
    if not a or time.time() - a > every_h * 3600:
        tg("⚠️ " + text)
        S["alerts"][key] = time.time()


def ok(key, text):
    """Проблема ушла: одно сообщение и сброс."""
    if key in S["alerts"]:
        del S["alerts"][key]
        tg("✅ " + text)


def every(key, minutes):
    if time.time() - S["last"].get(key, 0) >= minutes * 60:
        S["last"][key] = time.time()
        return True
    return False


def dispatch(wf):
    code, body = http(f"https://api.github.com/repos/{REPO}/actions/workflows/{wf}/dispatches", {"ref": "main"},
                      {"Authorization": f"Bearer {GH}", "Accept": "application/vnd.github+json"}, "POST")
    if code != 204:
        alert("gh-dispatch", f"Смотритель не может запустить публикацию на GitHub ({code}). Токену GitHub на сервере нужно право Actions: Read and write.\n{str(body)[:150]}")
    else:
        ok("gh-dispatch", "Смотритель снова запускает публикации на GitHub.")
    print(datetime.now(DUBAI).strftime("%H:%M"), "dispatch", wf, code, flush=True)
    return code == 204


def selfupdate():
    """Новая версия смотрителя в репозитории: копируем и перезапускаемся (systemd поднимет)."""
    for helper in ("replies_dump.py",):  # вспомогательные скрипты для радара
        src, dst = os.path.join(SITE, "tools", "radar", helper), os.path.join("/opt/radar", helper)
        if os.path.exists(src) and (not os.path.exists(dst) or open(src).read() != open(dst).read()):
            open(dst, "w").write(open(src).read())
    new = os.path.join(SITE, "tools", "radar", "keeper.py")
    if os.path.exists(new) and open(new).read() != open(__file__).read():
        subprocess.run(["python3", "-m", "py_compile", new], check=True)
        open(__file__, "w").write(open(new).read())
        print("keeper updated, restart", flush=True)
        os._exit(0)


RADAR_FILES = {"radar": ["autoreply.py", "starters.py", "content.py", "igdm.py", "reactions.py", "newsfeed.py", "kb.md", "server/radar.py"],
               "leadbot": ["leadbot.py"]}


def deploy_radar():
    """Обновления ассистента из репозитория: только файлы, которые уже стоят на сервере.
    Бэкап → проверка синтаксиса → перезапуск → если сервис не поднялся, откат и сообщение."""
    for svc, files in RADAR_FILES.items():
        changed = []
        for f in files:
            src, dst = os.path.join(SITE, "tools", "radar", f), os.path.join("/opt/radar", os.path.basename(f))
            if f.startswith("server/") and os.path.exists(src) and any(x in open(src, encoding="utf-8").read() for x in
                    ("<BOT_TOKEN>", "<OPENROUTER_KEY>", "<GITHUB_TOKEN>", "<HEX32>", "<PHONE>", "<API_ID>", "<SECRET>")):
                continue
            if os.path.exists(src) and os.path.exists(dst) and open(src, "rb").read() != open(dst, "rb").read():
                changed.append((src, dst))
        if not changed:
            continue
        if any(s.endswith(".py") and subprocess.run(["python3", "-m", "py_compile", s]).returncode for s, _ in changed):
            alert(f"deploy-{svc}", f"Обновление {svc} не поставил: ошибка в коде. Работает прежняя версия.", 24)
            continue
        for src, dst in changed:
            subprocess.run(["cp", "-p", dst, dst + ".prev"])
            open(dst, "wb").write(open(src, "rb").read())
            subprocess.run(["chown", "radar:radar", dst])
        subprocess.run(["systemctl", "restart", svc]); time.sleep(12)
        if subprocess.run(["systemctl", "is-active", svc], capture_output=True, text=True).stdout.strip() != "active":
            for _, dst in changed:
                subprocess.run(["cp", "-p", dst + ".prev", dst])
            subprocess.run(["systemctl", "restart", svc])
            alert(f"deploy-{svc}", f"Обновление {svc} не запустилось, вернул прежнюю версию.", 24)
        else:
            names = ", ".join(os.path.basename(d) for _, d in changed)
            print("deployed", svc, names, flush=True)
            tg(f"🔄 Ассистент обновлён: {names}")


def export_radar():
    """Копия radar.py с сервера в репозиторий (tools/radar/server/radar.py) без секретов: чтобы правки
    карточек и логики делались по точному коду. Ключи, токены, api_hash, телефоны вырезаются."""
    import base64, hashlib, re as _re
    try:
        src = open("/opt/radar/radar.py", encoding="utf-8").read()
    except Exception:
        return
    red = src
    red = _re.sub(r"\b\d{8,11}:[A-Za-z0-9_-]{30,}\b", "<BOT_TOKEN>", red)
    red = _re.sub(r"sk-or-v1-[A-Za-z0-9]+", "<OPENROUTER_KEY>", red)
    red = _re.sub(r"github_pat_[A-Za-z0-9_]+|gh[pousr]_[A-Za-z0-9]{20,}", "<GITHUB_TOKEN>", red)
    red = _re.sub(r"\b[0-9a-f]{32}\b", "<HEX32>", red)
    red = _re.sub(r"\+\d[\d ()-]{8,}\d", "<PHONE>", red)
    red = _re.sub(r"(?i)(api_id\s*=\s*)\d+", r"\1<API_ID>", red)
    red = _re.sub(r"(?i)((?:key|token|secret|password|hash)\w*\s*=\s*)([\"'])[^\"']{12,}\2", r"\1\2<SECRET>\2", red)
    h = hashlib.sha1(red.encode()).hexdigest()
    if S.get("radar_export") == h:
        return
    url = f"https://api.github.com/repos/{REPO}/contents/tools/radar/server/radar.py"
    hd = {"Authorization": f"Bearer {GH}", "Accept": "application/vnd.github+json"}
    code, cur = http(url, headers=hd)
    body = {"message": "Сервер: копия radar.py без секретов", "content": base64.b64encode(red.encode()).decode(), "branch": "main"}
    if code == 200 and isinstance(cur, dict):
        body["sha"] = cur["sha"]
    code, r = http(url, body, hd, "PUT")
    if code in (200, 201):
        S["radar_export"] = h
        print("radar.py exported", flush=True)
    else:
        print("export failed", code, str(r)[:200], flush=True)


def pull():
    if not os.path.isdir(os.path.join(SITE, ".git")):
        subprocess.run(["git", "clone", "-q", "--depth", "1", f"https://github.com/{REPO}", SITE], check=True)
    subprocess.run(["git", "-C", SITE, "fetch", "-q", "--depth", "1", "origin", "main"], check=True, timeout=60)
    subprocess.run(["git", "-C", SITE, "reset", "-q", "--hard", "origin/main"], check=True)


def load(p):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return {}


def due_posts():
    """Что пора выпускать: (threads[], instagram[]) — слаги с publish_at в прошлом (не старше суток), ещё не вышедшие."""
    now = datetime.now(timezone.utc)
    st = load(os.path.join(SITE, "threads", "status.json"))
    th, ig = [], []
    for f in glob.glob(os.path.join(SITE, "threads", "src", "*.json")):
        s, slug = load(f), os.path.basename(f)[:-5]
        if s.get("status") == "approved" and s.get("publish_at") and not st.get(slug, {}).get("id"):
            at = datetime.fromisoformat(s["publish_at"])
            if now - timedelta(days=1) < at <= now:
                th.append((slug, at))
    for f, reel in [(f, False) for f in glob.glob(os.path.join(SITE, "ig", "src", "*.json"))] + \
                   [(f, True) for f in glob.glob(os.path.join(SITE, "ig", "reels", "src", "*.json"))]:
        s, slug = load(f), os.path.basename(f)[:-5]
        meta = os.path.join(SITE, "ig", "reels" if reel else "", slug, "render.json")
        if s.get("status") in ("approved", "publishing") and s.get("publish_at") and os.path.exists(meta):
            at = datetime.fromisoformat(s["publish_at"])
            if now - timedelta(days=1) < at <= now:
                ig.append((slug, at))
    return th, ig


def publications():
    th, ig = due_posts()
    now = datetime.now(timezone.utc)
    if th and every("th-due", 4):
        dispatch("threads-fast.yml")
    if ig and every("ig-due", 6):
        dispatch("ig-publish.yml")
    for name, items in (("Threads", th), ("Instagram", ig)):
        late = [s for s, at in items if now - at > timedelta(minutes=40)]
        if late:
            alert(f"late-{name}", f"{name}: пост не вышел вовремя (больше 40 минут): {', '.join(late)}. Проверяю дальше.", 3)
        else:
            ok(f"late-{name}", f"{name}: отложенные посты вышли.")


def replies():
    h = datetime.now(DUBAI).hour
    if every("replies", 5 if (h >= 8 or h < 1) else 20):
        dispatch("threads-fast.yml")


def balances():
    if not every("balances", 60):
        return
    key = ENV.get("OPENROUTER_KEY")
    if key:
        code, r = http("https://openrouter.ai/api/v1/credits", headers={"Authorization": f"Bearer {key}"})
        if code == 200 and isinstance(r, dict):
            d = r.get("data", {})
            left = float(d.get("total_credits", 0)) - float(d.get("total_usage", 0))
            S["openrouter_left"] = round(left, 2)
            if left < LOW:
                alert("bal-openrouter", f"OpenRouter: осталось ${left:.2f}. Когда кончится, встанут ассистент в чатах, директ Instagram и автоответы в Threads.\nПополнить: https://openrouter.ai/settings/credits", 12)
            else:
                ok("bal-openrouter", f"OpenRouter пополнен: ${left:.2f}.")
    tok = ENV.get("APIFY_TOKEN")
    if tok:
        code, r = http("https://api.apify.com/v2/users/me/limits", headers={"Authorization": f"Bearer {tok}"})
        if code == 200 and isinstance(r, dict):
            d = r.get("data", {})
            left = float(d.get("limits", {}).get("maxMonthlyUsageUsd", 0)) - float(d.get("current", {}).get("monthlyUsageUsd", 0))
            S["apify_left"] = round(left, 2)
            if left < LOW:
                alert("bal-apify", f"Apify: до лимита месяца осталось ${left:.2f}. Когда кончится, утренние тренды Threads не соберутся.\nhttps://console.apify.com/billing", 12)
            else:
                ok("bal-apify", f"Apify: снова есть запас, ${left:.2f}.")


def health():
    if every("site", 10):
        code, _ = http("https://fortex-uae.com/", timeout=20)
        if code != 200:
            S["site_fail"] = S.get("site_fail", 0) + 1
            if S["site_fail"] >= 2:
                alert("site", f"Сайт fortex-uae.com не открывается (код {code}).", 2)
        else:
            S["site_fail"] = 0
            ok("site", "Сайт снова открывается.")
    if every("services", 3):
        for svc, what in (("radar", "Ассистент в Telegram-чатах (radar)"), ("leadbot", "Бот-проверка @FortexCheck_Bot")):
            r = subprocess.run(["systemctl", "is-active", svc], capture_output=True, text=True).stdout.strip()
            if r != "active":
                subprocess.run(["systemctl", "restart", svc])
                time.sleep(5)
                r = subprocess.run(["systemctl", "is-active", svc], capture_output=True, text=True).stdout.strip()
                if r != "active":
                    alert(f"svc-{svc}", f"{what} остановлен, перезапуск не помог.", 2)
                    continue
                tg(f"🔁 {what} падал, смотритель перезапустил.")
            ok(f"svc-{svc}", f"{what} снова работает.")
    if every("gh-runs", 15):
        code, r = http(f"https://api.github.com/repos/{REPO}/actions/runs?per_page=30",
                       headers={"Authorization": f"Bearer {GH}", "Accept": "application/vnd.github+json"})
        if code == 200 and isinstance(r, dict):
            since = datetime.now(timezone.utc) - timedelta(hours=2)
            for run in r.get("workflow_runs", []):
                if run.get("conclusion") == "failure" and run["id"] not in S["seen_fail"] and \
                        datetime.fromisoformat(run["created_at"].replace("Z", "+00:00")) > since:
                    S["seen_fail"] = (S["seen_fail"] + [run["id"]])[-200:]
                    tg(f"⚠️ GitHub: упал запуск «{run['name']}». {run['html_url']}")
    # OpenRouter молчит у автоответа (файл пишет tools/threads.py при сбое модели)
    e = load(os.path.join(SITE, "threads", "llm_error.json"))
    # разовые сбои (500) не тревожим, только когда кончились деньги или сломан ключ
    if e.get("at") and any(c in str(e.get("err")) for c in ("402", "401", "403")) and \
            datetime.now(DUBAI) - datetime.fromisoformat(e["at"]) < timedelta(minutes=30):
        alert("llm", "Автоответ в Threads не получил текст от нейросети: " + str(e.get("err", ""))[:200], 6)


def step(name, fn):
    try:
        fn()
    except Exception as e:
        tb = traceback.format_exc()
        print(tb, flush=True)
        errs = S.setdefault("errors", [])
        errs.append([datetime.now(DUBAI).strftime("%d.%m %H:%M"), name, f"{type(e).__name__}: {e}"[:300], tb[-600:]])
        S["errors"] = errs[-15:]


def push_status():
    """Состояние смотрителя в репозиторий (keeper/status.json): ошибки, балансы, что выложено. Для разбора без доступа к серверу."""
    import base64
    st = {"at": datetime.now(DUBAI).isoformat(timespec="minutes"), "errors": S.get("errors", []),
          "openrouter_left": S.get("openrouter_left"), "apify_left": S.get("apify_left"),
          "alerts": {k: datetime.fromtimestamp(v, DUBAI).strftime("%d.%m %H:%M") for k, v in S.get("alerts", {}).items()},
          "services": {svc: subprocess.run(["systemctl", "is-active", svc], capture_output=True, text=True).stdout.strip() for svc in ("radar", "leadbot", "keeper")},
          "radar_files": {f: datetime.fromtimestamp(os.path.getmtime(os.path.join("/opt/radar", os.path.basename(f))), DUBAI).strftime("%d.%m %H:%M") for f in sum(RADAR_FILES.values(), []) if os.path.exists(os.path.join("/opt/radar", os.path.basename(f)))}}
    key = ENV.get("OPENROUTER_KEY")
    if key:  # расход OpenRouter: по ключу и по моделям за последние дни
        c1, k = http("https://openrouter.ai/api/v1/key", headers={"Authorization": f"Bearer {key}"})
        st["openrouter_key"] = k.get("data") if c1 == 200 and isinstance(k, dict) else f"{c1} {str(k)[:150]}"
        c2, a = http("https://openrouter.ai/api/v1/activity", headers={"Authorization": f"Bearer {key}"})
        st["openrouter_activity"] = a.get("data") if c2 == 200 and isinstance(a, dict) else f"{c2} {str(a)[:150]}"
    try:  # сколько раз за сутки радар звал нейросеть (по журналу)
        j = subprocess.run(["journalctl", "-u", "radar", "--since", "24 hours ago", "--no-pager", "-o", "cat"], capture_output=True, text=True, timeout=60).stdout
        st["radar_log_24h"] = {"lines": j.count("\n"), "llm_warn": j.count("LLM "), "wealth": j.count("wealth "),
                               "scan_model": j.count("scan model"), "openrouter_http": j.count("openrouter.ai")}
    except Exception as e:
        st["radar_log_24h"] = str(e)[:100]
    url = f"https://api.github.com/repos/{REPO}/contents/keeper/status.json"
    hd = {"Authorization": f"Bearer {GH}", "Accept": "application/vnd.github+json"}
    code, cur = http(url, headers=hd)
    body = {"message": "Смотритель: состояние", "content": base64.b64encode(json.dumps(st, ensure_ascii=False, indent=1).encode()).decode(), "branch": "main"}
    if code == 200 and isinstance(cur, dict):
        body["sha"] = cur["sha"]
    code, r = http(url, body, hd, "PUT")
    if code not in (200, 201):
        raise RuntimeError(f"status push {code}: {str(r)[:200]}")


def main():
    if not S.get("started"):
        tg("Смотритель запущен: публикации минута в минуту, ответы в Threads каждые 5 минут, балансы и работоспособность под контролем.")
        S["started"] = time.time()
    while True:
        t = time.time()
        if every("pull", 1):
            step("pull", pull)
            step("selfupdate", selfupdate)
            step("deploy", deploy_radar)
        if every("export", 30):
            step("export", export_radar)
        step("publications", publications)
        step("replies", replies)
        step("balances", balances)
        step("health", health)
        if every("status", 15) or not S.get("status_v2"):
            S["status_v2"] = 1
            step("status", push_status)
        save()
        time.sleep(max(5, 60 - (time.time() - t)))


if __name__ == "__main__":
    main()
