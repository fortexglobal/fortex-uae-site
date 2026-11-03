"""Ежедневный шуточный рилс Fortex (только во вкладку Reels, в сетку не попадает).
Запуск в GitHub Actions (workflow joke-reel.yml) на каждый новый reels/joke/<id>.json:
{
 "id": "2026-11-04", "publish_at": "2026-11-04T09:30:00.000Z",
 "clips": [{"stock": "dubai marina", "must": "dubai"}, ... 5 штук],
 "cards": [["строка 1", "строка 2"], ... 4 штуки], "end": ["Пишите нам", "мы поможем"], "y": 900,
 "music_q": "phonk", "caption": "подпись в стиле А или В"
}
Результат: reels/joke/out/<id>.json (+ mp4). Ключи: BUNDLE_SOCIAL_API_KEY, PIXABAY_API_KEY, PEXELS_API_KEY."""
import glob, json, os, subprocess, sys, urllib.request, urllib.parse, uuid
import numpy as np
sys.path.insert(0, "tools")
import stock_search

KEY = os.environ.get("BUNDLE_SOCIAL_API_KEY", "")
BASE = "https://api.bundle.social"
TEAM = "34938f1a-9cb5-4a85-be16-15addc7b8989"
FONTS = os.path.abspath("tools/joke/node_modules/@fontsource")
STEP, END = 2.7, 2.7
UA = {"User-Agent": "Mozilla/5.0"}


def run(a):
    subprocess.run(a, check=True)


def dl(url, path):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=300) as r, open(path, "wb") as f:
        f.write(r.read())


def call(method, path, body=None):
    h = {"x-api-key": KEY, "User-Agent": "fortex-bot/1.0", "Accept": "application/json"}
    data = None
    if body is not None:
        data = json.dumps(body).encode(); h["Content-Type"] = "application/json"
    try:
        with urllib.request.urlopen(urllib.request.Request(BASE + path, data=data, method=method, headers=h), timeout=120) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, e.read()[:1500].decode("utf-8", "ignore")


