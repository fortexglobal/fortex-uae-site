"""Рилсы Instagram 1080x1920, 15–20 сек: AI-фото Дубая с плавным наездом + текст на стеклянной плашке, в стиле бренда.

ig/reels/src/<slug>.json:
{"caption": "...", "status": "approved", "publish_at": "2026-10-27T19:30+04:00",
 "bg_prompts": ["<англ. сцена 1>", "<сцена 2>", "<сцена 3>"],
 "scenes": [{"type": "hook", "text": "Банк отказал?", "sub": "Вот что делать дальше"},
            {"type": "point", "title": "Не подавайтесь сами", "text": "Каждый отказ видят следующие банки"},
            ...,
            {"type": "cta", "title": "Разберём ваш случай", "text": "Telegram @Fortex_Dubai"}]}
Результат: ig/reels/<slug>/<hash>.mp4, cover.jpg, render.json {"hash","video","cover"}.
"""
import base64, glob, hashlib, html, json, os, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from cover import FONTS, MARK  # noqa: E402

W, H, FPS, SCENE = 1080, 1920, 30, 3.6
E = html.escape


def md(t):
    t = E(t or "")
    parts = t.split("**")
    return "".join(f"<b>{p}</b>" if i % 2 else p for i, p in enumerate(parts)).replace("\n", "<br>")


CSS = FONTS + """
*{margin:0;padding:0;box-sizing:border-box}
html,body{width:1080px;height:1920px;background:transparent;font-family:"Inter Display",sans-serif;color:#F6F2EA;overflow:hidden}
.top{position:absolute;left:76px;top:250px;display:flex;align-items:center;gap:16px;font-weight:700;letter-spacing:.08em;font-size:30px;--m1:#F3E6C4;--m2:#C9A24B;text-shadow:0 2px 12px rgba(0,0,0,.5)}
.top svg{width:52px;height:52px}
.wrap{position:absolute;left:64px;right:64px;top:0;bottom:0;display:flex;flex-direction:column;justify-content:center}
.card{background:rgba(11,22,38,.66);border:2px solid rgba(212,176,97,.5);border-radius:44px;padding:64px 60px;box-shadow:0 30px 80px rgba(0,0,0,.35)}
.bar{width:110px;height:7px;border-radius:4px;background:linear-gradient(90deg,#D4B061,#B8913F);margin-bottom:38px}
h1{font-weight:800;font-size:118px;line-height:1.02;letter-spacing:-.03em;text-shadow:0 8px 40px rgba(0,0,0,.55)}
h1 em,h2 em{font-style:normal;color:#E6C877}
.shade{position:absolute;inset:0;background:linear-gradient(180deg,rgba(11,22,38,.25) 0%,rgba(11,22,38,0) 25%,rgba(11,22,38,.35) 50%,rgba(11,22,38,.9) 100%)}
.sub{margin-top:34px;font-weight:700;font-size:54px;line-height:1.2;color:#F3E6C4;text-shadow:0 4px 24px rgba(0,0,0,.6)}
h2{font-weight:800;font-size:84px;line-height:1.05;letter-spacing:-.02em;margin-bottom:30px}
.txt{font-weight:600;font-size:50px;line-height:1.3;color:rgba(246,242,234,.9)}
.txt b{color:#E6C877;font-weight:800}
.btn{display:inline-block;margin-top:44px;font-weight:800;font-size:52px;padding:30px 46px;border-radius:26px;background:linear-gradient(135deg,#E6C877,#B8913F);color:#0B1626}
.hookwrap{justify-content:flex-end;padding-bottom:520px}
"""


def scene_html(sc):
    kind = sc.get("type", "point")
    top = f'<div class="top">{MARK}<span>FORTEX UAE</span></div>'
    if kind == "hook":
        t = E(sc["text"])
        if sc.get("accent"):
            t = t.replace(E(sc["accent"]), f"<em>{E(sc['accent'])}</em>", 1)
        body = '<div class="shade"></div>' + f'<div class="wrap hookwrap"><div class="bar"></div><h1>{t}</h1>' + (f'<div class="sub">{md(sc.get("sub"))}</div>' if sc.get("sub") else "") + "</div>"
    elif kind == "cta":
        body = f'<div class="wrap"><div class="card"><div class="bar"></div><h2>{E(sc["title"])}</h2><div class="txt">{md(sc.get("text", ""))}</div>' \
               f'<div class="btn">Telegram @Fortex_Dubai</div></div></div>'
    else:
        body = f'<div class="wrap"><div class="card"><div class="bar"></div><h2>{E(sc["title"])}</h2><div class="txt">{md(sc.get("text", ""))}</div></div></div>'
    return f'<!doctype html><html><head><meta charset="utf-8"><style>{CSS}</style></head><body>{top}{body}</body></html>'


