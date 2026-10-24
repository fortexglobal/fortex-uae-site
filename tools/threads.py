"""Threads @fortex__uae: публикация постов и поиск потенциальных клиентов по ключевым словам.

Посты: threads/src/<slug>.json
  {"text": "...", "publish_at": "2026-10-26T09:30+04:00", "status": "approved",
   "image": "threads/img/<file>.jpg" (необязательно), "kind": "стёб|польза|новость|вопрос"}
Поиск: threads/queries.json (список запросов) → threads/leads/<YYYY-MM-DD>.json (новые посты, без повторов).
Ключ: THREADS_TOKEN (секрет GitHub).

python3 tools/threads.py publish   — опубликовать всё, у чего наступило время
python3 tools/threads.py search    — собрать свежие посты по запросам
python3 tools/threads.py refresh   — продлить токен (раз в месяц)
"""
import glob, json, os, sys, time, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API = "https://graph.threads.net/v1.0"
TOKEN = os.environ.get("THREADS_TOKEN", "")
DUBAI = timezone(timedelta(hours=4))
D = os.path.join(ROOT, "threads")


def call(method, path, **params):
    params["access_token"] = TOKEN
    q = urllib.parse.urlencode(params)
    url = f"{API}/{path}"
    req = urllib.request.Request(url + ("?" + q if method == "GET" else ""), data=None if method == "GET" else q.encode(), method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:400]
        raise RuntimeError(f"{e.code} {body}")


def sha():
    import subprocess
    return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=ROOT).stdout.strip()


def publish():
    status_p = os.path.join(D, "status.json")
    st = json.load(open(status_p)) if os.path.exists(status_p) else {}
    now = datetime.now(DUBAI)
    done = 0
    for f in sorted(glob.glob(os.path.join(D, "src", "*.json"))):
        slug = os.path.basename(f)[:-5]
        src = json.load(open(f, encoding="utf-8"))
        if src.get("status") != "approved" or st.get(slug, {}).get("id"):
            continue
        if datetime.fromisoformat(src["publish_at"]) > now:
            continue
        if done >= 1:  # не больше одного поста за запуск
            break
        params = {"media_type": "TEXT", "text": src["text"][:500]}
        if src.get("image"):
            params = {"media_type": "IMAGE", "text": src["text"][:500],
                      "image_url": f"https://raw.githubusercontent.com/fortexglobal/fortex-uae-site/{sha()}/{src['image']}"}
        try:
            c = call("POST", "me/threads", **params)
            time.sleep(8 if src.get("image") else 2)
            r = call("POST", "me/threads_publish", creation_id=c["id"])
            info = call("GET", r["id"], fields="permalink")
            st[slug] = {"id": r["id"], "url": info.get("permalink", ""), "at": now.isoformat(timespec="minutes")}
            print("published", slug, st[slug]["url"])
            done += 1
        except Exception as e:
            st[slug] = {"error": str(e)[:300], "at": now.isoformat(timespec="minutes")}
            print("error", slug, e)
        json.dump(st, open(status_p, "w"), ensure_ascii=False, indent=1)


def search():
    qs = json.load(open(os.path.join(D, "queries.json"), encoding="utf-8"))
    seen_p = os.path.join(D, "seen.json")
    seen = set(json.load(open(seen_p))) if os.path.exists(seen_p) else set()
    day = datetime.now(DUBAI).date().isoformat()
    out_p = os.path.join(D, "leads", f"{day}.json")
    os.makedirs(os.path.dirname(out_p), exist_ok=True)
    out = json.load(open(out_p)) if os.path.exists(out_p) else []
    since = int(time.time()) - 3 * 86400
    for q in qs[:25]:
        try:
            res = call("GET", "keyword_search", q=q, search_type="RECENT", since=since, limit=25,
                       fields="id,text,username,permalink,timestamp,media_type,has_replies,is_reply")
        except Exception as e:
            print("search", q, e)
            continue
        for p in res.get("data", []):
            if p["id"] in seen or not p.get("text") or p.get("username") == "fortex__uae":
                continue
            seen.add(p["id"])
            out.append({"q": q, "id": p["id"], "user": p.get("username", ""), "url": p.get("permalink", ""),
                        "at": p.get("timestamp", ""), "text": p["text"][:1500], "is_reply": p.get("is_reply", False)})
        time.sleep(1)
    json.dump(out, open(out_p, "w"), ensure_ascii=False, indent=1)
    json.dump(sorted(seen)[-5000:], open(seen_p, "w"))
    print("leads", len(out))


ALPHA = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"


def code_to_id(code):
    n = 0
    for ch in code[:11]:
        n = n * 64 + ALPHA.index(ch)
    return str(n)


