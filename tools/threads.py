"""Threads @fortex__uae: публикация постов и поиск потенциальных клиентов по ключевым словам.

Посты: threads/src/<slug>.json
  {"text": "...", "publish_at": "2026-10-26T09:30+04:00", "status": "approved",
   "image": "threads/img/<file>.jpg" (необязательно), "kind": "стёб|польза|новость|вопрос"}
Поиск: threads/queries.json (список запросов) → threads/leads/<YYYY-MM-DD>.json (новые посты, без повторов).
Ключ: THREADS_TOKEN (секрет GitHub).

python3 tools/threads.py publish   — опубликовать всё, у чего наступило время
python3 tools/threads.py search    — собрать свежие посты по запросам
python3 tools/threads.py refresh   — продлить токен (раз в месяц)
python3 tools/threads.py replies   — диалоги в комментариях под нашими постами
python3 tools/threads.py insights  — статистика постов и аккаунта → threads/stats/
"""
import glob, json, os, sys, time, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API = "https://graph.threads.net/v1.0"
TOKEN = os.environ.get("THREADS_TOKEN", "")
DUBAI = timezone(timedelta(hours=4))
D = os.path.join(ROOT, "threads")
TOPIC = "Дубай"  # решение Александра 31.10: все посты с темой «Дубай» (самая большая подборка)


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


def recent_posts(limit=25):
    try:
        return call("GET", "me/threads", fields="id,text,timestamp,permalink", limit=limit).get("data", [])
    except Exception as e:
        print("recent posts:", e)
        return []


def norm(t):
    return " ".join((t or "").split())[:120]


def already_posted(text):
    n = norm(text)
    for p in recent_posts():
        if norm(p.get("text")) == n:
            return p
    return None


def dedupe():
    """Удалить повторы наших постов (одинаковый текст): оставляем самый ранний."""
    seen, out = {}, []
    for p in sorted(recent_posts(50), key=lambda x: x.get("timestamp", "")):
        n = norm(p.get("text"))
        if not n:
            continue
        if n in seen:
            try:
                call("DELETE", p["id"])
                out.append({"deleted": p.get("permalink"), "text": n[:60]})
            except Exception as e:
                out.append({"not_deleted": p.get("permalink"), "text": n[:60], "error": str(e)[:200]})
        else:
            seen[n] = p["id"]
    json.dump(out, open(os.path.join(D, "dedupe.json"), "w"), ensure_ascii=False, indent=1)
    print(json.dumps(out, ensure_ascii=False, indent=1))


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
        dup = already_posted(src["text"])
        if dup:  # такой текст уже вышел (параллельный запуск): не публикуем второй раз
            st[slug] = {"id": dup["id"], "url": dup.get("permalink", ""), "at": now.isoformat(timespec="minutes"), "dedup": True}
            json.dump(st, open(status_p, "w"), ensure_ascii=False, indent=1)
            print("already posted", slug)
            continue
        params = {"media_type": "TEXT", "text": src["text"][:500]}
        imgs = src.get("images") or []
        if len(imgs) >= 2:  # подборка фото (карусель, до 10 штук)
            base = f"https://raw.githubusercontent.com/fortexglobal/fortex-uae-site/{sha()}/"
            try:
                kids = [call("POST", "me/threads", media_type="IMAGE", is_carousel_item="true", image_url=base + im)["id"] for im in imgs[:10]]
                time.sleep(10)
                params = {"media_type": "CAROUSEL", "text": src["text"][:500], "children": ",".join(kids)}
            except Exception as e:
                st[slug] = {"error": "carousel: " + str(e)[:280], "at": now.isoformat(timespec="minutes")}
                json.dump(st, open(status_p, "w"), ensure_ascii=False, indent=1)
                continue
        elif imgs and not src.get("image"):
            src["image"] = imgs[0]
        if src.get("image") and params["media_type"] == "TEXT":
            params = {"media_type": "IMAGE", "text": src["text"][:500],
                      "image_url": f"https://raw.githubusercontent.com/fortexglobal/fortex-uae-site/{sha()}/{src['image']}"}
        topic = src.get("topic", TOPIC)
        if topic:  # тема публикации (кликабельная «Дубай» рядом с именем): посты с темой получают больше показов
            params["topic_tag"] = topic
        try:
            try:
                c = call("POST", "me/threads", **params)
            except RuntimeError as e:
                if "topic" not in str(e).lower() or "topic_tag" not in params:
                    raise
                print("topic_tag rejected, posting without it:", str(e)[:200])
                params.pop("topic_tag")
                c = call("POST", "me/threads", **params)
            time.sleep(8 if (src.get("image") or imgs) else 2)
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


