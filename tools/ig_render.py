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
STORY_CSS = """body{height:1920px}.s{height:1920px;padding:250px 76px 330px}.cover h1{font-size:118px}
h2{font-size:84px;margin-bottom:34px;line-height:1.04}.body{font-size:46px;line-height:1.38}.body b{font-weight:800}
li{font-size:42px;padding:26px 30px 26px 80px}li:before{top:40px}ul{gap:16px}.stat{font-size:160px}
.num{font-size:96px;margin-bottom:18px}.chips span{font-size:40px}.col p{font-size:36px}.col h3{font-size:46px}
.pts{display:flex;flex-direction:column;gap:26px;margin-top:6px}
.pt{display:grid;grid-template-columns:16px 1fr;gap:26px;align-items:start}
.pt i{width:16px;height:16px;border-radius:8px;margin-top:18px;background:linear-gradient(135deg,#E6C877,#B8913F)}
.pt b{display:block;font-size:46px;font-weight:800;margin-bottom:6px;line-height:1.15}
.pt span{display:block;font-size:38px;line-height:1.34;color:var(--mut);font-weight:600}
.lead{font-size:44px;line-height:1.38;color:var(--mut);font-weight:600;margin-bottom:30px}
.photo{color:#F6F2EA;background:#0B1626;--m1:#F3E6C4;--m2:#C9A24B;--acc:#E6C877;--mut:rgba(246,242,234,.86);--card:rgba(255,255,255,.08);--ln:rgba(212,176,97,.45)}
.photo .pbg{position:absolute;inset:-30px;background-size:cover;background-position:center;filter:blur(1.5px) brightness(.95) saturate(1.05);z-index:0}
.photo:after{content:"";position:absolute;inset:0;background:linear-gradient(180deg,rgba(11,22,38,.35) 0%,rgba(11,22,38,.15) 35%,rgba(11,22,38,.55) 100%);z-index:1}
.photo .card{background:rgba(11,22,38,.62);backdrop-filter:blur(18px);-webkit-backdrop-filter:blur(18px);border:2px solid rgba(212,176,97,.45);border-radius:40px;padding:60px 56px;box-shadow:0 30px 80px rgba(0,0,0,.35)}
.photo .body b,.photo h2 b{color:#E6C877}.photo li{background:rgba(255,255,255,.06)}"""
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


# ---------- редакционный стиль (светлый, журнальный) ----------
ED_CSS = """@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=block');
*{box-sizing:border-box;margin:0;padding:0}
body{width:1080px;height:1350px;overflow:hidden;font-family:Inter,"Inter Display",sans-serif}
.e{position:relative;width:1080px;height:1350px;overflow:hidden}
.ecover{color:#fff;background:#3d6f9c}
.ecover .ph{position:absolute;inset:0;background-size:cover;background-position:center}
.ecover:before{content:"";position:absolute;inset:0;background:linear-gradient(180deg,rgba(10,30,55,.32) 0%,rgba(10,30,55,.10) 34%,rgba(10,30,55,0) 55%);z-index:1}
.ecover .in{position:absolute;left:70px;right:70px;top:92px;text-align:center;z-index:2}
.wm2{font-weight:700;font-size:46px;letter-spacing:-.02em;text-shadow:0 2px 18px rgba(0,0,0,.18)}
.wm2 span{font-weight:300;opacity:.9}
.ecover h1{margin-top:74px;font-family:Inter,sans-serif;font-weight:300;font-size:50px;line-height:1.22;letter-spacing:.01em;text-transform:uppercase;text-shadow:0 2px 22px rgba(0,0,0,.22);text-wrap:balance}
.ecover h1 b{font-weight:700}
.box{display:inline-block;margin-top:44px;border:2px solid rgba(255,255,255,.92);padding:16px 28px;font-weight:400;font-size:27px;letter-spacing:.01em;text-shadow:0 1px 10px rgba(0,0,0,.2)}
.epage{background:#FAFAF7;color:#2A2A2A;padding:66px 74px}
.ehead{display:flex;justify-content:space-between;font-weight:400;font-size:25px;color:#3a3a3a;margin-bottom:30px}
.epic{width:100%;height:520px;border-radius:6px;background-size:cover;background-position:center;margin-bottom:46px}
.etext{font-weight:400;font-size:37px;line-height:1.52;color:#333}
.etext p{margin-bottom:30px}
.etext b{font-weight:600;color:#9A7433}
.eh{font-weight:700;font-size:68px;line-height:1.08;text-transform:uppercase;letter-spacing:-.01em;color:#C9A24B;margin:26px 0 8px}
.eh2{font-weight:300;font-size:58px;line-height:1.12;text-transform:uppercase;color:#2A2A2A;margin-bottom:40px}
.eline{position:absolute;right:74px;top:130px;width:2px;height:420px;background:linear-gradient(#C9A24B,rgba(201,162,75,0))}
.ebtn{display:inline-block;margin-top:20px;border:2px solid #C9A24B;color:#9A7433;font-weight:600;font-size:34px;padding:22px 34px}
.ecount{position:absolute;left:74px;bottom:54px;font-size:24px;color:#9a9a9a;font-weight:400}
.eswipe{position:absolute;right:74px;bottom:54px;font-size:24px;color:#9A7433;font-weight:600}
"""


