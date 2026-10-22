"""Instagram: проверка токена и публикация каруселей/постов из ig/queue/*.json (в GitHub Actions).
Файл очереди: {"caption": "...", "images": ["https://fortex-uae.com/ig/<slug>/1.jpg", ...], "status": "approved"}
После публикации: status=published, permalink. Токен: секрет IG_TOKEN."""
import glob, json, os, sys, time, urllib.parse, urllib.request

T = os.environ.get("IG_TOKEN", "")
API = "https://graph.instagram.com/v21.0"
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


def publish(item):
    imgs = item["images"]
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
        for f in sorted(glob.glob(os.path.join(ROOT, "ig", "queue", "*.json"))):
            item = json.load(open(f, encoding="utf-8"))
            if item.get("status") != "approved":
                continue
            res = publish(item)
            item.update(status="published" if "id" in res else "error", result=res,
                        published_at=time.strftime("%Y-%m-%dT%H:%MZ", time.gmtime()))
            json.dump(item, open(f, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            out["published"].append({"file": os.path.basename(f), **res})
    json.dump(out, open(os.path.join(ROOT, "ig", "status.json"), "w"), ensure_ascii=False, indent=1)
    print(json.dumps(out, ensure_ascii=False)[:800])


if __name__ == "__main__":
    main()
