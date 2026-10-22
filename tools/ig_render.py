"""Карусели Instagram в стиле бренда (тёмно-синий и золото), 1080x1350.

ig/src/<slug>.json:
{"caption": "...", "status": "wait|approved|published", "bg_prompt": "<сцена для обложки, англ.>",
 "slides": [{"type": "cover", "tag": "...", "title": "..."},
            {"type": "text", "title": "...", "body": "..."},
            {"type": "list", "title": "...", "items": ["...", ...]},
            {"type": "case", "title": "...", "stat": "3 недели", "body": "..."},
            {"type": "compare", "title": "...", "cols": [{"h": "...", "items": [...]}, {"h": "...", "items": [...]}]},
            {"type": "cta", "title": "...", "body": "..."}]}
Результат: ig/<slug>/<hash>-<n>.jpg и ig/<slug>/render.json {"hash", "files"}.
Фон обложки: ig/bg/<slug>.jpg (генерируется через OpenRouter, если есть bg_prompt и ключ).
"""
import base64, glob, hashlib, html, json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from cover import FONTS, MARK  # noqa: E402

W, H = 1080, 1350
STORY = {"on": False}
# сторис 1080x1920: сверху и снизу безопасные поля под интерфейс Instagram
STORY_CSS = """body{height:1920px}.s{height:1920px;padding:250px 88px 330px}.cover h1{font-size:112px}h2{font-size:92px}.body{font-size:52px}li{font-size:46px}.stat{font-size:170px}"""
E = html.escape

CSS = FONTS + """
*{box-sizing:border-box;margin:0;padding:0}
body{width:1080px;height:1350px;overflow:hidden;font-family:"Inter Display",sans-serif}
.s{position:relative;width:1080px;height:1350px;padding:84px 88px 80px;display:flex;flex-direction:column;overflow:hidden}
.navy{background:radial-gradient(1100px 1100px at 85% 15%,#1A2E48 0%,#0B1626 62%);color:#F6F2EA;--m1:#F3E6C4;--m2:#C9A24B;--acc:#D4B061;--mut:rgba(246,242,234,.72);--card:rgba(255,255,255,.06);--ln:rgba(212,176,97,.35)}
.cream{background:linear-gradient(160deg,#FBF8F2 0%,#F1EADC 100%);color:#0B1626;--m1:#0B1626;--m2:#B8913F;--acc:#A8822F;--mut:rgba(11,22,38,.7);--card:#FFFFFF;--ln:#E4DCCB}
.top{display:flex;align-items:center;gap:16px;font-weight:700;letter-spacing:.08em;font-size:26px;position:relative;z-index:3}
.top svg{width:46px;height:46px}
.top .pg{margin-left:auto;font-weight:600;letter-spacing:.02em;color:var(--mut)}
.wm{position:absolute;right:-50px;bottom:-60px;width:380px;opacity:.06;z-index:0}
.mid{flex:1;display:flex;flex-direction:column;justify-content:center;position:relative;z-index:2}
.num{font-weight:800;font-size:120px;line-height:1;letter-spacing:-.03em;background:linear-gradient(135deg,#E6C877,#B8913F);-webkit-background-clip:text;color:transparent;margin-bottom:26px}
.bar{width:96px;height:6px;border-radius:3px;background:linear-gradient(90deg,#D4B061,#B8913F);margin:0 0 40px}
h2{font-weight:800;font-size:86px;line-height:1.05;letter-spacing:-.025em;text-wrap:balance;margin-bottom:40px}
.body{font-weight:600;font-size:47px;line-height:1.34;color:var(--mut);text-wrap:pretty}
.body b{color:inherit;font-weight:800;color:var(--acc)}
.navy .body b{color:#E6C877}
ul{list-style:none;display:flex;flex-direction:column;gap:22px}
li{background:var(--card);border:2px solid var(--ln);border-radius:26px;padding:30px 32px 30px 84px;position:relative;font-weight:600;font-size:42px;line-height:1.28}
li:before{content:"";position:absolute;left:32px;top:44px;width:22px;height:22px;border-radius:50%;background:linear-gradient(135deg,#E6C877,#B8913F)}
.stat{display:inline-block;font-weight:800;font-size:150px;line-height:1;letter-spacing:-.04em;background:linear-gradient(135deg,#F3E6C4,#C9A24B);-webkit-background-clip:text;color:transparent;margin-bottom:34px}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:24px}
.col{background:var(--card);border:2px solid var(--ln);border-radius:28px;padding:34px 30px}
.col.hl{background:linear-gradient(160deg,#16294A,#0B1626);border-color:#C9A24B;color:#F6F2EA}
.col h3{font-weight:800;font-size:44px;margin-bottom:24px;color:var(--acc)}
.col.hl h3{color:#E6C877}
.col p{font-weight:600;font-size:37px;line-height:1.28;margin-bottom:22px}
.foot{display:flex;align-items:center;gap:14px;position:relative;z-index:3;font-weight:600;font-size:28px;color:var(--mut)}
.dots{display:flex;gap:10px}.dots i{width:12px;height:12px;border-radius:6px;background:var(--ln)}.dots i.on{width:40px;background:linear-gradient(90deg,#D4B061,#B8913F)}
.foot .sw{margin-left:auto;color:var(--acc);font-weight:700}
.cover{color:#fff;background:#0B1626;--m1:#F3E6C4;--m2:#C9A24B}
.cover .bg{position:absolute;inset:-30px;background-size:cover;background-position:center 40%;filter:blur(3px) brightness(1.1) saturate(1.05);z-index:0}
.cover:after{content:"";position:absolute;inset:0;background:linear-gradient(180deg,rgba(11,22,38,.25) 0%,rgba(11,22,38,.35) 40%,rgba(11,22,38,.92) 100%);z-index:1}
.cover .mid{justify-content:flex-end;padding-bottom:30px}
.tag{align-self:flex-start;font-weight:700;font-size:32px;padding:12px 26px;border-radius:16px;background:linear-gradient(135deg,#D4B061,#B8913F);color:#0B1626;margin-bottom:34px}
.cover h1{font-weight:800;font-size:104px;line-height:1.02;letter-spacing:-.03em;text-wrap:balance;text-shadow:0 6px 40px rgba(0,0,0,.4)}
.cover h1 em{font-style:normal;background:linear-gradient(135deg,#F3E6C4,#D4B061);-webkit-background-clip:text;color:transparent}
.cover .foot{color:rgba(255,255,255,.85)}
.cover .foot .sw{color:#E6C877}
.btn{align-self:flex-start;margin-top:50px;font-weight:800;font-size:44px;padding:30px 44px;border-radius:24px;background:linear-gradient(135deg,#E6C877,#B8913F);color:#0B1626;box-shadow:0 20px 50px rgba(201,162,75,.25)}
.chips{display:flex;flex-wrap:wrap;gap:16px;margin-bottom:40px}.chips span{padding:16px 28px;border-radius:44px;border:2px solid var(--ln);background:var(--card);font-weight:700;font-size:40px}
.save{margin-top:40px;font-weight:600;font-size:32px;color:var(--mut)}
"""