REPLY_PROMPT = """Ты ведёшь Threads @fortex__uae (Fortex UAE, Дубай: счета в банках ОАЭ, Emirates ID, рабочие визы, компании). Задача: поддержать разговор так, чтобы людям было приятно и смешно, и пост получал больше активности. Тон: живой, тёплый, с лёгкой иронией, как пишет собеседник (на «ты» или «вы»).
Наш пост: «{post}»
Ветка до этого:
{thread}
Новый комментарий @{user}: «{text}»
Ответь 1–2 короткими предложениями (до 200 знаков): отреагируй на то, что человек сказал, коротким утверждением с юмором или лёгкой иронией на эту тему (согласись, подшути, добавь меткий факт). Вопросов не задавай, знак «?» не используй. Если человек сам спрашивает про счёт, визу или компанию: ответь по сути одной фразой и скажи, что в Telegram @Fortex_Dubai бесплатно разберём его случай (консультация бесплатная). Без эмодзи и смайликов, только русские слова (без английских вставок), без длинных тире, без хэштегов, без ссылок, без обещаний «100%», без цен кроме «от X». Не продавай, если не спрашивают.
Если это спам, реклама, оскорбление, политика или просто одно эмодзи без слов, верни ровно SKIP."""

HOT_WORDS = ("счёт", "счет", "банк", "виз", "emirates", "эмирейтс", "компани", "лиценз", "сколько стоит", "цена", "стоимость", "помогите", "подскажите", "как открыть", "отказ")


def llm(prompt):
    key = os.environ.get("OPENROUTER_API_KEY", "")
    for m in ("anthropic/claude-sonnet-4.5", "openai/gpt-4.1"):
        try:
            req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions",
                                         data=json.dumps({"model": m, "max_tokens": 200, "messages": [{"role": "user", "content": prompt}]}).encode(),
                                         headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
            return json.loads(urllib.request.urlopen(req, timeout=60).read())["choices"][0]["message"]["content"].strip()
        except Exception as e:
            body = e.read().decode()[:200] if hasattr(e, "read") else ""
            print("llm", m, e, body)
            LLM_ERR.append(f"{m}: {e} {body}")
    return ""


LLM_ERR = []


def replies():
    """Ведём диалоги под НАШИМИ постами за последние 10 дней: отвечаем на комментарии и на ответы нам (до 3 наших ответов одному человеку в ветке)."""
    st = json.load(open(os.path.join(D, "status.json"))) if os.path.exists(os.path.join(D, "status.json")) else {}
    rp = os.path.join(D, "replied.json")
    done = json.load(open(rp)) if os.path.exists(rp) else {}
    hp = os.path.join(D, "hot.json")
    hot = json.load(open(hp)) if os.path.exists(hp) else []
    srcs = {os.path.basename(f)[:-5]: json.load(open(f, encoding="utf-8")) for f in glob.glob(os.path.join(D, "src", "*.json"))}
    me = call("GET", "me", fields="username").get("username", "fortex__uae")
    sent = 0
    for slug, info in st.items():
        if not info.get("id") or sent >= 8:
            continue
        if datetime.now(DUBAI) - datetime.fromisoformat(info["at"]) > timedelta(days=10):
            continue
        try:
            conv = call("GET", f"{info['id']}/conversation", fields="id,text,username,timestamp,hide_status,replied_to", reverse="false")
        except Exception as e:
            print("conversation", slug, e)
            continue
        items = conv.get("data", [])
        by_id = {c["id"]: c for c in items}
        ours = {c["id"] for c in items if c.get("username") == me}
        for c in items:
            if c["id"] in done or c.get("username") == me or not c.get("text") or c.get("hide_status", "NOT_HUSHED") != "NOT_HUSHED":
                continue
            parent = (c.get("replied_to") or {}).get("id")
            if parent and parent != info["id"] and parent not in ours:
                done[c["id"]] = "not-to-us"  # люди спорят между собой, не встреваем
                continue
            user = c.get("username", "")
            n_ours = sum(1 for k, v in done.items() if isinstance(v, dict) and v.get("user") == user and v.get("post") == slug)
            if n_ours >= 3:
                done[c["id"]] = "limit"
                continue
            chain, p = [], parent
            while p and p in by_id and len(chain) < 6:
                chain.insert(0, f"@{by_id[p].get('username')}: {by_id[p].get('text', '')[:200]}")
                p = (by_id[p].get("replied_to") or {}).get("id")
            ans = llm(REPLY_PROMPT.format(post=srcs.get(slug, {}).get("text", "")[:400], thread="\n".join(chain) or "(нет)",
                                          user=user, text=c["text"][:500]))
            import re as _r, random as _rnd
            ans = _r.sub(r"\s*[—–]\s*", ", ", ans).strip().strip("«»\"")
            ans = _r.sub(r"\s+([,.!…)])", r"\1", ans)
            if _rnd.random() > 0.1:  # смайлик примерно в 1 ответе из 10
                ans = _r.sub(r"\s*([\U0001F300-\U0001FAFF\u2600-\u27BF]|[:;]-?\)+|\)+$)", "", ans).strip()
            if "?" in ans and not ans.upper().startswith("SKIP"):
                import re as _re
                keep = [x.strip() for x in _re.findall(r"[^.!?…]+[.!?…]*", ans) if x.strip() and "?" not in x]
                ans = " ".join(keep) if keep else ans.replace("?", ".")
            if any(w in c["text"].lower() for w in HOT_WORDS):
                hot.append({"at": datetime.now(DUBAI).isoformat(timespec="minutes"), "user": user, "text": c["text"][:300], "post": info.get("url", ""), "sent": False})
            if not ans:
                print("llm empty, retry later", LLM_ERR[-1:] )
                json.dump({"at": datetime.now(DUBAI).isoformat(timespec="minutes"), "err": LLM_ERR[-2:]}, open(os.path.join(D, "llm_error.json"), "w"), ensure_ascii=False)
                continue  # не помечаем, попробуем в следующий прогон
            if ans.upper().startswith("SKIP"):
                done[c["id"]] = {"skip": c["text"][:120], "user": user}
                continue
            try:
                cont = call("POST", "me/threads", media_type="TEXT", text=ans[:480], reply_to_id=c["id"])
                time.sleep(3)
                r = call("POST", "me/threads_publish", creation_id=cont["id"])
                done[c["id"]] = {"id": r["id"], "user": user, "post": slug, "text": ans}
                sent += 1
                print("replied", user, ans)
            except Exception as e:
                done[c["id"]] = "error " + str(e)[:200]
                print("reply error", e)
            json.dump(done, open(rp, "w"), ensure_ascii=False, indent=1)
            time.sleep(15)
    json.dump(done, open(rp, "w"), ensure_ascii=False, indent=1)
    json.dump(hot[-200:], open(hp, "w"), ensure_ascii=False, indent=1)
    print("replies sent", sent)


