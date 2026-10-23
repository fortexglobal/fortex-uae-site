"""Instagram: проверка токена и публикация утверждённых каруселей ig/src/*.json (в GitHub Actions).
Картинки берутся из ig/<slug>/render.json и отдаются Instagram по ссылкам raw.githubusercontent.com.
После публикации: status=published, permalink. Токен: секрет IG_TOKEN."""
import glob, json, os, subprocess, sys, time, urllib.parse, urllib.request

T = os.environ.get("IG_TOKEN", "")
API = "https://graph.instagram.com/v21.0"
RAW = "https://raw.githubusercontent.com/fortexglobal/fortex-uae-site/main"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def call(method, path, **params):
    params["access_token"] = T
    data = urllib.parse.urlencode(params).encode()
    url = f"{API}/{path}"
    q = method in ("GET", "DELETE")
    req = urllib.request.Request(url + ("?" + data.decode() if q else ""), None if q else data, method=method)
    try:
        return json.load(urllib.request.urlopen(req, timeout=120))
    except urllib.error.HTTPError as e:
        return {"error": e.read().decode()[:500]}


def wait_ready(cid):
    """Ждём, пока Instagram обработает контейнер (status_code FINISHED)."""
    for i in range(40):
        st = call("GET", cid, fields="status_code").get("status_code")
        if st == "FINISHED":
            return True
        if st == "ERROR":
            return False
        time.sleep(4)
    return False


def publish_container(cid):
    """media_publish с повторами: сразу после создания контейнер бывает ещё «не найден»."""
    p = {}
    for i in range(6):
        p = call("POST", "me/media_publish", creation_id=cid)
        if "id" in p:
            return p
        time.sleep(6)
    return p


def publish_stories(imgs):
    ids = []
    for u in imgs:
        c = call("POST", "me/media", image_url=u, media_type="STORIES")
        if "id" not in c:
            return {"error": c, "done": ids}
        wait_ready(c["id"])
        p = publish_container(c["id"])
        if "id" not in p:
            return {"error": p, "done": ids}
        ids.append(p["id"])
        time.sleep(3)
    return {"id": ids[0] if ids else "", "ids": ids, "permalink": "https://www.instagram.com/stories/fortex__uae/"}


def publish_reel(video_url, cover_url, caption):
    c = call("POST", "me/media", media_type="REELS", video_url=video_url, cover_url=cover_url, caption=caption, share_to_feed="true")
    if "id" not in c:
        return {"error": c}
    ok = False
    for i in range(60):  # видео обрабатывается до нескольких минут
        st = call("GET", c["id"], fields="status_code,status").get("status_code")
        if st == "FINISHED":
            ok = True; break
        if st == "ERROR":
            return {"error": call("GET", c["id"], fields="status")}
        time.sleep(6)
    if not ok:
        return {"error": "video processing timeout"}
    p = publish_container(c["id"])
    if "id" not in p:
        return {"error": p}
    return {"id": p["id"], "permalink": call("GET", p["id"], fields="permalink").get("permalink", "")}


def publish(item):
    imgs = item["images"]
    if item.get("format") == "stories":
        return publish_stories(imgs)
    if len(imgs) == 1:
        c = call("POST", "me/media", image_url=imgs[0], caption=item["caption"])
    else:
        kids = []
        for u in imgs:
            k = call("POST", "me/media", image_url=u, is_carousel_item="true")
            if "id" not in k:
                return {"error": k}
            kids.append(k["id"])
        for k in kids:
            wait_ready(k)
        c = call("POST", "me/media", media_type="CAROUSEL", children=",".join(kids), caption=item["caption"])
    if "id" not in c:
        return {"error": c}
    wait_ready(c["id"])
    p = publish_container(c["id"])
    if "id" not in p:
        return {"error": p}
    link = call("GET", p["id"], fields="permalink").get("permalink", "")
    return {"id": p["id"], "permalink": link}


def lock(path, slug):
    import subprocess
    run = lambda *c: subprocess.run(["git", "-C", ROOT, *c], capture_output=True).returncode == 0
    if not (run("add", path) and run("commit", "-m", f"IG publishing: {slug}")):
        return False
    if run("push"):
        return True
    # чужие коммиты: подтягиваем; если тот же файл менял другой запуск, rebase упадёт
    if not run("pull", "--rebase", "--autostash"):
        run("rebase", "--abort")
        return False
    return run("push")