def probe():
    out = {}
    pr = json.load(open(os.path.join(D, "probe.json")))
    if isinstance(pr, dict) and pr.get("reply_test"):
        pid = code_to_id(pr["reply_test"])
        try:
            c = call("POST", "me/threads", media_type="TEXT", text="test", reply_to_id=pid)
            out["reply_container"] = c  # контейнер не публикуем, он истечёт сам
        except Exception as e:
            out["reply_container_error"] = str(e)[:400]
        json.dump(out, open(os.path.join(D, "probe_out.json"), "w"), ensure_ascii=False, indent=1)
        print(out)
        return
    for code in json.load(open(os.path.join(D, "probe.json"))):
        pid = code_to_id(code)
        try:
            out[code] = {"id": pid, "ok": call("GET", pid, fields="id,text,username,permalink")}
        except Exception as e:
            out[code] = {"id": pid, "error": str(e)[:300]}
    json.dump(out, open(os.path.join(D, "probe_out.json"), "w"), ensure_ascii=False, indent=1)
    print(out)


REPLY_PROMPT = """Ты ведёшь Threads @fortex__uae (Fortex UAE, Дубай: счета в банках ОАЭ, Emirates ID, рабочие визы, компании). Тон: живой, с лёгкой иронией, коротко, на «вы» или как пишет собеседник.
Наш пост: «{post}»
Комментарий @{user}: «{text}»
Ответь одним-двумя короткими предложениями (до 200 знаков): поддержи разговор, ответь по сути, можно с юмором, можно короткий встречный вопрос. Если человек спрашивает про счёт, визу или компанию, ответь по делу и предложи написать в Telegram @Fortex_Dubai. Без длинных тире, без хэштегов, без обещаний «100%», без цен кроме «от X».
Если комментарий спам, реклама, оскорбление, политика или ответ не нужен (одно эмодзи, «+»), верни ровно SKIP."""


def llm(prompt):
    key = os.environ.get("OPENROUTER_API_KEY", "")
    for m in ("anthropic/claude-sonnet-4.5", "openai/gpt-4.1"):
        try:
            req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions",
                                         data=json.dumps({"model": m, "max_tokens": 200, "messages": [{"role": "user", "content": prompt}]}).encode(),
                                         headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
            return json.loads(urllib.request.urlopen(req, timeout=60).read())["choices"][0]["message"]["content"].strip()
        except Exception as e:
            print("llm", m, e)
    return ""


def replies():
    """Отвечаем на комментарии под НАШИМИ постами за последние 7 дней."""
    st = json.load(open(os.path.join(D, "status.json"))) if os.path.exists(os.path.join(D, "status.json")) else {}
    rp = os.path.join(D, "replied.json")
    done = json.load(open(rp)) if os.path.exists(rp) else {}
    srcs = {os.path.basename(f)[:-5]: json.load(open(f, encoding="utf-8")) for f in glob.glob(os.path.join(D, "src", "*.json"))}
    me = call("GET", "me", fields="username").get("username", "fortex__uae")
    sent = 0
    for slug, info in st.items():
        if not info.get("id") or sent >= 10:
            continue
        if datetime.now(DUBAI) - datetime.fromisoformat(info["at"]) > timedelta(days=7):
            continue
        try:
            conv = call("GET", f"{info['id']}/replies", fields="id,text,username,timestamp,hide_status", reverse="false")
        except Exception as e:
            print("replies", slug, e)
            continue
        for c in conv.get("data", []):
            if c["id"] in done or c.get("username") == me or not c.get("text") or c.get("hide_status", "NOT_HUSHED") != "NOT_HUSHED":
                continue
            ans = llm(REPLY_PROMPT.format(post=srcs.get(slug, {}).get("text", "")[:400], user=c.get("username", ""), text=c["text"][:500]))
            ans = ans.replace("—", ",").replace("–", ",").strip().strip("«»\"")
            if not ans or ans.upper().startswith("SKIP"):
                done[c["id"]] = "skip"
                continue
            try:
                cont = call("POST", "me/threads", media_type="TEXT", text=ans[:480], reply_to_id=c["id"])
                time.sleep(3)
                r = call("POST", "me/threads_publish", creation_id=cont["id"])
                done[c["id"]] = r["id"]
                sent += 1
                print("replied", c.get("username"), ans)
            except Exception as e:
                done[c["id"]] = "error " + str(e)[:200]
                print("reply error", e)
            json.dump(done, open(rp, "w"), ensure_ascii=False, indent=1)
            time.sleep(20)
    json.dump(done, open(rp, "w"), ensure_ascii=False, indent=1)
    print("replies sent", sent)


def check():
    me = call("GET", "me", fields="id,username,threads_profile_picture_url")
    json.dump({"username": me.get("username"), "id": me.get("id"), "checked": datetime.now(DUBAI).isoformat(timespec="minutes")},
              open(os.path.join(D, "me.json"), "w"), ensure_ascii=False, indent=1)
    print("token ok:", me.get("username"))


def refresh():
    r = urllib.request.urlopen(f"https://graph.threads.net/refresh_access_token?grant_type=th_refresh_token&access_token={TOKEN}", timeout=60)
    print("refreshed, expires_in", json.loads(r.read()).get("expires_in"))


if __name__ == "__main__":
    if not TOKEN:
        print("no THREADS_TOKEN, skip")
        sys.exit(0)
    {"publish": publish, "search": search, "refresh": refresh, "check": check, "probe": probe, "replies": replies}[sys.argv[1]]()
