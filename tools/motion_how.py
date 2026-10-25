"""Анимация «Как мы открываем счёт» без видеонейросетей: HTML/CSS → покадровый рендер → MP4.

python3 tools/motion_how.py            → motion/how-16x9.mp4 (сайт, YouTube) и motion/how-9x16.mp4 (Reels, Stories, реклама)
Стиль сайта: ночной синий, золото, Inter Display. Тексты только из того, что уже есть на сайте.
"""
import os, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from cover import FONTS, MARK  # noqa: E402

FPS, DUR = 30, 18.0
OUT = os.path.join(ROOT, "motion")

# сцены: (начало, конец) в секундах
SC = {"a": (0.0, 3.3), "b": (3.3, 7.6), "c": (7.6, 13.8), "d": (13.8, DUR)}


def scene_kf(name, a, b):
    """Видимость сцены: появление 0,3 с, уход 0,35 с со сдвигом вверх."""
    p = lambda t: f"{100 * t / DUR:.3f}%"
    rows = [f"0%{{opacity:0;transform:translateY(30px)}}"]
    if a > 0:
        rows.append(f"{p(a)}{{opacity:0;transform:translateY(30px)}}")
    rows.append(f"{p(a + 0.3)}{{opacity:1;transform:none}}")
    if b < DUR:
        rows.append(f"{p(b - 0.35)}{{opacity:1;transform:none;filter:blur(0)}}")
        rows.append(f"{p(b)}{{opacity:0;transform:translateY(-40px);filter:blur(8px)}}")
        rows.append("100%{opacity:0}")
    else:
        rows.append("100%{opacity:1;transform:none}")
    return f"@keyframes sc-{name}{{{''.join(rows)}}}.sc-{name}{{animation:sc-{name} {DUR}s linear both}}"


