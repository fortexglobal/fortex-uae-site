import base64, os, sys, html
sys.path.insert(0, "/home/claude/fortex-uae-site/tools")
from cover import MARK
from playwright.sync_api import sync_playwright
R = "/home/claude/fortex-uae-site/"
G = os.path.dirname(os.path.abspath(__file__))
FD = G + "/node_modules/@fontsource/playfair-display/files/"
def b64(p, mime="image/jpeg"):
    return f"data:{mime};base64," + base64.b64encode(open(p, "rb").read()).decode()
ff = ""
for w in (400, 600, 700):
    for sub in ("latin", "cyrillic"):
        for st in ("normal", "italic"):
            f = FD + f"playfair-display-{sub}-{w}-{st}.woff2"
            if os.path.exists(f):
                ff += f"@font-face{{font-family:PF;font-weight:{w};font-style:{st};src:url({b64(f,'font/woff2')})}}"
# (тип, заголовок, акцент, плашка, фото)
P = [
 ("r", "Дубай: новые лимиты скорости с 1 ноября", "лимиты скорости", "Список дорог в описании", "ig/bg/st-kompanii-2.jpg"),
 ("c", "Счёт в банке ОАЭ с паспортом РФ в 2026", "паспортом РФ", "Личные и корпоративные", "ig/bg/ig-schet-pasport-rf.jpg"),
 ("b", "Банк отказал? Не подавайтесь в следующий", "Банк отказал?", "Разберём ваш случай", "ig/heroes/man.jpg"),
 ("c", "Mainland или фризона: что выбрать бизнесу", "фризона", "Сравнение на 6 слайдах", "ig/bg/st-kompanii-0.jpg"),
 ("r", "5 новых прямых рейсов из России в ОАЭ", "5 новых", "Новости Дубая", "ig/bg/ig-rabochaya-viza-skywards-2.jpg"),
 ("r", "Сколько стоит жизнь в Дубае в 2026", "Сколько стоит", "Аренда, школы, еда", "ig/bg/ig-rabochaya-viza-skywards.jpg"),
 ("c", "Рабочая виза и карта Emirates NBD: один комплекс", "один комплекс", "Emirates ID и зарплатный счёт", "ig/bg/st-vizy.jpg"),
 ("b", "Счёт для бизнеса: 3 ошибки при подаче", "3 ошибки", "Разберём ваш случай", "ig/heroes/woman.jpg"),
 ("c", "Счёт для крипто-компании после отказов", "после отказов", "Корпоративный и crypto account", "ig/bg/ig-schet-kripto-kompanii.jpg"),
 ("r", "Бесплатные пляжи Дубая: топ-5", "топ-5", "Сохраняй на выходные", "ig/bg/ig-e-invoicing-2027.jpg"),
 ("r", "Dubai Fitness Challenge: 30 дней бесплатно", "бесплатно", "С 1 ноября", "ig/bg/st-vopros-1.jpg" if os.path.exists(R+"ig/bg/st-vopros-1.jpg") else "ig/bg/st-voprosy-1.jpg"),
 ("c", "Электронные счета в ОАЭ с 2027 года", "с 2027 года", "Решение Минфина ОАЭ", "ig/bg/st-scheta.jpg"),
]
IMG = {p[4]: b64(R + p[4]) for p in P}
def T(t, a, cls="g"):
    t = html.escape(t); a = html.escape(a)
    return t.replace(a, f'<b class="{cls}">{a}</b>', 1)