def insights():
    """Статистика: просмотры, лайки, ответы, репосты по каждому посту за 14 дней и по аккаунту. threads/stats/latest.json и <дата>.json."""
    st = json.load(open(os.path.join(D, "status.json"))) if os.path.exists(os.path.join(D, "status.json")) else {}
    srcs = {os.path.basename(f)[:-5]: json.load(open(f, encoding="utf-8")) for f in glob.glob(os.path.join(D, "src", "*.json"))}
    out = {"generated": datetime.now(DUBAI).isoformat(timespec="minutes"), "posts": [], "errors": []}
    for slug, info in st.items():
        if not info.get("id") or datetime.now(DUBAI) - datetime.fromisoformat(info["at"]) > timedelta(days=14):
            continue
        row = {"slug": slug, "at": info["at"], "url": info.get("url"), "kind": srcs.get(slug, {}).get("kind"), "text": srcs.get(slug, {}).get("text", "")[:120]}
        try:
            r = call("GET", f"{info['id']}/insights", metric="views,likes,replies,reposts,quotes,shares")
            for m in r.get("data", []):
                row[m["name"]] = (m.get("values") or [{}])[0].get("value", m.get("total_value", {}).get("value"))
        except Exception as e:
            out["errors"].append(f"{slug}: {str(e)[:200]}")
        out["posts"].append(row)
    now = int(time.time())
    for label, days in (("account_1d", 1), ("account_7d", 7)):
        try:
            r = call("GET", "me/threads_insights", metric="views,likes,replies,reposts,quotes,followers_count", since=now - days * 86400, until=now)
            acc = {}
            for m in r.get("data", []):
                if "total_value" in m:
                    acc[m["name"]] = m["total_value"].get("value")
                else:
                    acc[m["name"]] = sum(v.get("value", 0) for v in m.get("values", []))
            out[label] = acc
        except Exception as e:
            out["errors"].append(f"{label}: {str(e)[:200]}")
    # просмотры страницы (профиля) по дням за 7 дней и клики по ссылкам в шапке
    try:
        r = call("GET", "me/threads_insights", metric="views", since=now - 7 * 86400, until=now)
        for m in r.get("data", []):
            out["profile_views_by_day"] = [{"date": v.get("end_time", "")[:10], "views": v.get("value")} for v in m.get("values", [])]
    except Exception as e:
        out["errors"].append(f"profile_views: {str(e)[:200]}")
    try:
        r = call("GET", "me/threads_insights", metric="clicks", since=now - 7 * 86400, until=now)
        out["link_clicks_7d"] = r.get("data", [])
    except Exception as e:
        out["errors"].append(f"clicks: {str(e)[:200]}")
    kinds = {}
    for p in out["posts"]:
        k = p.get("kind") or "—"
        kinds.setdefault(k, {"posts": 0, "views": 0, "replies": 0, "likes": 0})
        kinds[k]["posts"] += 1
        for m in ("views", "replies", "likes"):
            kinds[k][m] += p.get(m) or 0
    out["by_kind"] = {k: {**v, "avg_views": round(v["views"] / v["posts"], 1), "avg_replies": round(v["replies"] / v["posts"], 2)} for k, v in kinds.items()}
    os.makedirs(os.path.join(D, "stats"), exist_ok=True)
    for name in ("latest.json", datetime.now(DUBAI).date().isoformat() + ".json"):
        json.dump(out, open(os.path.join(D, "stats", name), "w"), ensure_ascii=False, indent=1)
    print("insights", len(out["posts"]), "posts, errors:", out["errors"][:3])


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
    {"publish": publish, "dedupe": dedupe, "search": search, "refresh": refresh, "check": check, "probe": probe, "replies": replies, "insights": insights}[sys.argv[1]]()
