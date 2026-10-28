"""Обложка рилса в стиле обложек каруселей (editorial): чистый кадр из видео без субтитров, логотип,
крупный заголовок с золотым акцентом, золотая плашка. Всё важное внутри центральной зоны 3:4,
которую Instagram показывает в сетке ленты."""
import base64, html, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cover import MARK  # noqa: E402

W, H = 1080, 1920
TOP, BOT = 240, 1680  # видимая в сетке зона 1080x1440

CSS = f"""@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=block');
*{{box-sizing:border-box;margin:0;padding:0}}
body{{width:{W}px;height:{H}px;overflow:hidden;font-family:Inter,"Inter Display",sans-serif}}
.c{{position:relative;width:{W}px;height:{H}px;overflow:hidden;color:#fff;background:#0B1626}}
.ph{{position:absolute;inset:0;background-size:cover;background-position:center}}
.c:before{{content:"";position:absolute;inset:0;z-index:1;background:linear-gradient(180deg,rgba(11,22,38,.55) 0%,rgba(11,22,38,.25) {TOP + 120}px,rgba(11,22,38,0) 760px,rgba(11,22,38,.82) 1380px,rgba(11,22,38,.96) 100%)}}
.mk{{position:absolute;left:72px;top:{TOP + 70}px;z-index:2;display:flex;align-items:center;gap:14px;font-weight:600;font-size:24px;letter-spacing:.22em;--m1:#F3E6C4;--m2:#C9A24B;text-shadow:0 2px 14px rgba(0,0,0,.3)}}
.mk svg{{width:40px;height:40px}}
.in{{position:absolute;left:72px;right:72px;bottom:{H - BOT + 92}px;z-index:2}}
h1{{font-weight:600;font-size:80px;line-height:1.06;letter-spacing:-.025em;text-wrap:balance}}
h1 b{{font-weight:700;color:#E6C877}}
.pill{{display:inline-block;margin-top:38px;background:#E6C877;color:#0B1626;font-weight:600;font-size:28px;padding:14px 26px;border-radius:40px}}
.play{{position:absolute;right:72px;top:{TOP + 64}px;z-index:2;width:56px;height:56px;border-radius:50%;border:2px solid rgba(255,255,255,.8);display:flex;align-items:center;justify-content:center}}
.play:after{{content:"";margin-left:5px;border-left:18px solid #fff;border-top:11px solid transparent;border-bottom:11px solid transparent}}
"""


def render(frame_jpg, title, accent, note, out_jpg, browser):
    t = html.escape(title or "")
    if accent and html.escape(accent) in t:
        t = t.replace(html.escape(accent), f"<b>{html.escape(accent)}</b>", 1)
    url = "data:image/jpeg;base64," + base64.b64encode(open(frame_jpg, "rb").read()).decode()
    pill = f'<div class="pill">{html.escape(note)}</div>' if note else ""
    doc = (f'<!doctype html><html><head><meta charset="utf-8"><style>{CSS}</style></head><body>'
           f'<div class="c"><div class="ph" style="background-image:url({url})"></div>'
           f'<div class="mk">{MARK}<span>FORTEX UAE</span></div>'
           f'<div class="in"><h1>{t}</h1>{pill}</div></div></body></html>')
    pg = browser.new_page(viewport={"width": W, "height": H})
    pg.set_content(doc)
    pg.wait_for_timeout(900)
    pg.screenshot(path=out_jpg, type="jpeg", quality=90)
    pg.close()


# ---------- светлый журнальный стиль ленты (ig/feed/STYLE.md, утверждён 28.10.2026) ----------
FONTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")


def _ttf(name):
    return "data:font/ttf;base64," + base64.b64encode(open(os.path.join(FONTS, name), "rb").read()).decode()


def render_light(frame_jpg, title, accent, out_jpg, browser):
    """Светлый кадр на весь экран, внизу кремовая плашка с заголовком Playfair, акцент курсивом золотом.
    Всё внутри зоны 3:4, которую Instagram показывает в сетке."""
    t = html.escape(title or "")
    if accent and html.escape(accent) in t:
        t = t.replace(html.escape(accent), f"<i>{html.escape(accent)}</i>", 1)
    url = "data:image/jpeg;base64," + base64.b64encode(open(frame_jpg, "rb").read()).decode()
    css = (f"@font-face{{font-family:PF;font-style:normal;src:url({_ttf('PlayfairDisplay_500Medium.ttf')})}}"
           f"@font-face{{font-family:PF;font-style:italic;src:url({_ttf('PlayfairDisplay_500Medium_Italic.ttf')})}}"
           f"*{{box-sizing:border-box;margin:0;padding:0}}body{{width:{W}px;height:{H}px;overflow:hidden}}"
           f".c{{position:relative;width:{W}px;height:{H}px;overflow:hidden;background:#F4EFE6}}"
           f".ph{{position:absolute;inset:0;background-size:cover;background-position:center;filter:brightness(1.06) saturate(.92)}}"
           f".b{{position:absolute;left:44px;right:44px;bottom:{H - BOT + 44}px;background:rgba(244,239,230,.95);padding:46px 50px 52px;color:#0B1626}}"
           f".k{{font:600 22px Inter,sans-serif;letter-spacing:.26em;color:#A88A4A;margin-bottom:20px}}"
           f"h1{{font:500 72px/1.12 PF,serif;letter-spacing:-.01em;text-wrap:balance}}h1 i{{color:#9C7A33}}")
    doc = (f'<!doctype html><html><head><meta charset="utf-8"><style>{css}</style></head><body><div class="c">'
           f'<div class="ph" style="background-image:url({url})"></div>'
           f'<div class="b"><div class="k">FORTEX UAE</div><h1>{t}</h1></div></div></body></html>')
    pg = browser.new_page(viewport={"width": W, "height": H})
    pg.set_content(doc)
    pg.wait_for_timeout(900)
    pg.screenshot(path=out_jpg, type="jpeg", quality=90)
    pg.close()