BASE = ff + """*{box-sizing:border-box;margin:0;padding:0}body{width:1290px;background:#fff;font-family:Inter,sans-serif;color:#111}
.hd{padding:40px 40px 24px}.top{display:flex;align-items:center;gap:34px}.av{width:150px;height:150px;border-radius:50%;background:#0B1626;display:flex;align-items:center;justify-content:center;--m1:#F3E6C4;--m2:#C9A24B}.av svg{width:78px}
.un{font-size:38px;font-weight:600}.nm{font-size:28px;font-weight:600;margin-top:22px}.bio{font-size:27px;line-height:1.38;margin-top:6px}.bio a{color:#00376B}
.btn{display:flex;gap:12px;margin-top:22px}.btn div{flex:1;background:#EFEFEF;border-radius:14px;text-align:center;font-size:26px;font-weight:600;padding:16px}
.hl{display:flex;gap:30px;margin-top:30px}.hl div{text-align:center;font-size:21px}.hl img{width:116px;height:116px;border-radius:50%;border:2px solid #ddd;padding:4px;display:block;margin-bottom:8px}
.tabs{display:flex;border-top:1px solid #ddd;margin-top:24px}.tabs div{flex:1;text-align:center;padding:18px;font-size:22px;color:#999}.tabs div:first-child{color:#111;border-top:2px solid #111;margin-top:-1px}
.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:3px}
.t{position:relative;aspect-ratio:3/4;overflow:hidden;background:#0B1626}.ph{position:absolute;inset:0;background-size:cover;background-position:center}
.ic{position:absolute;right:14px;top:14px;z-index:3;width:30px;height:30px}
.lbl{position:absolute;left:0;right:0;top:-46px;text-align:center;font:600 22px Inter;color:#888}
"""
ICR = '<svg class="ic" viewBox="0 0 24 24"><path fill="#fff" d="M8 5v14l11-7z"/></svg>'
ICC = '<svg class="ic" viewBox="0 0 24 24"><rect x="7" y="3" width="13" height="13" rx="2" fill="none" stroke="#fff" stroke-width="2"/><rect x="3" y="7" width="13" height="13" rx="2" fill="#fff" fill-opacity=".85"/></svg>'

V = {}
# A: единый фирменный (как сейчас, всё одинаково)
V["A"] = ("Единый фирменный стиль", """.t:before{content:"";position:absolute;inset:0;z-index:1;background:linear-gradient(180deg,rgba(11,22,38,.45),rgba(11,22,38,0) 30%,rgba(11,22,38,.15) 50%,rgba(11,22,38,.92) 100%)}
.mk{position:absolute;left:22px;top:20px;z-index:2;display:flex;gap:8px;align-items:center;font:600 13px Inter;letter-spacing:.2em;color:#fff;--m1:#F3E6C4;--m2:#C9A24B}.mk svg{width:20px}
.in{position:absolute;left:22px;right:22px;bottom:26px;z-index:2;color:#fff}.in h1{font:600 31px/1.1 Inter;letter-spacing:-.02em}.g{color:#E6C877}
.pill{display:inline-block;margin-top:14px;background:#E6C877;color:#0B1626;font:600 14px Inter;padding:7px 13px;border-radius:20px}""",
 lambda p: f'<div class="ph" style="background-image:url({IMG[p[4]]})"></div><div class="mk">{MARK}<span>FORTEX UAE</span></div><div class="in"><h1>{T(p[1],p[2])}</h1><div class="pill">{html.escape(p[3])}</div></div>')
# B: шахматка: рилсы фото, карусели фирменный тёмно-синий с золотым шрифтом
def b_tile(p):
    if p[0] == "c":
        return (f'<div class="nv"><div class="mk2">{MARK}</div><h2>{T(p[1],p[2],"gi")}</h2><div class="ln"></div>'
                f'<div class="nt">{html.escape(p[3])}</div><div class="sw">Листайте →</div></div>')
    return f'<div class="ph" style="background-image:url({IMG[p[4]]})"></div><div class="sh"></div><div class="rt"><h1>{T(p[1],p[2])}</h1></div>'
