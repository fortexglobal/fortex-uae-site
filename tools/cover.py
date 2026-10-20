"""Обложка для статьи и поста в Telegram: 1280x720 PNG в фирменном стиле.
python3 tools/cover.py <slug> "<заголовок>" "<рубрика>" [light|dark|photo]
Результат: static/covers/<slug>.png
"""
import base64, html, os, sys
from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MARK = '<svg viewBox="0 0 256 256"><path fill="var(--m1)" d="M52 12H228C226 44 204 68 168 68H30C30 36 38 12 52 12Z"/><path fill="var(--m2)" d="M104 90H194C192 122 172 148 136 148H88V244H30V164C30 120 62 90 104 90Z"/></svg>'


def render(slug, title, topic, style="light"):
    poster = os.path.join(ROOT, "static", "video", "bg-poster.jpg")
    bg = ""
    if style == "photo" and os.path.exists(poster):
        bg = "data:image/jpeg;base64," + base64.b64encode(open(poster, "rb").read()).decode()
    doc = f"""<!doctype html><html><head><meta charset="utf-8"><style>
*{{box-sizing:border-box;margin:0}}
body{{width:1280px;height:720px;overflow:hidden;font-family:"Inter Display","Inter",sans-serif}}
.c{{position:relative;width:1280px;height:720px;padding:72px 80px;display:flex;flex-direction:column;justify-content:space-between;overflow:hidden}}
.light{{background:linear-gradient(135deg,#EAF2F7 0%,#F6F4EE 100%);color:#0E1B2C;--m1:#0E1B2C;--m2:#0E7A82}}
.dark{{background:radial-gradient(900px 600px at 85% 30%,#123A48 0%,#0E1B2C 60%);color:#fff;--m1:#E8EEF4;--m2:#4FC3CA}}
.photo{{color:#fff;--m1:#fff;--m2:#5CC6CC;background:#0E1B2C}}
.photo .bgimg{{position:absolute;inset:-20px;background:url({bg}) center 30%/cover;filter:blur(3px) brightness(.55) saturate(.9)}}
.photo::after{{content:"";position:absolute;inset:0;background:linear-gradient(90deg,rgba(14,27,44,.92) 0%,rgba(14,27,44,.6) 55%,rgba(14,27,44,.2) 100%)}}
.c>*{{position:relative;z-index:2}}
.mark{{position:absolute;right:-70px;bottom:-60px;width:520px;opacity:.10;z-index:1}}
.dark .mark,.photo .mark{{opacity:.14}}
.top{{display:flex;align-items:center;gap:16px;font-weight:700;letter-spacing:.06em;font-size:24px}}
.top svg{{width:44px;height:44px}}
.tag{{display:inline-block;font-weight:700;font-size:22px;padding:8px 18px;border-radius:12px;background:#0E7A82;color:#fff;margin-bottom:26px}}
h1{{font-weight:800;font-size:{ '64' if len(title) < 60 else '54' }px;line-height:1.08;letter-spacing:-.02em;max-width:1000px}}
.foot{{font-size:24px;font-weight:600;opacity:.85}}
</style></head><body><div class="c {style}">{'<div class="bgimg"></div>' if style=='photo' else ''}
<div class="mark">{MARK}</div>
<div class="top">{MARK}<span>FORTEX UAE</span></div>
<div><span class="tag">{html.escape(topic)}</span><h1>{html.escape(title)}</h1></div>
<div class="foot">fortex-uae.com · Дубай</div></div></body></html>"""
    out = os.path.join(ROOT, "static", "covers", f"{slug}.png")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1280, "height": 720})
        pg.set_content(doc); pg.wait_for_timeout(300); pg.screenshot(path=out); b.close()
    return out


if __name__ == "__main__":
    print(render(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else "light"))
