"""bundle.social: публикация рилсов с музыкой Instagram. Запуск из GitHub Actions (ключ BUNDLE_SOCIAL_API_KEY).
bundle/req.json: {"cmd": "discover"} | {"cmd": "audio", "q": [...], "type": "music|original_sound"} | {"cmd": "post", ...}
Результат: bundle/out/<cmd>.json"""
import json, os, sys, urllib.request, urllib.error

KEY = os.environ.get("BUNDLE_SOCIAL_API_KEY", "")
BASE = "https://api.bundle.social"


def call(method, path, body=None, raw=False, hdr="x-api-key"):
    h = {hdr: KEY, "User-Agent": "fortex-bot/1.0", "Accept": "application/json"}
    data = None
    if body is not None:
        data = json.dumps(body).encode(); h["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            b = r.read()
            return r.status, (b if raw else json.loads(b or b"null"))
    except urllib.error.HTTPError as e:
        return e.code, e.read()[:2000].decode("utf-8", "ignore")


os.makedirs("bundle/out", exist_ok=True)
req = json.load(open("bundle/req.json"))
cmd = req["cmd"]
out = {"cmd": cmd}
if cmd == "discover":
    for p in ["/swagger-json", "/api-json", "/swagger/json", "/api/v1/openapi.json", "/swagger.json"]:
        code, b = call("GET", p, raw=True)
        out[p] = code
        if code == 200 and b[:1] in (b"{", b"["):
            open("bundle/out/swagger.json", "wb").write(b)
            break
    for hdr in ["x-api-key", "Authorization"]:
        for p in ["/api/v1/team", "/api/v1/team/", "/api/v1/teams"]:
            code, b = call("GET", p, hdr=hdr)
            out[f"{hdr} {p}"] = [code, b if isinstance(b, str) else b]
            if code == 200:
                break
if cmd == "connect":
    out["r"] = call("POST", "/api/v1/social-account/connect", dict({"type": req.get("type", "INSTAGRAM"), "teamId": req["teamId"], "redirectUrl": "https://fortex-uae.com/"},
                    **({"instagramConnectionMethod": "FACEBOOK"} if req.get("type", "INSTAGRAM") == "INSTAGRAM" else {}),
                    **({"withBusinessScope": True} if req.get("biz") else {})))
if cmd == "accounts":
    out["r"] = call("GET", "/api/v1/team/" + req["teamId"])
if cmd == "raw":  # {"cmd":"raw","calls":[[method, path, body|null], ...]}
    out["r"] = [[m, pth, call(m, pth, b)] for m, pth, b in req["calls"]]
if cmd == "audio":  # {"cmd":"audio","q":["", "luxury"],"n":4,"type":"music"} -> список + скачанные bundle/out/audio/<id>.m4a
    import urllib.parse
    os.makedirs("bundle/out/audio", exist_ok=True)
    out["r"] = {}
    for q in req["q"]:
        path = f"/api/v1/misc/instagram/audio?teamId={req['teamId']}&audioType={req.get('type', 'music')}"
        if q:
            path += "&searchQuery=" + urllib.parse.quote(q)
        code, b = call("GET", path)
        items = (b or {}).get("audio", []) if isinstance(b, dict) else []
        out["r"][q or "_top"] = [code] + [{k: a.get(k) for k in ("audio_id", "title", "display_artist", "duration_in_ms")} for a in items]
        for a in items[:req.get("dl", 4)]:
            f = f"bundle/out/audio/{a['audio_id']}.m4a"
            if a.get("download_url") and not os.path.exists(f):
                try:
                    urllib.request.urlretrieve(a["download_url"], f)
                except Exception as e:
                    out.setdefault("dl_err", []).append(str(e)[:100])
json.dump(out, open(f"bundle/out/{cmd}.json", "w"), ensure_ascii=False, indent=1, default=str)
print(json.dumps(out, ensure_ascii=False, default=str)[:3000])
