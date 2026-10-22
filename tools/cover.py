"""Обложки в фирменном стиле Fortex UAE.

python3 tools/cover.py <slug> "<заголовок>" "<рубрика>" [light|dark|photo] [--scene crypto|bank|city|docs|chart] [--bg path.jpg]

Делает две картинки:
  static/covers/<slug>.jpg      1280x720  для сайта и превью ссылок
  static/covers/tg/<slug>.jpg   1080x1350 для поста в Telegram (крупно, на весь экран телефона)

Стиль photo: на фоне размытая картинка по теме. Источник фона по приоритету:
  --bg <файл>   (например, сгенерированная картинка по теме),
  --scene <имя> (нарисованная сцена: crypto = экран биржи со свечами, bank = банковская карта и счёт,
                 city = силуэт Дубая, docs = документы и Emirates ID, chart = графики и цифры),
  иначе кадр из видео сайта.
"""
import argparse, base64, html, os, random
from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONTS = "".join(
    f'@font-face{{font-family:"Inter Display";font-weight:{w};src:url(data:font/otf;base64,'
    + base64.b64encode(open(os.path.join(ROOT, "tools", "fonts", f"InterDisplay-{n}.otf"), "rb").read()).decode()
    + ')}' for w, n in ((600, "SemiBold"), (700, "Bold"), (800, "ExtraBold")))
MARK = '<svg viewBox="0 0 256 256"><path fill="var(--m1)" d="M52 12H228C226 44 204 68 168 68H30C30 36 38 12 52 12Z"/><path fill="var(--m2)" d="M104 90H194C192 122 172 148 136 148H88V244H30V164C30 120 62 90 104 90Z"/></svg>'


def _candles(w, h, n, seed=7):
    r = random.Random(seed); x0 = 40; step = (w - 80) / n; y = h * .55; out = []
    for i in range(n):
        o = y; y = max(h * .15, min(h * .85, y + r.uniform(-1, 1) * h * .06 + (h * .006 if i > n * .55 else -h * .001)))
        c = y; hi = min(o, c) - r.uniform(4, 30); lo = max(o, c) + r.uniform(4, 30)
        col = "#2EBD85" if c < o else "#F6465D"; x = x0 + i * step
        out.append(f'<line x1="{x+step*.35:.1f}" x2="{x+step*.35:.1f}" y1="{hi:.1f}" y2="{lo:.1f}" stroke="{col}" stroke-width="2"/>'
                   f'<rect x="{x:.1f}" y="{min(o,c):.1f}" width="{step*.7:.1f}" height="{max(3,abs(c-o)):.1f}" fill="{col}"/>')
    return "".join(out)


