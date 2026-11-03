"""Карусели и посты ленты в утверждённом стиле «Fortex · Дубай» (03.11.2026, ig/feed/STYLE.md).
python3 tools/ig_v2.py <slug>     -> ig/<slug>/<hash>-<n>.jpg + render.json, публикует tools/ig.py (status approved).
ig/src/<slug>.json:
{"style": "v2", "prerendered": true, "status": "wait", "publish_at": "2026-11-05T19:07+04:00",
 "tpl": "S1|S2|S3|S4" (обложка), "photos": ["ig/bg/<slug>-0.jpg", ...] (качественные фото, 1 на слайд),
 "slides": [
   {"type": "cover", "a": "тонкое начало", "b": "жирный конец", "sub": "подзаголовок (S3)", "box": "плашка (S1)", "photo": 0},
   {"type": "page", "pos": "top|bottom|mid|light", "a": "...", "b": "...", "body": "2-3 коротких предложения, **жирное**", "photo": 1},
   {"type": "cta", "a": "Пишите нам", "b": "мы поможем", "body": "...", "photo": 4}],
 "caption": "..."}
Размер 1080x1350 (4:5, максимум для каруселей Instagram), всё важное внутри 1012x1350 (сетка 3:4)."""
import base64, glob, hashlib, json, os, re, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
W, H = 1080, 1350
NM = os.environ.get("FONTS_DIR") or os.path.join(ROOT, "tools", "joke", "node_modules", "@fontsource")


def fonts():
    if not os.path.exists(os.path.join(NM, "manrope")):
        d = os.path.dirname(os.path.dirname(NM))
        os.makedirs(d, exist_ok=True)
        subprocess.run(["npm", "i", "-s", "--prefix", d, "@fontsource/manrope@5"], check=True, capture_output=True)
    css = ""
    for w in (300, 400, 600, 800):
        for s in ("cyrillic", "latin"):
            p = os.path.join(NM, "manrope", "files", f"manrope-{s}-{w}-normal.woff2")
            css += "@font-face{font-family:M;font-weight:%d;src:url(data:font/woff2;base64,%s) format('woff2')}" % (
                w, base64.b64encode(open(p, "rb").read()).decode())
    return css