def ed_slide(s, i, n, cover_url, photo_url):
    kind = s.get("type", "page")
    if kind == "cover":
        title = E(s["title"])
        if s.get("bold"):
            title = title.replace(E(s["bold"]), f"<b>{E(s['bold'])}</b>", 1)
        box = f'<div class="box">{E(s["note"])}</div>' if s.get("note") else ""
        return (f'<div class="e ecover"><div class="ph" style="background-image:url({cover_url})"></div>'
                f'<div class="in"><div class="wm2">fortex<span> uae</span></div><h1>{title}</h1>{box}</div></div>')
    head = f'<div class="ehead"><span>{E(s.get("head", ""))}</span><span>@fortex__uae</span></div>'
    pic = f'<div class="epic" style="background-image:url({photo_url})"></div>' if photo_url else ""
    big = ""
    if s.get("h"):
        big = f'<div class="eh">{E(s["h"])}</div>' + (f'<div class="eh2">{E(s["h2"])}</div>' if s.get("h2") else "")
    import re as _re
    nb = lambda t: _re.sub(r"(\d) (\d{3})", "\\1\u00a0\\2", _re.sub(r"(\d) (USD|AED|EUR|дн|нед|мес)", "\\1\u00a0\\2", t))
    paras = "".join(f"<p>{md(nb(x))}</p>" for x in s.get("body", "").split("\n\n") if x.strip())
    btn = '<div class="ebtn">Telegram @Fortex_Dubai</div>' if kind == "cta" else ""
    foot = f'<div class="ecount">{i + 1} / {n}</div>' + ('<div class="eswipe">Листайте →</div>' if i < n - 1 else "")
    line = '<div class="eline"></div>' if big and not pic else ""
    return f'<div class="e epage">{line}{head}{big}{pic}<div class="etext">{paras}</div>{btn}{foot}</div>'


def md(t):
    """**жирный** -> <b>, переносы строк -> <br>"""
    t = E(t)
    parts = t.split("**")
    t = "".join(f"<b>{p}</b>" if i % 2 else p for i, p in enumerate(parts))
    return t.replace("\n", "<br>")


