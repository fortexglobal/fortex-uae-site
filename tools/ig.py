"""Instagram: проверка токена и публикация утверждённых каруселей ig/src/*.json (в GitHub Actions).
Картинки берутся из ig/<slug>/render.json и отдаются Instagram по ссылкам raw.githubusercontent.com.
После публикации: status=published, permalink. Токен: секрет IG_TOKEN."""
import glob, json, os, sys, time, urllib.parse, urllib.request

T = os.environ.get("IG_TOKEN", "")
API = "https://graph.instagram.com/v21.0"
RAW = "https://raw.githubusercontent.com/fortexglobal/fortex-uae-site/main"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def call(method, path, **params):
    params["access_token"] = T
    data = urllib.parse.urlencode(params).encode()
    url = f"{API}/{path}"
    req = urllib.request.Request(url + ("?" + data.decode() if method == "GET" else ""), None if method == "GET" else data, method=method)
    try:
        return json.load(urllib.request.urlopen(req, timeout=120))
    except urllib.error.HTTPError as e:
        return {"error": e.read().decode()[:500]}


def wait_ready(cid):
    for _ in range(30):
        st = call("GET", cid, fields="status_code").get("status_code")
        if st in ("FINISHED", None):
            return True
        if st == "ERROR":
            return False
        time.sleep(5)
    return False


def publish_stories(imgs):
    ids = []
    for u in imgs:
        c = call("POST", "me/media", image_url=u, media_type="STORIES")
        if "id" not in c:
            return {"error": c, "done": ids}
        wait_ready(c["id"])
        p = call("POST", "me/media_publish", creation_id=c["id"])
        if "id" not in p:
            return {"error": p, "done": ids}
        ids.append(p["id"])
        time.sleep(3)
    return {"id": ids[0] if ids else "", "ids": ids, "permalink": "https://www.instagram.com/stories/fortex__uae/"}


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
    p = call("POST", "me/media_publish", creation_id=c["id"])
    if "id" not in p:
        return {"error": p}
    link = call("GET", p["id"], fields="permalink").get("permalink", "")
    return {"id": p["id"], "permalink": link}


def main():
    me = call("GET", "me", fields="user_id,username,account_type,media_count")
    out = {"checked": time.strftime("%Y-%m-%dT%H:%MZ", time.gmtime()), "me": me, "published": []}
    if "error" not in me:
        for f in sorted(glob.glob(os.path.join(ROOT, "ig", "src", "*.json"))):
            slug = os.path.basename(f)[:-5]
            item = json.load(open(f, encoding="utf-8"))
            meta = os.path.join(ROOT, "ig", slug, "render.json")
            if item.get("status") != "approved" or not os.path.exists(meta):
                continue
            # publish_at (ISO с часовым поясом, напр. 2026-10-26T19:07+04:00): не раньше этого времени, по одному за запуск
            if item.get("publish_at"):
                from datetime import datetime, timezone
                if datetime.fromisoformat(item["publish_at"]) > datetime.now(timezone.utc):
                    continue
                if any(x.get("scheduled") == item.get("format", "carousel") for x in out["published"]):
                    continue
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