def E(s):
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def md(s):
    s = E(s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    return "".join(f"<p>{p.strip()}</p>" for p in s.split("\n\n") if p.strip())


BASE = """*{box-sizing:border-box;margin:0}body{width:1080px;height:1350px;position:relative;overflow:hidden;font-family:M;color:#fff;background:#111}
.ph{position:absolute;inset:0;background-size:cover;background-position:center}
.wm{font-weight:800;font-size:44px;letter-spacing:-1.5px}
.up{text-transform:uppercase;letter-spacing:1px;line-height:1.25}.l{font-weight:300}.b{font-weight:800}
.gold{color:#8A6A3A}.body{font-size:34px;line-height:1.42;font-weight:400}.body p+p{margin-top:18px}.body b{font-weight:800}
.num{position:absolute;right:90px;font-size:24px;letter-spacing:3px;font-weight:600;opacity:.85}"""


def bg(u):
    return f'<div class="ph" style="background-image:url({u})"></div>'


def cover(s, tpl, u):
    a, b = E(s.get("a")), E(s.get("b"))
    if tpl == "S1":
        box = f'<div style="display:inline-block;margin-top:38px;border:1.5px solid #fff;padding:14px 28px;font-size:26px;font-weight:400">{E(s["box"])}</div>' if s.get("box") else ""
        return bg(u) + '<div class="ph" style="background:linear-gradient(180deg,rgba(0,0,0,.45),rgba(0,0,0,0) 48%)"></div>' + \
            f'<div style="position:absolute;top:80px;width:100%;text-align:center"><div class="wm">Fortex</div>' \
            f'<div class="up" style="margin:44px auto 0;width:840px;font-size:48px"><span class="l">{a}</span><br><span class="b">{b}</span></div>{box}</div>'
    if tpl == "S2":
        return bg(u) + '<div class="ph" style="background:linear-gradient(0deg,rgba(0,0,0,.72),rgba(0,0,0,0) 60%)"></div>' + \
            '<div style="position:absolute;left:90px;right:90px;bottom:100px;height:420px;border:1.5px solid rgba(255,255,255,.85)"></div>' + \
            f'<div style="position:absolute;left:130px;right:130px;bottom:165px;text-align:center"><div class="up" style="font-size:46px"><span class="l">{a}</span><br><span class="b">{b}</span></div></div>' + \
            '<div class="wm" style="position:absolute;top:70px;width:100%;text-align:center">Fortex</div>'
    if tpl == "S3":
        return '<div class="ph" style="background:#F7F4EE"></div><div class="wm" style="position:absolute;left:90px;top:64px;color:#1A1A1A">Fortex</div>' + \
            '<div style="position:absolute;left:290px;right:70px;top:94px;height:1.5px;background:#B89A63"></div>' + \
            '<div style="position:absolute;right:70px;top:94px;height:480px;width:1.5px;background:#B89A63"></div>' + \
            f'<div style="position:absolute;left:90px;right:140px;top:175px"><div class="up gold" style="font-size:60px;line-height:1.12;letter-spacing:0"><span class="b">{a}</span><br><span class="l">{b}</span></div>' + \
            f'<div style="margin-top:30px;font-size:30px;line-height:1.4;color:#333">{E(s.get("sub"))}</div></div>' + \
            f'<div class="ph" style="left:90px;right:90px;top:auto;bottom:90px;height:600px;background-image:url({u})"></div>'
    return bg(u) + '<div class="ph" style="background:linear-gradient(0deg,rgba(0,0,0,.8),rgba(0,0,0,0) 55%)"></div>' + \
        f'<div style="position:absolute;left:90px;right:90px;bottom:190px;text-align:center"><div class="up" style="font-size:48px"><span class="b">{a}</span><br><span class="l">{b}</span></div>' + \
        (f'<div style="margin-top:20px;font-size:28px;font-weight:300">{E(s["sub"])}</div>' if s.get("sub") else "") + '</div>' + \
        '<div class="wm" style="position:absolute;bottom:80px;width:100%;text-align:center;font-size:40px">Fortex</div>'


def page(s, u, i, n):
    a, b, body, pos = E(s.get("a")), E(s.get("b")), md(s.get("body", "")), s.get("pos", "bottom")
    num = f"{i:02d} / {n:02d}"
    head = f'<div class="up" style="font-size:44px"><span class="l">{a}</span><br><span class="b">{b}</span></div>'
    if pos == "light":
        return '<div class="ph" style="background:#F7F4EE"></div>' + \
            f'<div class="wm" style="position:absolute;left:90px;top:64px;color:#1A1A1A;font-size:38px">Fortex</div><div class="num" style="top:76px;color:#8A6A3A">{num}</div>' + \
            f'<div class="ph" style="left:90px;right:90px;top:150px;bottom:auto;height:560px;background-image:url({u})"></div>' + \
            f'<div style="position:absolute;left:90px;right:90px;top:760px;color:#1A1A1A"><div class="up gold" style="font-size:44px;letter-spacing:0"><span class="b">{a}</span> <span class="l">{b}</span></div>' + \
            f'<div class="body" style="margin-top:24px;color:#2A2A2A">{body}</div></div>'
    if pos == "top":
        sh, box, mark = "linear-gradient(180deg,rgba(0,0,0,.82) 0%,rgba(0,0,0,.55) 45%,rgba(0,0,0,0) 72%)", "top:150px;left:90px;right:90px", "bottom:70px"
    elif pos == "mid":
        sh, box, mark = "linear-gradient(90deg,rgba(0,0,0,.86) 0%,rgba(0,0,0,.6) 60%,rgba(0,0,0,.1) 100%)", "top:50%;transform:translateY(-50%);left:90px;right:260px", "top:70px"
    else:
        sh, box, mark = "linear-gradient(0deg,rgba(0,0,0,.86) 0%,rgba(0,0,0,.6) 45%,rgba(0,0,0,0) 72%)", "bottom:110px;left:90px;right:90px", "top:70px"
    rule = '<div style="width:70px;height:2px;background:#C9A45C;margin:26px 0"></div>'
    return bg(u) + f'<div class="ph" style="background:{sh}"></div>' + \
        f'<div class="wm" style="position:absolute;left:90px;{mark};font-size:36px">Fortex</div><div class="num" style="{mark}">{num}</div>' + \
        f'<div style="position:absolute;{box}">{head}{rule}<div class="body">{body}</div></div>'


def cta(s, u):
    return bg(u) + '<div class="ph" style="background:rgba(0,0,0,.55)"></div>' + \
        '<div style="position:absolute;left:90px;right:90px;top:250px;bottom:250px;border:1.5px solid rgba(255,255,255,.85)"></div>' + \
        f'<div style="position:absolute;left:150px;right:150px;top:50%;transform:translateY(-50%);text-align:center">' + \
        f'<div class="wm" style="font-size:40px;margin-bottom:46px">Fortex</div>' + \
        f'<div class="up" style="font-size:52px"><span class="l">{E(s.get("a", "Пишите нам"))}</span><br><span class="b">{E(s.get("b", "мы поможем"))}</span></div>' + \
        f'<div class="body" style="margin-top:34px;font-size:32px">{md(s.get("body", ""))}</div>' + \
        '<div style="margin-top:40px;font-size:30px;font-weight:600;letter-spacing:2px">TELEGRAM @FORTEX_DUBAI<br><span style="font-weight:400;opacity:.9">FORTEX-UAE.COM</span></div></div>'


def render(slug):
    src = json.load(open(os.path.join(ROOT, "ig", "src", slug + ".json"), encoding="utf-8"))
    photos = ["data:image/jpeg;base64," + base64.b64encode(open(os.path.join(ROOT, p), "rb").read()).decode() for p in src["photos"]]
    css = fonts() + BASE
    h = hashlib.md5((json.dumps(src["slides"], sort_keys=True, ensure_ascii=False) + src.get("tpl", "") +
                     str([os.path.getsize(os.path.join(ROOT, p)) for p in src["photos"]]) + BASE).encode()).hexdigest()[:10]
    od = os.path.join(ROOT, "ig", slug)
    os.makedirs(od, exist_ok=True)
    for old in glob.glob(os.path.join(od, "*.jpg")):
        os.remove(old)
    from playwright.sync_api import sync_playwright
    files, n = [], len(src["slides"])
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page(viewport={"width": W, "height": H})
        for i, s in enumerate(src["slides"]):
            u = photos[int(s.get("photo", i)) % len(photos)]
            inner = cover(s, src.get("tpl", "S1"), u) if s["type"] == "cover" else cta(s, u) if s["type"] == "cta" else page(s, u, i + 1, n)
            pg.set_content(f'<!doctype html><html><head><meta charset="utf-8"><style>{css}</style></head><body>{inner}</body></html>')
            pg.evaluate("document.fonts.ready")
            f = f"{h}-{i + 1}.jpg"
            pg.screenshot(path=os.path.join(od, f), type="jpeg", quality=92)
            files.append(f)
        b.close()
    json.dump({"hash": h, "files": files, "style": "v2"}, open(os.path.join(od, "render.json"), "w"), indent=1)
    print("ok", slug, files)


if __name__ == "__main__":
    render(sys.argv[1])