def slide_html(s, i, n, bg_url, photo_url=""):
    kind = s.get("type", "text")
    theme = "cover" if kind == "cover" else ("navy" if kind == "cta" or i % 2 == 0 else "cream")
    if kind == "case":
        theme = "navy"
    if photo_url and kind != "cover":
        theme = "photo"
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
    head = f'<div class="num">{i:02d}</div>' if kind == "text" and not STORY["on"] else '<div class="bar"></div>'
    if kind == "text":
        inner = f'{head}<h2>{E(s["title"])}</h2><div class="body">{md(s["body"])}</div>'
    elif kind == "list":
        lis = "".join(f"<li>{md(x)}</li>" for x in s["items"])
        inner = f'{head}<h2>{E(s["title"])}</h2><ul>{lis}</ul>'
    elif kind == "points":
        pts = "".join(f'<div class="pt"><i></i><div><b>{md(x["h"])}</b><span>{md(x.get("t", ""))}</span></div></div>' for x in s["items"])
        lead = f'<div class="lead">{md(s["lead"])}</div>' if s.get("lead") else ""
        inner = f'{head}<h2>{E(s["title"])}</h2>{lead}<div class="pts">{pts}</div>'
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
                f'<div class="btn">Telegram @Fortex_Dubai</div><div class="save">{"Или ответьте на эту сторис" if STORY["on"] else "Сохраните, чтобы не потерять"}</div>'
    if theme == "photo":
        return (f'<div class="s photo"><div class="pbg" style="background-image:url({photo_url})"></div>{top}'
                f'<div class="mid"><div class="card">{inner}</div></div>{foot}</div>')
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
    # дополнительные фото для кадров сторис: src["bgs"] = [промпты], файлы ig/bg/<slug>-<k>.jpg
    photos = []
    for k, prompt in enumerate(src.get("bgs", []) or src.get("photos", [])):
        pp = os.path.join(ROOT, "ig", "bg", f"{slug}-{k}.jpg")
        if not os.path.exists(pp) and os.environ.get("OPENROUTER_API_KEY"):
            import ai_bg
            from PIL import Image
            ai_bg.KEY = os.environ["OPENROUTER_API_KEY"]
            data = ai_bg.gen(prompt)
            if data:
                os.makedirs(os.path.dirname(pp), exist_ok=True)
                open(pp, "wb").write(data)
                Image.open(pp).convert("RGB").save(pp, "JPEG", quality=88)
        if os.path.exists(pp):
            photos.append(pp)
    photo_urls = ["data:image/jpeg;base64," + base64.b64encode(open(x, "rb").read()).decode() for x in photos]
    h = hashlib.md5((src.get("format", "") + json.dumps(src["slides"], sort_keys=True, ensure_ascii=False) +
                     str(os.path.exists(bgp) and os.path.getsize(bgp)) + str([os.path.getsize(x) for x in photos]) + CSS[-3000:] + STORY_CSS + ED_CSS + src.get("style", "") + "v3").encode()).hexdigest()[:10]
    out_dir = os.path.join(ROOT, "ig", slug)
    meta_p = os.path.join(out_dir, "render.json")
    if os.path.exists(meta_p) and json.load(open(meta_p)).get("hash") == h:
        return False
    os.makedirs(out_dir, exist_ok=True)
    for old in glob.glob(os.path.join(out_dir, "*.jpg")):
        os.remove(old)
    files, n = [], len(src["slides"])
    if src.get("style") == "editorial":
        for i, sl in enumerate(src["slides"]):
            pu = ""
            if sl.get("photo") is not None and photo_urls:
                pu = photo_urls[int(sl["photo"]) % len(photo_urls)]
            pg = browser.new_page(viewport={"width": W, "height": H})
            pg.set_content(f'<!doctype html><html><head><meta charset="utf-8"><style>{ED_CSS}{FONTS}</style></head><body>{ed_slide(sl, i, n, bg_url, pu)}</body></html>')
            try:
                pg.wait_for_load_state("networkidle", timeout=8000)
            except Exception:
                pass
            pg.wait_for_timeout(400)
            f = f"{h}-{i + 1}.jpg"
            pg.screenshot(path=os.path.join(out_dir, f), type="jpeg", quality=92)
            pg.close()
            files.append(f)
        json.dump({"hash": h, "files": files}, open(meta_p, "w"), indent=1)
        print("rendered editorial", slug, n)
        return True
    story = src.get("format") == "stories"
    STORY["on"] = story
    css = CSS + (STORY_CSS if story else "")
    for i, s in enumerate(src["slides"]):
        # фото на каждом втором кадре (кроме обложки и последнего), по кругу
        photo_url = photo_urls[(i // 2) % len(photo_urls)] if (story and photo_urls and i % 2 == 1 and i < n - 1) else ""
        pg = browser.new_page(viewport={"width": W, "height": 1920 if story else H})
        pg.set_content(f'<!doctype html><html><head><meta charset="utf-8"><style>{css}</style></head><body>{slide_html(s, i, n, bg_url, photo_url)}</body></html>')
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