V["B"] = ("Шахматка: фото и фирменный синий", """.nv{position:absolute;inset:0;background:radial-gradient(120% 80% at 50% 0%,#16294A,#0B1626 70%);color:#F3E6C4;padding:44px 34px;display:flex;flex-direction:column;justify-content:center;text-align:center;--m1:#F3E6C4;--m2:#C9A24B}
.mk2{position:absolute;left:50%;top:34px;transform:translateX(-50%)}.mk2 svg{width:30px}
.nv h2{font:600 40px/1.12 PF;color:#fff}.gi{font-style:italic;color:#E6C877;font-weight:600}.ln{width:60px;height:2px;background:#C9A24B;margin:24px auto 16px}.nt{font:500 16px Inter;color:#C9B98F}.sw{position:absolute;bottom:26px;left:0;right:0;font:500 14px Inter;color:#8a8f9c;letter-spacing:.08em}
.sh{position:absolute;inset:0;z-index:1;background:linear-gradient(180deg,rgba(0,0,0,0) 40%,rgba(0,0,0,.65))}
.rt{position:absolute;left:22px;right:22px;bottom:30px;z-index:2;color:#fff}.rt h1{font:800 34px/1.05 Inter;letter-spacing:-.02em;text-shadow:0 2px 16px rgba(0,0,0,.4)}.g{color:#E6C877}""", b_tile)
# C: светлый журнальный
def c_tile(p):
    if p[0] == "c":
        return (f'<div class="cr"><div class="kk">FORTEX UAE · ГАЙД</div><h2>{T(p[1],p[2],"it")}</h2>'
                f'<div class="ip" style="background-image:url({IMG[p[4]]})"></div></div>')
    return (f'<div class="ph lt" style="background-image:url({IMG[p[4]]})"></div>'
            f'<div class="band"><h3>{T(p[1],p[2],"it")}</h3></div>')
V["C"] = ("Светлый журнальный", """.t{background:#F4EFE6}.cr{position:absolute;inset:0;background:#F4EFE6;padding:30px 26px;color:#0B1626}
.kk{font:600 12px Inter;letter-spacing:.24em;color:#A88A4A}.cr h2{font:500 35px/1.1 PF;margin-top:14px}.it{font-style:italic;color:#9C7A33;font-weight:500}
.ip{position:absolute;left:26px;right:26px;bottom:26px;height:46%;background-size:cover;background-position:center;border-radius:4px;filter:brightness(1.12) saturate(.85)}
.lt{filter:brightness(1.1) saturate(.9)}.band{position:absolute;left:14px;right:14px;bottom:14px;z-index:2;background:rgba(244,239,230,.94);padding:18px 18px 20px;color:#0B1626}.band h3{font:500 25px/1.15 PF}""", c_tile)

def page(k):
    name, css, tile = V[k]
    hl = "".join(f'<div><img src="{b64(R+"ig/highlights/"+f, "image/png")}">{n}</div>' for f, n in
                 [("1-scheta.png","Счета"),("2-vizy.png","Визы"),("3-kompanii.png","Компании"),("4-keisy.png","Кейсы"),("5-kak-rabotaem.png","Как работаем"),("6-voprosy.png","Вопросы")])
    tiles = "".join(f'<div class="t">{tile(p)}{ICR if p[0]!="c" else ICC}</div>' for p in P)
    return (f'<!doctype html><html><head><meta charset="utf-8"><style>{BASE}{css}</style></head><body>'
            f'<div class="hd"><div class="top"><div class="av">{MARK}</div><div><div class="un">fortex__uae</div></div></div>'
            f'<div class="nm">Fortex UAE · Дубай</div><div class="bio">Счета в банках ОАЭ, визы и компании для русскоязычных<br>🎁 Бесплатная консультация 👇<br><a>fortex-uae.com/c/ig</a></div>'
            f'<div class="btn"><div>Подписаться</div><div>Написать</div></div><div class="hl">{hl}</div>'
            f'<div class="tabs"><div>▦</div><div>▶</div><div>☐</div></div></div><div class="grid">{tiles}</div></body></html>')

with sync_playwright() as pw:
    b = pw.chromium.launch()
    for k in V:
        pg = b.new_page(viewport={"width": 1290, "height": 1000})
        pg.set_content(page(k)); pg.wait_for_timeout(1200)
        pg.screenshot(path=f"{G}/feed-{k}.jpg", type="jpeg", quality=88, full_page=True); pg.close()
    b.close()
print("ok")