def scene_html(name, w, h):
    r = random.Random(3)
    if name == "crypto":
        book = "".join(f'<div style="display:flex;justify-content:space-between;color:{"#F6465D" if i<9 else "#2EBD85"}"><span>{67250+(9-i)*12.5:,.1f}</span><span style="color:#8a94a6">{r.uniform(.01,2.5):.4f}</span></div>' for i in range(18))
        return f'''<div style="position:absolute;inset:0;background:#0B0E11;font:600 22px Inter,sans-serif;color:#EAECEF">
<div style="height:70px;border-bottom:1px solid #222831;display:flex;align-items:center;gap:40px;padding:0 40px"><b style="font-size:28px;color:#F0B90B">EXCHANGE</b><span>Spot</span><span>Futures</span><span>Earn</span><span style="margin-left:auto;color:#8a94a6">Withdraw</span></div>
<div style="display:flex;height:calc(100% - 70px)"><div style="flex:1;position:relative;height:100%"><div style="position:absolute;top:20px;left:40px;font-size:30px">BTC/USDT <span style="color:#F6465D">67,184.2 −4.31%</span></div>
<svg style="position:absolute;inset:80px 0 0 0" width="100%" height="85%" viewBox="0 0 {int(w*.72)} {h-70}" preserveAspectRatio="none">{_candles(int(w*.72), h-70, 46)}</svg></div>
<div style="width:28%;padding:24px;border-left:1px solid #222831;font-size:19px;line-height:1.75">{book}</div></div></div>'''
    if name == "bank":
        return '''<div style="position:absolute;inset:0;background:linear-gradient(135deg,#1d3b52,#0E1B2C)">
<div style="position:absolute;left:12%;top:18%;width:620px;height:390px;border-radius:34px;background:linear-gradient(135deg,#C9A961,#7d6431);transform:rotate(-12deg);box-shadow:0 40px 80px rgba(0,0,0,.5)">
<div style="position:absolute;left:50px;top:120px;width:90px;height:70px;border-radius:12px;background:linear-gradient(135deg,#f3e3a8,#a8893c)"></div>
<div style="position:absolute;left:50px;bottom:60px;font:600 38px Inter;letter-spacing:.12em;color:#1b1b1b">4532 •••• •••• 7781</div></div>
<div style="position:absolute;right:8%;top:30%;width:520px;height:600px;border-radius:30px;background:#F4F7FA;transform:rotate(8deg);padding:40px;font:600 26px Inter;color:#0E1B2C">
<div style="font-size:22px;color:#6a7685">Balance</div><div style="font-size:60px;margin:10px 0 30px">AED 248,500</div>
<div style="height:14px;background:#C9A24B;border-radius:7px;width:70%;margin:18px 0"></div><div style="height:14px;background:#cfd8e0;border-radius:7px;width:90%;margin:18px 0"></div><div style="height:14px;background:#cfd8e0;border-radius:7px;width:55%;margin:18px 0"></div></div></div>'''
    if name == "city":
        bld = "".join(f'<div style="position:absolute;bottom:0;left:{x}%;width:{wd}%;height:{ht}%;background:linear-gradient(#2c4a63,#14283a);border-radius:{6 if x!=46 else 200}px {6 if x!=46 else 200}px 0 0"></div>'
                      for x, wd, ht in [(2,7,38),(10,5,52),(16,8,44),(25,6,61),(32,9,48),(42,4,70),(46,3,92),(50,4,66),(56,8,55),(65,6,47),(72,9,58),(82,7,41),(90,9,50)])
        return f'<div style="position:absolute;inset:0;background:linear-gradient(#f2b679 0%,#e07b5a 35%,#3b4f6b 70%,#14283a 100%)"><div style="position:absolute;left:62%;top:22%;width:180px;height:180px;border-radius:50%;background:#ffe2a8;opacity:.9"></div>{bld}</div>'
    if name == "docs":
        return '''<div style="position:absolute;inset:0;background:linear-gradient(135deg,#d9e4ec,#b8c7d3)">
<div style="position:absolute;left:8%;top:12%;width:560px;height:740px;background:#fff;transform:rotate(-8deg);box-shadow:0 30px 60px rgba(0,0,0,.25);padding:60px">
<div style="height:24px;background:#0E1B2C;width:60%;margin-bottom:40px"></div>''' + "".join('<div style="height:12px;background:#cfd8e0;margin:22px 0;width:%d%%"></div>' % w_ for w_ in (95, 88, 92, 70, 96, 84, 60, 90, 78)) + '''</div>
<div style="position:absolute;right:10%;top:34%;width:600px;height:380px;border-radius:28px;background:linear-gradient(135deg,#e9f3ef,#bfdcd2);transform:rotate(6deg);box-shadow:0 30px 60px rgba(0,0,0,.3);padding:40px;font:700 30px Inter;color:#0E3A33">
<div>RESIDENT IDENTITY CARD</div><div style="display:flex;gap:30px;margin-top:40px"><div style="width:170px;height:210px;border-radius:14px;background:#9fb9b0"></div>
<div style="flex:1"><div style="height:16px;background:#7fa598;margin:14px 0"></div><div style="height:16px;background:#7fa598;margin:24px 0;width:70%"></div><div style="height:16px;background:#7fa598;margin:24px 0;width:85%"></div></div></div></div></div>'''
    # chart
    bars = "".join(f'<rect x="{60+i*70}" y="{h-80-v}" width="44" height="{v}" fill="{"#C9A24B" if i%3 else "#8F6C22"}"/>' for i, v in enumerate(r.randint(80, int(h*.7)) for _ in range(int((w-120)/70))))
    return f'<div style="position:absolute;inset:0;background:#0E1B2C"><svg width="{w}" height="{h}">{bars}</svg></div>'


