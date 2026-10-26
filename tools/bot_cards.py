"""Картинки для бота-проверки @FortexCheck_Bot в стиле сайта (ночной синий, золото, Inter Display).

python3 tools/bot_cards.py
→ static/bot/welcome.jpg  (1280×720, приветствие после /start; сайт отдаёт /bot/welcome.jpg)
→ static/bot/intro.jpg    (640×360, картинка описания бота до /start; ставится вручную в @BotFather)
"""
import os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from cover import FONTS, MARK  # noqa: E402

OUT = os.path.join(ROOT, "static", "bot")


def page(W, H):
    k = W / 1280
    chips = ["Шансы по вашему случаю", "Что подготовить для банка", "Бесплатный разбор"]
    chips_html = "".join(f'<span class="chip"><i></i>{c}</span>' for c in chips)
    css = f"""{FONTS}
*{{box-sizing:border-box;margin:0;padding:0}}
html,body{{width:{W}px;height:{H}px;overflow:hidden;background:#0B1626}}
body{{font-family:"Inter Display",sans-serif;color:#F6F2EA;--m1:#F3E6C4;--m2:#C9A24B;position:relative}}
.bg{{position:absolute;inset:0;background:radial-gradient(ellipse 60% 70% at 78% 40%,rgba(201,162,75,.24),rgba(201,162,75,0) 70%),linear-gradient(160deg,#10213A,#0B1626 55%,#08111D)}}
.grid{{position:absolute;inset:0;background-image:linear-gradient(rgba(243,230,196,.05) 1px,transparent 1px),linear-gradient(90deg,rgba(243,230,196,.05) 1px,transparent 1px);background-size:{int(64 * k)}px {int(64 * k)}px}}
.brand{{position:absolute;left:{int(72 * k)}px;top:{int(56 * k)}px;display:flex;align-items:center;gap:{int(14 * k)}px;font-weight:800;letter-spacing:.14em;font-size:{int(22 * k)}px;color:#F3E6C4}}
.brand svg{{width:{int(30 * k)}px;height:{int(30 * k)}px}}
.big{{position:absolute;right:{int(70 * k)}px;top:50%;transform:translateY(-50%);width:{int(330 * k)}px;height:{int(330 * k)}px;opacity:.95}}
.big svg{{width:100%;height:100%;filter:drop-shadow(0 {int(20 * k)}px {int(60 * k)}px rgba(201,162,75,.35))}}
.tx{{position:absolute;left:{int(72 * k)}px;top:{int(150 * k)}px;width:{int(780 * k)}px}}
.lbl{{font-weight:700;font-size:{int(20 * k)}px;letter-spacing:.18em;text-transform:uppercase;color:#D9B866}}
h1{{margin-top:{int(18 * k)}px;font-weight:800;font-size:{int(74 * k)}px;line-height:1.02;letter-spacing:-.02em}}
h1 .g{{background:linear-gradient(135deg,#F3E6C4,#C9A24B);-webkit-background-clip:text;background-clip:text;color:transparent}}
.sub{{margin-top:{int(22 * k)}px;font-weight:600;font-size:{int(30 * k)}px;color:#C9C2B0}}
.sub b{{color:#F3E6C4}}
.chips{{position:absolute;left:{int(72 * k)}px;bottom:{int(64 * k)}px;display:flex;gap:{int(14 * k)}px;flex-wrap:wrap;width:{int(1150 * k)}px}}
.chip{{display:inline-flex;align-items:center;gap:{int(10 * k)}px;padding:{int(12 * k)}px {int(20 * k)}px;border-radius:999px;border:1px solid rgba(217,184,102,.45);background:rgba(243,230,196,.06);font-weight:600;font-size:{int(20 * k)}px;color:#F3E6C4}}
.chip i{{width:{int(8 * k)}px;height:{int(8 * k)}px;border-radius:50%;background:#D9B866}}
"""
    body = f"""<div class="bg"></div><div class="grid"></div>
<div class="brand">{MARK}<span>FORTEX UAE</span></div>
<div class="big">{MARK}</div>
<div class="tx"><div class="lbl">Проверка за 1 минуту</div>
<h1>Откроют ли вам счёт<br>в <span class="g">банке ОАЭ?</span></h1>
<div class="sub"><b>6 вопросов</b> кнопками · для паспорта РФ</div></div>
<div class="chips">{chips_html}</div>"""
    return f'<!doctype html><html><head><meta charset="utf-8"><style>{css}</style></head><body>{body}</body></html>'


def main():
    from playwright.sync_api import sync_playwright
    os.makedirs(OUT, exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch()
        for name, (W, H) in {"welcome": (1280, 720), "intro": (640, 360)}.items():
            pg = b.new_page(viewport={"width": W, "height": H}, device_scale_factor=1)
            pg.set_content(page(W, H))
            pg.wait_for_timeout(600)
            pg.screenshot(path=os.path.join(OUT, f"{name}.jpg"), type="jpeg", quality=90)
            print("ok", name)
        b.close()


if __name__ == "__main__":
    main()