def upload(fp):
    bnd = uuid.uuid4().hex
    ct = "video/mp4" if fp.endswith(".mp4") else "image/jpeg"
    body = (f"--{bnd}\r\nContent-Disposition: form-data; name=\"teamId\"\r\n\r\n{TEAM}\r\n"
            f"--{bnd}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{os.path.basename(fp)}\"\r\nContent-Type: {ct}\r\n\r\n").encode() \
        + open(fp, "rb").read() + f"\r\n--{bnd}--\r\n".encode()
    req = urllib.request.Request(BASE + "/api/v1/upload/", data=body, method="POST",
                                 headers={"x-api-key": KEY, "Content-Type": f"multipart/form-data; boundary={bnd}", "User-Agent": "fortex-bot/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=300) as x:
            return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e:
        return e.code, e.read()[:1000].decode("utf-8", "ignore")


def best_window(audio, dur):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", audio, "-ac", "1", "-ar", "8000", "-f", "s16le", "-"], capture_output=True).stdout
    x = np.frombuffer(raw, np.int16).astype(float) / 32768
    e = np.array([np.sqrt(np.mean(x[i:i + 800] ** 2)) for i in range(0, len(x) - 800, 800)])
    w = int(dur * 10)
    if len(e) < w + 30:
        return 0.0
    best = max(range(20, min(len(e) - w, 900)), key=lambda i: e[i:i + w].mean() + 0.5 * (e[i + 3:i + w].mean() - e[i - 20:i].mean()))
    return best / 10


def build(spec_path):
    spec = json.load(open(spec_path))
    rid = spec["id"]
    od = f"reels/joke/out"
    os.makedirs(od, exist_ok=True)
    res_path = f"{od}/{rid}.json"
    if os.path.exists(res_path):
        return
    res = {"id": rid, "log": []}
    tmp = f"/tmp/joke-{rid}"
    os.makedirs(tmp, exist_ok=True)
    cards = spec["cards"]
    dur = len(cards) * STEP + END
    # 1. сток: по клипу на карточку + один на концовку
    clips = spec["clips"][: len(cards) + 1]
    seg = dur / len(clips)
    used = set()
    parts = []
    for i, c in enumerate(clips):
        found = stock_search.search(c["stock"])
        want = c.get("must", "").lower()
        pick = [r for r in found if (not want or want in (r.get("tags", "") + " " + r.get("link", "")).lower()) and r.get("id") not in used]
        pick = [r for r in pick if (r.get("dur") or 0) >= seg + 1] or pick or found
        r = pick[0]; used.add(r.get("id"))
        raw = f"{tmp}/c{i}.src.mp4"; dl(r["link"], raw)
        out = f"{tmp}/c{i}.mp4"
        run(["ffmpeg", "-y", "-v", "error", "-ss", "1", "-i", raw, "-t", f"{seg:.2f}", "-an",
             "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30,setpts=PTS-STARTPTS",
             "-c:v", "libx264", "-crf", "17", "-pix_fmt", "yuv420p", out])
        parts.append(out)
        res["log"].append(f"clip {i}: {r['site']} {r['id']} {r.get('tags', '')[:60]}")
    lst = f"{tmp}/list.txt"; open(lst, "w").write("".join(f"file '{p}'\n" for p in parts))
    base = f"{tmp}/base.mp4"
    run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c:v", "libx264", "-crf", "17", "-pix_fmt", "yuv420p", base])
    # 2. карточки с текстом
    y = spec.get("y", 900)
    rs = {"cards": [{"l1": a, "l2": b, "y": y, "out": f"{tmp}/k{i}.png"} for i, (a, b) in enumerate(cards)]}
    rs["cards"].append({"l1": spec["end"][0], "l2": spec["end"][1], "site": "fortex-uae.com", "y": 1180, "out": f"{tmp}/kend.png"})
    json.dump(rs, open(f"{tmp}/cards.json", "w"), ensure_ascii=False)
    run(["node", "tools/joke/render.js", FONTS, f"{tmp}/cards.json"])
    # 3. музыка из библиотеки Instagram (bundle.social)
    music_id, audio, from_start = None, None, False
    snd = spec.get("sound")  # {"q": "...", "match": "подстрока названия"}: оригинальный звук из залетевших рилсов
    if snd:
        code, b = call("GET", f"/api/v1/misc/instagram/audio?teamId={TEAM}&audioType=original_sound&searchQuery={urllib.parse.quote(snd['q'])}")
        items = (b or {}).get("audio", []) if isinstance(b, dict) else []
        m = snd.get("match", snd["q"]).lower()
        items = [a for a in items if m in (a.get("title") or "").lower() and a.get("download_url")
                 and (a.get("duration_in_ms") or 0) >= (len(cards) * STEP + END) * 1000]
        if snd.get("id"):
            items = [a for a in items if a["audio_id"] == snd["id"]] or items
        for a in items[:3]:
            try:
                f = f"{tmp}/a.m4a"; dl(a["download_url"], f)
                music_id, audio, from_start = a["audio_id"], f, True
                res["music"] = f"original sound: {a.get('title')} ({a['audio_id']})"
                break
            except Exception as e:
                res["log"].append(f"sound dl fail {str(e)[:80]}")
        if not audio:
            res["log"].append(f"sound not found: {snd}")
    for q in ([] if audio else [spec.get("music_q", ""), "phonk", ""]):
        path = f"/api/v1/misc/instagram/audio?teamId={TEAM}&audioType=music" + (f"&searchQuery={urllib.parse.quote(q)}" if q else "")
        code, b = call("GET", path)
        items = (b or {}).get("audio", []) if isinstance(b, dict) else []
        hist = set(json.load(open("reels/joke/music_used.json"))) if os.path.exists("reels/joke/music_used.json") else set()
        items = [a for a in items if a.get("download_url") and (a.get("duration_in_ms") or 0) > 30000 and a["audio_id"] not in hist] or items
        for a in items[:3]:
            try:
                f = f"{tmp}/a.m4a"; dl(a["download_url"], f)
                music_id, audio = a["audio_id"], f
                res["music"] = f"{a.get('title')} | {a.get('display_artist')} ({a['audio_id']})"
                break
            except Exception as e:
                res["log"].append(f"audio dl fail {str(e)[:80]}")
        if audio:
            break
    # 4. сборка
    pngs = [c["out"] for c in rs["cards"]]
    inp = ["-i", base]
    ss = 0 if from_start else (best_window(audio, dur) if audio else 0)
    if audio:
        inp += ["-ss", str(ss), "-i", audio]
    fc, last = "", "0:v"
    off = 2 if audio else 1
    for i, png in enumerate(pngs):
        st = i * STEP
        d = STEP - 0.1 if i < len(pngs) - 1 else dur - st
        inp += ["-loop", "1", "-t", f"{d:.2f}", "-i", png]
        n = i + off
        fo = f",fade=out:st={d - 0.25:.2f}:d=0.25:alpha=1" if i < len(pngs) - 1 else ""
        fc += f"[{n}:v]format=rgba,fade=in:st=0:d=0.3:alpha=1{fo},setpts=PTS-STARTPTS+{st}/TB[t{i}];"
        fc += f"[{last}][t{i}]overlay=x=0:y='if(lt(t-{st},0.35),24*(1-(t-{st})/0.35),0)':eof_action=pass[o{i}];"
        last = f"o{i}"
    maps = ["-map", f"[{last}]"]
    if audio:
        fc += f"[1:a]atrim=0:{dur},asetpts=PTS-STARTPTS,afade=t=in:d=0.3,afade=t=out:st={dur - 0.8}:d=0.8,loudnorm=I=-14:TP=-1.5[a]"
        maps += ["-map", "[a]"]
    else:
        fc = fc.rstrip(";")
    mp4 = f"{od}/{rid}.mp4"
    run(["ffmpeg", "-y", "-v", "error", *inp, "-filter_complex", fc, *maps, "-t", f"{dur:.2f}", "-c:v", "libx264", "-crf", "21",
         "-preset", "medium", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", mp4])
    cover = f"{tmp}/cover.jpg"
    run(["ffmpeg", "-y", "-v", "error", "-ss", "1.4", "-i", mp4, "-frames:v", "1", "-q:v", "2", cover])
    # 5. публикация только во вкладку Reels
    cv, v = upload(mp4)
    cc, c = upload(cover)
    res["upload"] = [cv, cc]
    if cv == 200:
        ig = {"type": "REEL", "text": spec["caption"], "uploadIds": [v["id"]], "shareToFeed": False}
        if cc == 200 and c.get("url"):
            ig["thumbnail"] = c["url"]
        if music_id:
            # оригинальный звук играет с начала, как в залетевших рилсах: ставим его самого на 100, звук ролика на 0
            ig["musicSoundInfo"] = ({"musicSoundId": music_id, "musicSoundVolume": 100, "videoOriginalSoundVolume": 1} if from_start
                                    else {"musicSoundId": music_id, "musicSoundVolume": 1, "videoOriginalSoundVolume": 100})
        code, p = call("POST", "/api/v1/post/", {"teamId": TEAM, "title": f"joke {rid}", "postDate": spec["publish_at"],
                                                 "status": "SCHEDULED", "socialAccountTypes": ["INSTAGRAM"], "data": {"INSTAGRAM": ig}})
        res["post"] = [code, p.get("id") if isinstance(p, dict) else p, p.get("status") if isinstance(p, dict) else None]
        if code == 200 and music_id:
            hist = json.load(open("reels/joke/music_used.json")) if os.path.exists("reels/joke/music_used.json") else []
            json.dump(hist + [music_id], open("reels/joke/music_used.json", "w"))
    else:
        res["post"] = [cv, str(v)[:300]]
    json.dump(res, open(res_path, "w"), ensure_ascii=False, indent=1)
    print(json.dumps(res, ensure_ascii=False))


for sp in sorted(glob.glob("reels/joke/*.json")):
    if os.path.basename(sp) in ("music_used.json",):
        continue
    try:
        build(sp)
    except Exception as e:
        rid = os.path.splitext(os.path.basename(sp))[0]
        os.makedirs("reels/joke/out", exist_ok=True)
        json.dump({"id": rid, "error": str(e)[:500]}, open(f"reels/joke/out/{rid}.json", "w"), ensure_ascii=False)
        print("fail", rid, e)