def page(w, h, title, topic, style, bg_url, scene, tg):
    big = tg
    fs = (92 if len(title) < 50 else 80 if len(title) < 75 else 68) if big else (64 if len(title) < 60 else 54)
    bg_layer = ""
    if style == "photo":
        inner = scene_html(scene, w, h) if (scene and not bg_url) else f'<div style="position:absolute;inset:0;background:url({bg_url}) center 35%/cover"></div>'
        bg_layer = f'<div class="bgwrap">{inner}</div>'
    real = bool(bg_url) and not scene  # настоящая картинка (нейросеть): меньше размытия и затемнения
    grad = ("180deg,rgba(14,27,44,.15) 0%,rgba(14,27,44,.25) 35%,rgba(14,27,44,.85) 100%" if real else "180deg,rgba(14,27,44,.35) 0%,rgba(14,27,44,.55) 40%,rgba(14,27,44,.92) 100%") if big else "90deg,rgba(14,27,44,.92) 0%,rgba(14,27,44,.62) 55%,rgba(14,27,44,.25) 100%"
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
{FONTS}
*{{box-sizing:border-box;margin:0}}
body{{width:{w}px;height:{h}px;overflow:hidden;font-family:"Inter Display","Inter",sans-serif}}
.c{{position:relative;width:{w}px;height:{h}px;padding:{90 if big else 72}px {80 if big else 80}px;display:flex;flex-direction:column;justify-content:space-between;overflow:hidden}}
.light{{background:linear-gradient(135deg,#EAF2F7 0%,#F6F4EE 100%);color:#0E1B2C;--m1:#0E1B2C;--m2:#B8913F}}
.dark{{background:radial-gradient({w*.8:.0f}px {h*.8:.0f}px at 85% 30%,#1b2a3a 0%,#0b1220 60%);color:#fff;--m1:#F3E6C4;--m2:#C9A24B}}
.photo{{color:#fff;--m1:#F3E6C4;--m2:#C9A24B;background:#0E1B2C}}
.bgwrap{{position:absolute;inset:-30px;filter:blur({(2 if real else 5) if big else (2 if real else 4)}px) brightness({1.25 if real else 1}) saturate(1.1);z-index:0}}
.photo::after{{content:"";position:absolute;inset:0;background:linear-gradient({grad});z-index:1}}
.c>.top,.c>div:not(.bgwrap):not(.mark),.c>.foot{{position:relative;z-index:2}}
.c>.bgwrap{{position:absolute}} .c>.mark{{position:absolute}}
.mark{{position:absolute;right:-70px;bottom:-60px;width:{620 if big else 520}px;opacity:.10;z-index:1}}
.dark .mark{{opacity:.14}} .photo .mark{{opacity:.08}}
.top{{display:flex;align-items:center;gap:18px;font-weight:700;letter-spacing:.06em;font-size:{30 if big else 24}px}}
.top svg{{width:{54 if big else 44}px;height:{54 if big else 44}px}}
.tag{{display:inline-block;font-weight:700;font-size:{30 if big else 22}px;padding:{10 if big else 8}px {22 if big else 18}px;border-radius:14px;background:linear-gradient(135deg,#D4B061,#B8913F);color:#0B1626;margin-bottom:{34 if big else 26}px}}
h1{{font-weight:800;font-size:{fs}px;line-height:1.06;letter-spacing:-.02em;max-width:{w-160}px;text-wrap:balance}}
.photo h1{{text-shadow:0 4px 30px rgba(0,0,0,.35)}}
.foot{{font-size:{30 if big else 24}px;font-weight:600;opacity:.85}}
</style></head><body><div class="c {style}">{bg_layer}
<div class="mark">{MARK}</div>
<div class="top">{MARK}<span>FORTEX UAE</span></div>
<div><span class="tag">{html.escape(topic)}</span><h1>{html.escape(title)}</h1></div>
<div class="foot">fortex-uae.com · Дубай</div></div></body></html>"""


def render(slug, title, topic, style="light", scene=None, bg=None):
    bg_url = ""
    if style == "photo":
        src = bg or (None if scene else os.path.join(ROOT, "static", "video", "bg-poster.jpg"))
        if src and os.path.exists(src):
            bg_url = "data:image/jpeg;base64," + base64.b64encode(open(src, "rb").read()).decode()
    outs = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        for w, h, tg, out in [(1280, 720, False, os.path.join(ROOT, "static", "covers", f"{slug}.jpg")),
                              (1080, 1350, True, os.path.join(ROOT, "static", "covers", "tg", f"{slug}.jpg"))]:
            os.makedirs(os.path.dirname(out), exist_ok=True)
            pg = b.new_page(viewport={"width": w, "height": h})
            pg.set_content(page(w, h, title, topic, style, bg_url, scene, tg)); pg.wait_for_timeout(300)
            pg.screenshot(path=out, type="jpeg", quality=86); pg.close(); outs.append(out)
        b.close()
    return outs


if __name__ == "__main__":
    a = argparse.ArgumentParser()
    a.add_argument("slug"); a.add_argument("title"); a.add_argument("topic")
    a.add_argument("style", nargs="?", default="light", choices=["light", "dark", "photo"])
    a.add_argument("--scene", choices=["crypto", "bank", "city", "docs", "chart"])
    a.add_argument("--bg")
    x = a.parse_args()
    for o in render(x.slug, x.title, x.topic, x.style, x.scene, x.bg):
        print(o)