def main():
    me = call("GET", "me", fields="user_id,username,account_type,media_count")
    out = {"checked": time.strftime("%Y-%m-%dT%H:%MZ", time.gmtime()), "me": me, "published": []}
    # удаление постов по списку ig/delete.json {"ids": [...]}
    dp = os.path.join(ROOT, "ig", "delete.json")
    if "error" not in me and os.path.exists(dp):
        dj = json.load(open(dp))
        dj.setdefault("done", {})
        for mid in dj.get("ids", []):
            if mid in dj["done"] and dj["done"][mid] == "deleted":
                continue
            r = call("DELETE", mid)
            dj["done"][mid] = "deleted" if r.get("success") else str(r)[:300]
        json.dump(dj, open(dp, "w"), ensure_ascii=False, indent=1)
        out["deleted"] = dj["done"]
    recent = call("GET", "me/media", fields="id,caption,permalink", limit="50").get("data", []) if "error" not in me else []
    if "error" not in me:
        srcs = [(f, False) for f in sorted(glob.glob(os.path.join(ROOT, "ig", "src", "*.json")))] + \
               [(f, True) for f in sorted(glob.glob(os.path.join(ROOT, "ig", "reels", "src", "*.json")))]
        for f, is_reel in srcs:
            slug = os.path.basename(f)[:-5]
            item = json.load(open(f, encoding="utf-8"))
            if is_reel:
                item["format"] = "reel"
            meta = os.path.join(ROOT, "ig", "reels", slug, "render.json") if is_reel else os.path.join(ROOT, "ig", slug, "render.json")
            if item.get("status") != "approved" or not os.path.exists(meta):
                continue
            # publish_at (ISO с часовым поясом, напр. 2026-10-26T19:07+04:00): не раньше этого времени, по одному за запуск
            if item.get("publish_at"):
                from datetime import datetime, timezone
                if datetime.fromisoformat(item["publish_at"]) > datetime.now(timezone.utc):
                    continue
                if any(x.get("scheduled") == item.get("format", "carousel") for x in out["published"]):
                    continue
            # защита от дублей: такой пост уже есть в Instagram
            if item.get("format") != "stories" and item.get("caption"):
                same = [m for m in recent if (m.get("caption") or "").strip() == item["caption"].strip()]
                if same:
                    item.update(status="published", result={"id": same[0]["id"], "permalink": same[0].get("permalink", ""), "dedup": True})
                    json.dump(item, open(f, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
                    continue
            # блокировка: отмечаем «publishing» и пушим, если другой запуск успел раньше, push не пройдёт
            item["status"] = "publishing"
            json.dump(item, open(f, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            if not lock(f, slug):
                print("lock failed, другой запуск уже публикует", slug)
                break
            if is_reel:
                m = json.load(open(meta))
                sha = subprocess.run(["git", "-C", ROOT, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
                cdn = f"https://cdn.jsdelivr.net/gh/fortexglobal/fortex-uae-site@{sha}/ig/reels/{slug}"
                res = publish_reel(f"{cdn}/{m['video']}", f"{cdn}/{m['cover']}", item.get("caption", ""))
                item.pop("format", None)
            else:
                item["images"] = [f"{RAW}/ig/{slug}/{x}" for x in json.load(open(meta))["files"]]
                if item.get("format") != "stories":
                    item["images"] = item["images"][:10]
                res = publish(item)
                item.pop("images")
            item.update(status="published" if "id" in res else "error", result=res,
                        published_at=time.strftime("%Y-%m-%dT%H:%MZ", time.gmtime()))
            json.dump(item, open(f, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            out["published"].append({"slug": slug, "scheduled": item.get("format", "carousel") if item.get("publish_at") else "", **res})
    if "error" not in me:
        out["media"] = call("GET", "me/media", fields="id,timestamp,permalink,media_type,caption", limit="25").get("data", [])
        for m in out["media"]:
            m["caption"] = (m.get("caption") or "")[:60]
    json.dump(out, open(os.path.join(ROOT, "ig", "status.json"), "w"), ensure_ascii=False, indent=1)
    print(json.dumps(out, ensure_ascii=False)[:800])


if __name__ == "__main__":
    main()