def html(vertical):
    W, H = (1080, 1920) if vertical else (1920, 1080)
    k = 1.0 if vertical else 1.1
    steps = [("01", "Бесплатный разбор", "за 5 минут"), ("02", "Подбор банка", "под вашу задачу"),
             ("03", "Подготовка подачи", "и ответы комплаенсу"), ("04", "Счёт открыт", "доступ в онлайн-банк")]
    reasons = ["Не тот банк", "Лишние документы", "Цепочка отказов"]
    step_t = [8.1, 9.3, 10.5, 11.7]
    steps_html = "".join(
        f'<div class="st" style="--d:{t}s"><div class="node"><b>{n}</b></div><div class="stx"><div class="s1">{a}</div><div class="s2">{b}</div></div></div>'
        for (n, a, b), t in zip(steps, step_t))
    reasons_html = "".join(
        f'<div class="rs" style="--d:{3.7 + i * 0.3:.1f}s;--x:{5.7 + i * 0.18:.2f}s"><span>{r}</span><i></i></div>' for i, r in enumerate(reasons))
    css = f"""{FONTS}
*{{box-sizing:border-box;margin:0;padding:0}}
html,body{{width:{W}px;height:{H}px;overflow:hidden;background:#0B1626}}
body{{font-family:"Inter Display",sans-serif;color:#F6F2EA;--m1:#F3E6C4;--m2:#C9A24B;position:relative}}
.bg{{position:absolute;inset:0;background:radial-gradient(ellipse 70% 50% at 50% {'38%' if vertical else '45%'},rgba(201,162,75,.20),rgba(201,162,75,0) 70%),linear-gradient(180deg,#0E1D33,#0B1626 60%,#08111D)}}
.grid{{position:absolute;inset:0;background-image:linear-gradient(rgba(243,230,196,.045) 1px,transparent 1px),linear-gradient(90deg,rgba(243,230,196,.045) 1px,transparent 1px);background-size:{int(90 * k)}px {int(90 * k)}px;animation:drift {DUR}s linear both}}
@keyframes drift{{from{{transform:translateY(0)}}to{{transform:translateY(-{int(90 * k)}px)}}}}
.glow{{position:absolute;width:{int(900 * k)}px;height:{int(900 * k)}px;border-radius:50%;left:50%;top:{'34%' if vertical else '50%'};margin:-{int(450 * k)}px 0 0 -{int(450 * k)}px;background:radial-gradient(circle,rgba(201,162,75,.16),rgba(201,162,75,0) 65%);animation:breath 6s ease-in-out infinite alternate both}}
@keyframes breath{{from{{transform:scale(.9)}}to{{transform:scale(1.12)}}}}
.brand{{position:absolute;left:{int(80 * k)}px;top:{int((230 if vertical else 70) * k)}px;display:flex;align-items:center;gap:{int(18 * k)}px;font-weight:800;letter-spacing:.14em;font-size:{int(30 * k)}px;color:#F3E6C4;animation:fade .6s .2s both}}
.brand svg{{width:{int(54 * k)}px;height:{int(54 * k)}px}}
.sc{{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;padding:0 {int(90 * k)}px {300 if vertical else 0}px}}
{''.join(scene_kf(n, a, b) for n, (a, b) in SC.items())}
@keyframes fade{{from{{opacity:0}}to{{opacity:1}}}}
@keyframes rise{{from{{opacity:0;transform:translateY(60px) scale(.98);filter:blur(10px)}}to{{opacity:1;transform:none;filter:blur(0)}}}}
@keyframes pop{{0%{{opacity:0;transform:scale(.6)}}70%{{opacity:1;transform:scale(1.06)}}100%{{opacity:1;transform:scale(1)}}}}
@keyframes slide{{from{{opacity:0;transform:translateX(-80px)}}to{{opacity:1;transform:none}}}}
@keyframes strike{{from{{transform:scaleX(0)}}to{{transform:scaleX(1)}}}}
@keyframes dim{{from{{opacity:1}}to{{opacity:.38}}}}
@keyframes grow{{from{{transform:scale{'Y' if vertical else 'X'}(0)}}to{{transform:scale{'Y' if vertical else 'X'}(1)}}}}
@keyframes lit{{from{{background:#13233B;box-shadow:0 0 0 rgba(201,162,75,0);color:#8F98A6}}to{{background:linear-gradient(135deg,#E6C877,#B8913F);box-shadow:0 0 {int(60 * k)}px rgba(201,162,75,.55);color:#0B1626}}}}
@keyframes pulse{{0%,100%{{transform:scale(1);box-shadow:0 0 0 0 rgba(201,162,75,.5)}}50%{{transform:scale(1.035);box-shadow:0 0 0 {int(26 * k)}px rgba(201,162,75,0)}}}}
/* сцена A */
.logo{{width:{int(150 * k)}px;height:{int(150 * k)}px;animation:pop .7s .1s both}}
.logo svg{{width:100%;height:100%}}
.h1{{font-weight:800;font-size:{int((104 if vertical else 112) * k)}px;line-height:1.04;letter-spacing:-.025em;margin-top:{int(50 * k)}px}}
.h1 .l{{display:block;animation:rise .8s var(--d) cubic-bezier(.2,.8,.2,1) both}}
.gold{{color:#D9B866}}
.sub{{margin-top:{int(40 * k)}px;font-weight:600;font-size:{int(44 * k)}px;color:#C9C2B0;animation:rise .7s 1.6s cubic-bezier(.2,.8,.2,1) both}}
/* сцена B */
.lbl{{font-weight:700;font-size:{int(34 * k)}px;letter-spacing:.16em;text-transform:uppercase;color:#D9B866;animation:rise .6s 3.4s both}}
.big{{font-weight:800;font-size:{int(84 * k)}px;line-height:1.08;letter-spacing:-.02em;margin:{int(26 * k)}px 0 {int(60 * k)}px;animation:rise .7s 3.5s both}}
.rlist{{display:flex;flex-direction:{'column' if vertical else 'row'};gap:{int(28 * k)}px}}
.rs{{position:relative;padding:{int(34 * k)}px {int(54 * k)}px;border-radius:{int(28 * k)}px;background:rgba(19,35,59,.9);border:2px solid rgba(243,230,196,.14);font-weight:700;font-size:{int(52 * k)}px;animation:slide .6s var(--d) cubic-bezier(.2,.8,.2,1) both}}
.rs span{{display:inline-block;animation:dim .4s var(--x) both}}
.rs i{{position:absolute;left:{int(40 * k)}px;right:{int(40 * k)}px;top:50%;height:{int(7 * k)}px;margin-top:-{int(3 * k)}px;border-radius:9px;background:#D9B866;transform-origin:left;animation:strike .45s var(--x) cubic-bezier(.6,0,.2,1) both}}
.fix{{margin-top:{int(60 * k)}px;font-weight:700;font-size:{int(50 * k)}px;color:#F3E6C4;animation:rise .7s 6.35s both}}
.fix b{{color:#D9B866}}
/* сцена C */
.steps{{position:relative;display:flex;flex-direction:{'column' if vertical else 'row'};gap:{int((58 if vertical else 40) * k)}px;align-items:{'flex-start' if vertical else 'flex-start'};margin-top:{int(56 * k)}px}}
.rail{{position:absolute;{'left:' + str(int(58 * k)) + 'px;top:' + str(int(60 * k)) + 'px;bottom:' + str(int(60 * k)) + 'px;width:' + str(int(6 * k)) + 'px' if vertical else 'top:' + str(int(58 * k)) + 'px;left:' + str(int(150 * k)) + 'px;right:' + str(int(150 * k)) + 'px;height:' + str(int(6 * k)) + 'px'};background:rgba(243,230,196,.12);border-radius:6px;overflow:hidden}}
.rail i{{position:absolute;inset:0;background:linear-gradient({'180deg' if vertical else '90deg'},#E6C877,#B8913F);transform-origin:{'top' if vertical else 'left'};animation:grow 3.9s 8.0s cubic-bezier(.45,0,.25,1) both}}
.st{{position:relative;display:flex;flex-direction:{'row' if vertical else 'column'};align-items:center;gap:{int(36 * k)}px;text-align:{'left' if vertical else 'center'};width:{'auto' if vertical else str(int(400 * k)) + 'px'};animation:rise .6s calc(var(--d) - .5s) both}}
.node{{flex:none;width:{int(122 * k)}px;height:{int(122 * k)}px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:800;font-size:{int(40 * k)}px;border:2px solid rgba(243,230,196,.18);animation:lit .35s var(--d) both}}
.s1{{font-weight:800;font-size:{int(54 * k)}px;line-height:1.1}}
.s2{{font-weight:600;font-size:{int(38 * k)}px;color:#C9C2B0;margin-top:{int(8 * k)}px}}
.term{{margin-top:{int(70 * k)}px;display:flex;align-items:baseline;gap:{int(24 * k)}px;justify-content:center;animation:pop .7s 12.35s both}}
.term b{{white-space:nowrap;font-weight:800;font-size:{int(120 * k)}px;color:#D9B866;letter-spacing:-.03em}}
.term span{{white-space:nowrap;font-weight:600;font-size:{int(42 * k)}px;color:#C9C2B0}}
/* сцена D */
.cta1{{font-weight:800;font-size:{int(96 * k)}px;line-height:1.05;letter-spacing:-.02em;animation:rise .8s 14.0s both}}
.cta2{{margin-top:{int(30 * k)}px;font-weight:600;font-size:{int(44 * k)}px;color:#C9C2B0;animation:rise .7s 14.4s both}}
.btn{{margin-top:{int(70 * k)}px;display:inline-block;padding:{int(40 * k)}px {int(64 * k)}px;border-radius:{int(32 * k)}px;background:linear-gradient(135deg,#E6C877,#B8913F);color:#0B1626;font-weight:800;font-size:{int(56 * k)}px;animation:pop .6s 14.9s both,pulse 1.6s 15.6s ease-in-out infinite}}
.alt{{margin-top:{int(44 * k)}px;font-weight:700;font-size:{int(40 * k)}px;color:#F3E6C4;animation:fade .6s 15.5s both}}
"""
    body = f"""<div class="bg"></div><div class="grid"></div><div class="glow"></div>
<div class="brand">{MARK}<span>FORTEX UAE</span></div>
<div class="sc sc-a"><div class="logo">{MARK}</div>
 <div class="h1"><span class="l" style="--d:.45s">Счёт в банке ОАЭ</span><span class="l" style="--d:.75s">с <span class="gold">паспортом РФ</span></span></div>
 <div class="sub">даже после отказов</div></div>
<div class="sc sc-b"><div class="lbl">Почему банки отказывают</div><div class="big">Отказ почти всегда<br>из-за подачи</div>
 <div class="rlist">{reasons_html}</div><div class="fix">Это мы <b>убираем до подачи</b></div></div>
<div class="sc sc-c"><div class="lbl" style="animation-delay:7.7s">Как мы работаем</div>
 <div class="steps"><div class="rail"><i></i></div>{steps_html}</div>
 <div class="term"><b>2–3 недели</b><span>в наших кейсах</span></div></div>
<div class="sc sc-d"><div class="cta1">Проверьте шансы<br><span class="gold">за минуту</span></div>
 <div class="cta2">6 вопросов в Telegram-боте</div>
 <div class="btn">@FortexCheck_Bot</div><div class="alt">или пишите @Fortex_Dubai</div></div>"""
    return W, H, f'<!doctype html><html><head><meta charset="utf-8"><style>{css}</style></head><body>{body}</body></html>'