def md(t):
    """**жирный** -> <b>, переносы строк -> <br>"""
    t = E(t)
    parts = t.split("**")
    t = "".join(f"<b>{p}</b>" if i % 2 else p for i, p in enumerate(parts))
    return t.replace("\n", "<br>")


def slide_html(s, i, n, bg_url):
    kind = s.get("type", "text")
    theme = "cover" if kind == "cover" else ("navy" if kind == "cta" or i % 2 == 0 else "cream")
    if kind == "case":
        theme = "navy"
    dots = "".join(f'<i class="{"on" if k == i else ""}"></i>' for k in range(n))
    swipe = ("Дальше →" if STORY["on"] else "Листайте →") if i < n - 1 else "@fortex__uae"
    top = f'<div class="top">{MARK}<span>FORTEX UAE</span><span class="pg">{i + 1}/{n}</span></div>'
    foot = f'<div class="foot"><div class="dots">{dots}</div><span class="sw">{swipe}</span></div>'
    if kind == "cover":
        title = E(s["title"])
        if s.get("accent"):
            title = title.replace(E(s["accent"]), f"<em>{E(s['accent'])}</em>", 1)
        bg = f'<div class="bg" style="background-image:url({bg_url})"></div>' if bg_url else \
            '<div class="bg" style="background:radial-gradient(900px 900px at 70% 25%,#2A456A,#0B1626 65%)"></div>'
        mid = f'<div class="mid"><span class="tag">{E(s.get("tag", "Fortex UAE"))}</span><h1>{title}</h1></div>'
        return f'<div class="s cover">{bg}{top}{mid}{foot}</div>'
    head = f'<div class="num">{i:02d}</div>' if kind == "text" else '<div class="bar"></div>'
    if kind == "text":
        inner = f'{head}<h2>{E(s["title"])}</h2><div class="body">{md(s["body"])}</div>'
    elif kind == "list":
        lis = "".join(f"<li>{md(x)}</li>" for x in s["items"])
        inner = f'{head}<h2>{E(s["title"])}</h2><ul>{lis}</ul>'
    elif kind == "chips":
        ch = "".join(f"<span>{E(x)}</span>" for x in s["items"])
        inner = f'{head}<h2>{E(s["title"])}</h2><div class="chips">{ch}</div><div class="body">{md(s.get("body", ""))}</div>'
    elif kind == "case":
        inner = f'<div class="bar"></div><h2 style="font-size:56px;margin-bottom:24px;color:#E6C877">{E(s["title"])}</h2>' \
                f'<div class="stat">{E(s["stat"])}</div><div class="body">{md(s["body"])}</div>'
    elif kind == "compare":
        cols = "".join(f'<div class="col{" hl" if k == 1 else ""}"><h3>{E(c["h"])}</h3>' +
                       "".join(f"<p>{md(x)}</p>" for x in c["items"]) + "</div>" for k, c in enumerate(s["cols"]))
        inner = f'{head}<h2>{E(s["title"])}</h2><div class="cols">{cols}</div>'
    else:  # cta
        inner = f'<div class="bar"></div><h2 style="font-size:84px">{E(s["title"])}</h2><div class="body">{md(s.get("body", ""))}</div>' \
                f'<div class="btn">Telegram @FortexGlobal</div><div class="save">{"Или ответьте на эту сторис" if STORY["on"] else "Сохраните, чтобы не потерять"}</div>'
    return f'<div class="s {theme}"><div class="wm">{MARK}</div>{top}<div class="mid">{inner}</div>{foot}</div>'


