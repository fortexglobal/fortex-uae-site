"""Скачивание медиа для монтажа (Buzzy, сток), которые не скачиваются из рабочей среды Claude.
research/fetch/<name>.json: {"items": [{"url": "...", "out": "a.mp4"}, {"stock": "dubai marina", "out": "b.mp4", "dur": 3}]}
Результат: research/fetch/<name>/<out>. Сток режется до dur секунд и кадрируется в 1080x1920."""
import glob, json, os, subprocess, sys, urllib.request
sys.path.insert(0, "tools")

UA = {"User-Agent": "Mozilla/5.0"}


def dl(url, path):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=300) as r, open(path, "wb") as f:
        f.write(r.read())


for src in glob.glob("research/fetch/*.json"):
    name = os.path.splitext(os.path.basename(src))[0]
    od = f"research/fetch/{name}"
    os.makedirs(od, exist_ok=True)
    cfg = json.load(open(src))
    log = []
    for it in cfg.get("items", []):
        out = os.path.join(od, it["out"])
        if os.path.exists(out):
            continue
        try:
            if it.get("url"):
                dl(it["url"], out)
                log.append(f"ok {out}")
            elif it.get("stock"):
                import stock_search
                res = stock_search.search(it["stock"])
                want = it.get("must", it["stock"].split()[-1]).lower()
                pick = [r for r in res if want in (r.get("tags", "") + " " + r.get("link", "")).lower()] or res
                pick = [r for r in pick if (r.get("dur") or 0) >= it.get("dur", 3) + 1] or pick
                r = pick[0]
                raw = out + ".src.mp4"
                dl(r["link"], raw)
                d = it.get("dur", 3)
                subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", str(it.get("start", 1)), "-i", raw, "-t", str(d), "-an",
                                "-vf", "scale=-2:1920,crop=1080:1920,fps=30", "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", out], check=True)
                os.remove(raw)
                log.append(f"ok {out} <- {r['site']} {r['id']} {r['tags'][:80]}")
        except Exception as e:
            log.append(f"fail {out}: {str(e)[:200]}")
    open(os.path.join(od, "log.txt"), "a").write("\n".join(log) + "\n")
    print("\n".join(log))