def gen_bg(path, prompt):
    if os.path.exists(path) or not os.environ.get("OPENROUTER_API_KEY"):
        return
    import ai_bg
    from PIL import Image
    ai_bg.KEY = os.environ["OPENROUTER_API_KEY"]
    data = ai_bg.gen(prompt + ", vertical composition") or ai_bg.gen("Dubai skyline at golden hour, premium, calm, vertical composition")
    if data:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        open(path, "wb").write(data)
        Image.open(path).convert("RGB").save(path, "JPEG", quality=90)


def ff(args):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error"] + args, check=True)


def render_one(slug, src, browser):
    bgs = []
    for k, prompt in enumerate(src.get("bg_prompts", [])[:4]):
        pth = os.path.join(ROOT, "ig", "bg", f"reel-{slug}-{k}.jpg")
        gen_bg(pth, prompt)
        if os.path.exists(pth):
            bgs.append(pth)
    if not bgs:
        fallback = sorted(glob.glob(os.path.join(ROOT, "ig", "bg", "*.jpg")))
        bgs = fallback[:3]
    if not bgs:
        print("no backgrounds", slug)
        return False
    h = hashlib.md5((json.dumps(src["scenes"], sort_keys=True, ensure_ascii=False) + str([os.path.getsize(b) for b in bgs]) + CSS[-1500:] + "r2").encode()).hexdigest()[:10]
    out_dir = os.path.join(ROOT, "ig", "reels", slug)
    meta_p = os.path.join(out_dir, "render.json")
    if os.path.exists(meta_p) and json.load(open(meta_p)).get("hash") == h:
        return False
    os.makedirs(out_dir, exist_ok=True)
    tmp = tempfile.mkdtemp()
    parts = []
    for i, sc in enumerate(src["scenes"]):
        ov = os.path.join(tmp, f"ov{i}.png")
        pg = browser.new_page(viewport={"width": W, "height": H})
        pg.set_content(scene_html(sc)); pg.wait_for_timeout(200)
        pg.screenshot(path=ov, omit_background=True); pg.close()
        bg = bgs[i % len(bgs)]
        dur = SCENE + (0.6 if sc.get("type") in ("hook", "cta") else 0)
        frames = int(dur * FPS)
        zoom = "min(zoom+0.0009,1.14)" if i % 2 == 0 else "if(eq(on,0),1.14,max(zoom-0.0009,1.0))"
        part = os.path.join(tmp, f"p{i}.mp4")
        ff(["-loop", "1", "-i", bg, "-loop", "1", "-i", ov, "-filter_complex",
            f"[0]scale=-2:2400,crop=1350:2400,zoompan=z='{zoom}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={W}x{H}:fps={FPS},"
            f"eq=brightness=-0.06:saturation=1.05,gblur=sigma=1.2[b];[b][1]overlay=0:0,"
            f"fade=t=in:st=0:d=0.35,fade=t=out:st={dur - 0.35:.2f}:d=0.35,format=yuv420p[v]",
            "-map", "[v]", "-t", f"{dur:.2f}", "-r", str(FPS), "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", part])
        parts.append(part)
        if i == 0:
            cover = os.path.join(out_dir, "cover.jpg")
            ff(["-i", part, "-ss", "1.0", "-frames:v", "1", "-q:v", "3", cover])
    lst = os.path.join(tmp, "list.txt")
    open(lst, "w").write("".join(f"file '{p}'\n" for p in parts))
    for old in glob.glob(os.path.join(out_dir, "*.mp4")):
        os.remove(old)
    video = f"{h}.mp4"
    # тихая звуковая дорожка: Instagram надёжнее принимает видео со звуком
    ff(["-f", "concat", "-safe", "0", "-i", lst, "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
        "-shortest", "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "96k",
        "-movflags", "+faststart", os.path.join(out_dir, video)])
    json.dump({"hash": h, "video": video, "cover": "cover.jpg"}, open(meta_p, "w"), indent=1)
    print("rendered reel", slug)
    return True


def main(only=None):
    from playwright.sync_api import sync_playwright
    files = sorted(glob.glob(os.path.join(ROOT, "ig", "reels", "src", "*.json")))
    if not files:
        return
    with sync_playwright() as p:
        b = p.chromium.launch()
        for f in files:
            slug = os.path.basename(f)[:-5]
            if only and slug != only:
                continue
            src = json.load(open(f, encoding="utf-8"))
            if src.get("status") == "published":
                continue
            try:
                render_one(slug, src, b)
            except Exception as e:
                print("reel error", slug, e)
        b.close()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