def render_one(slug, src, browser):
    bgp = os.path.join(ROOT, "ig", "bg", slug + ".jpg")
    if src.get("new_bg"):
        if os.path.exists(bgp):
            os.remove(bgp)
        src.pop("new_bg")
        json.dump(src, open(os.path.join(ROOT, "ig", "src", slug + ".json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if not os.path.exists(bgp) and src.get("bg_prompt") and os.environ.get("OPENROUTER_API_KEY"):
        import ai_bg
        from PIL import Image
        ai_bg.KEY = os.environ["OPENROUTER_API_KEY"]
        data = ai_bg.gen(src["bg_prompt"]) or ai_bg.gen(
            "modern Dubai business district at golden hour, glass towers, calm premium mood")
        if data:
            os.makedirs(os.path.dirname(bgp), exist_ok=True)
            open(bgp, "wb").write(data)
            Image.open(bgp).convert("RGB").save(bgp, "JPEG", quality=90)
    bg_url = ("data:image/jpeg;base64," + base64.b64encode(open(bgp, "rb").read()).decode()) if os.path.exists(bgp) else ""
    h = hashlib.md5((src.get("format", "") + json.dumps(src["slides"], sort_keys=True, ensure_ascii=False) +
                     str(os.path.exists(bgp) and os.path.getsize(bgp)) + CSS[-3000:]).encode()).hexdigest()[:10]
    out_dir = os.path.join(ROOT, "ig", slug)
    meta_p = os.path.join(out_dir, "render.json")
    if os.path.exists(meta_p) and json.load(open(meta_p)).get("hash") == h:
        return False
    os.makedirs(out_dir, exist_ok=True)
    for old in glob.glob(os.path.join(out_dir, "*.jpg")):
        os.remove(old)
    files, n = [], len(src["slides"])
    story = src.get("format") == "stories"
    STORY["on"] = story
    css = CSS + (STORY_CSS if story else "")
    for i, s in enumerate(src["slides"]):
        pg = browser.new_page(viewport={"width": W, "height": 1920 if story else H})
        pg.set_content(f'<!doctype html><html><head><meta charset="utf-8"><style>{css}</style></head><body>{slide_html(s, i, n, bg_url)}</body></html>')
        pg.wait_for_timeout(250)
        f = f"{h}-{i + 1}.jpg"
        pg.screenshot(path=os.path.join(out_dir, f), type="jpeg", quality=90)
        pg.close()
        files.append(f)
    json.dump({"hash": h, "files": files}, open(meta_p, "w"), indent=1)
    print("rendered", slug, n)
    return True


def main(only=None):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        for f in sorted(glob.glob(os.path.join(ROOT, "ig", "src", "*.json"))):
            slug = os.path.basename(f)[:-5]
            if only and slug != only:
                continue
            src = json.load(open(f, encoding="utf-8"))
            if src.get("status") == "published":
                continue
            render_one(slug, src, b)
        b.close()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