def render(vertical, out_mp4, browser):
    W, H, page_html = html(vertical)
    pg = browser.new_page(viewport={"width": W, "height": H})
    pg.set_content(page_html)
    pg.wait_for_timeout(500)
    pg.evaluate("document.getAnimations().forEach(a => a.pause())")
    silent = out_mp4 + ".v.mp4"
    ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", str(FPS), "-c:v", "png", "-i", "-",
                           "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p", "-r", str(FPS), silent],
                          stdin=subprocess.PIPE)
    n = int(DUR * FPS)
    for f in range(n):
        t = f / FPS * 1000
        pg.evaluate(f"document.getAnimations().forEach(a => a.currentTime = {t})")
        ff.stdin.write(pg.screenshot(type="png"))
    ff.stdin.close(); ff.wait(); pg.close()
    add_sfx(silent, out_mp4)
    os.remove(silent)


def add_sfx(video, out):
    """Тихие эффекты на сменах сцен и шагах: без музыки, ролик можно ставить на сайт без звука."""
    sfx = os.path.join(ROOT, "ig", "sfx")
    ev = [("whoosh1", 3.15), ("whoosh2", 7.45), ("whoosh1", 13.65)] + [("click", t) for t in (8.1, 9.3, 10.5, 11.7)] + \
         [("pop", 0.15), ("pop", 12.35), ("pop", 14.9)]
    ev = [(n, t) for n, t in ev if os.path.exists(os.path.join(sfx, n + ".mp3"))]
    if not ev:
        os.replace(video, out); return
    args, fl = ["-i", video], []
    for i, (n, t) in enumerate(ev, 1):
        args += ["-i", os.path.join(sfx, n + ".mp3")]
        fl.append(f"[{i}]aresample=48000,volume={0.5 if n == 'click' else 0.35},adelay={int(t * 1000)}:all=1[s{i}]")
    mix = "".join(f"[s{i}]" for i in range(1, len(ev) + 1))
    fl.append(f"{mix}amix=inputs={len(ev)}:normalize=0,apad,atrim=0:{DUR},loudnorm=I=-18:TP=-2[a]")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error"] + args + ["-filter_complex", ";".join(fl), "-map", "0:v", "-map", "[a]",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out], check=True)


if __name__ == "__main__":
    from playwright.sync_api import sync_playwright
    os.makedirs(OUT, exist_ok=True)
    only = sys.argv[1] if len(sys.argv) > 1 else ""
    with sync_playwright() as p:
        b = p.chromium.launch()
        if only in ("", "16x9"):
            render(False, os.path.join(OUT, "how-16x9.mp4"), b)
        if only in ("", "9x16"):
            render(True, os.path.join(OUT, "how-9x16.mp4"), b)
        b.close()
    print("ok")
