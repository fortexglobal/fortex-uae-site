"""Макет редизайна сайта (финтех-стиль) по скрытой ссылке /v/redesign-fx7/.

Берёт уже собранные страницы public/ (python3 build.py), меняет шапку и подвал на новые,
подключает новый слой стилей и собирает главную из блоков tools/redesign/home_src.html
плюс оригинальных разделов. Основной сайт не трогает.

python3 build.py && python3 tools/redesign/mock.py
"""
import os, re, glob, html

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PUB = os.path.join(ROOT, "public")
B = "/v/redesign-fx7"
OUT = os.path.join(ROOT, "static", B.strip("/"))
HERE = os.path.dirname(os.path.abspath(__file__))

ARTICLES = []  # (url, tag, title)


def collect_articles():
    s = open(os.path.join(PUB, "articles", "index.html"), encoding="utf-8").read()
    for href, tag, title in re.findall(r'<a class="card art" href="([^"]+)">\s*<span class="tag">([^<]+)</span>\s*<h3>([^<]+)</h3>', s):
        ARTICLES.append((href, tag, title))


def header():
    arts = "".join(f'<a href="{B}{u}"><b>{html.escape(t)}</b><span>{g}</span></a>' for u, g, t in ARTICLES[:5])
    svc = [
        ("/schet-v-banke-oae/", "Счёт в банке ОАЭ", "Корпоративный и личный, в том числе после отказов"),
        ("/rezidentstvo-oae/", "Резидентство и ВНЖ", "Рабочая виза и Emirates ID за 5–7 дней, Virtual Work"),
        ("/kompaniya-v-dubae/", "Компания в Дубае", "Фризона или mainland, сразу с визой и счётом"),
        ("/schet-v-banke-oae/#hard", "Сложные случаи", "Отказы, закрытия счетов, крипта и трейдинг"),
        ("/#directions", "Платежи и ВЭД", "Юани, расчёты с Китаем и Гонконгом"),
    ]
    svcs = "".join(f'<a href="{B}{u}"><b>{t}</b><span>{d}</span></a>' for u, t, d in svc)
    contacts = ('<a href="https://t.me/Fortex_Dubai"><b>Telegram @Fortex_Dubai</b><span>Ответим в течение часа</span></a>'
                '<a href="/c/call"><b>Записаться на звонок</b><span>Zoom или Telegram</span></a>'
                '<a href="https://wa.me/971558194123"><b>WhatsApp +971 55 819 4123</b><span>Удобнее всего писать в Telegram</span></a>'
                '<a href="mailto:alexey@fortex-uae.com"><b>alexey@fortex-uae.com</b><span>Пн–сб, 10:00–20:00 по Дубаю</span></a>')
    dd = lambda name, items, wide="": (f'<div class="nx-dd{wide}"><button type="button" aria-expanded="false">{name}<svg width="10" height="10" viewBox="0 0 10 10"><path d="M1 3l4 4 4-4" fill="none" stroke="currentColor" stroke-width="1.6"/></svg></button>'
                                       f'<div class="nx-menu">{items}</div></div>')
    mob = (f'<details open><summary>Услуги</summary>{svcs}</details>'
           f'<a class="nx-mlink" href="{B}/#cases">Кейсы</a>'
           f'<details><summary>Статьи</summary>{arts}<a href="{B}/articles/"><b>Все статьи →</b></a></details>'
           f'<details><summary>Контакты</summary>{contacts}</details>'
           f'<a class="nx-cta nx-mcta" href="/c/site">Бесплатная консультация</a>')
    return f'''<header class="nx-hdr nx-ondark" id="nxh">
  <a class="nx-logo" href="{B}/"><img src="/img/mark.png" alt="" width="30" height="30"><span>FORTEX</span><span class="nx-uae"><em>UAE</em></span></a>
  <nav class="nx-nav" aria-label="Меню">
    {dd("Услуги", svcs, " nx-wide")}
    <a href="{B}/#cases">Кейсы</a>
    {dd("Статьи", arts + f'<a class="nx-all" href="{B}/articles/"><b>Все статьи →</b></a>')}
    {dd("Контакты", contacts)}
  </nav>
  <a class="nx-cta" href="/c/site"><i></i><span>Бесплатная консультация</span></a>
  <button class="nx-burger" type="button" aria-label="Меню" aria-expanded="false"><i></i><i></i><i></i></button>
</header>
<div class="nx-mob" id="nxmob" hidden>{mob}</div>
<a class="nx-float" id="nxfloat" href="/c/site" aria-label="Бесплатная консультация"><svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M21.9 4.3 18.7 19.4c-.2 1-.9 1.3-1.7.8l-4.8-3.5-2.3 2.2c-.3.3-.5.5-1 .5l.3-4.9 8.9-8c.4-.3-.1-.5-.6-.2L6.5 13.2 1.8 11.7c-1-.3-1-1 .2-1.5L20.6 3c.9-.3 1.6.2 1.3 1.3z"/></svg><span>Бесплатная консультация</span></a>
'''


NX_JS = r'''<script>
(()=>{const h=document.getElementById('nxh'),mob=document.getElementById('nxmob'),bg=h.querySelector('.nx-burger'),fl=document.getElementById('nxfloat');
const dark=()=>{const y=40;let d=false;document.querySelectorAll('.nx-dark').forEach(e=>{const r=e.getBoundingClientRect();if(r.top<=y&&r.bottom>=y)d=true});h.classList.toggle('nx-ondark',d);
 fl.classList.toggle('nx-show',scrollY>500&&!document.querySelector('.nx-final')?.matches(':hover'));
 const f=document.querySelector('.nx-final,.foot');if(f){const r=f.getBoundingClientRect();if(r.top<innerHeight-80)fl.classList.remove('nx-show')}};
addEventListener('scroll',dark,{passive:true});addEventListener('resize',dark);dark();
h.querySelectorAll('.nx-dd>button').forEach(b=>b.addEventListener('click',e=>{const p=b.parentElement,o=p.classList.toggle('open');b.setAttribute('aria-expanded',o);h.querySelectorAll('.nx-dd').forEach(x=>{if(x!==p){x.classList.remove('open');x.firstElementChild.setAttribute('aria-expanded','false')}});e.stopPropagation()}));
document.addEventListener('click',()=>h.querySelectorAll('.nx-dd').forEach(x=>x.classList.remove('open')));
bg.addEventListener('click',()=>{const o=mob.hidden;mob.hidden=!o;bg.setAttribute('aria-expanded',o);h.classList.toggle('nx-menuopen',o);document.body.style.overflow=o?'hidden':''});
mob.querySelectorAll('a').forEach(a=>a.addEventListener('click',()=>{mob.hidden=true;h.classList.remove('nx-menuopen');document.body.style.overflow=''}));
})();
</script>'''


def footer():
    return f'''<footer class="nx-foot nx-dark">
  <div class="nx-fwrap">
    <div class="nx-fcols">
      <div><a class="nx-logo" href="{B}/"><img src="/img/mark.png" alt="" width="30" height="30"><span>FORTEX</span><span class="nx-uae"><em>UAE</em></span></a>
        <p>Банковские счета и финансовая инфраструктура в ОАЭ. Направление компании Fortex Global, Дубай.</p>
        <p class="nx-dim">Часы работы: пн–сб, 10:00–20:00 по Дубаю. Воскресенье выходной.</p></div>
      <div><h4>Услуги</h4><a href="{B}/schet-v-banke-oae/">Счёт в банке ОАЭ</a><a href="{B}/rezidentstvo-oae/">Резидентство и ВНЖ</a><a href="{B}/kompaniya-v-dubae/">Компания в Дубае</a><a href="{B}/#cases">Кейсы</a></div>
      <div><h4>Связь</h4><a href="https://t.me/Fortex_Dubai">Telegram @Fortex_Dubai</a><a href="https://wa.me/971558194123">WhatsApp +971 55 819 4123</a><a href="/c/call">Записаться на звонок</a><a href="mailto:alexey@fortex-uae.com">alexey@fortex-uae.com</a></div>
      <div><h4>Читать</h4><a href="{B}/articles/">Статьи</a><a href="{B}/privacy/">Политика конфиденциальности</a></div>
    </div>
    <p class="nx-legal">Fortex UAE не является банком и не принимает депозиты. Решение об открытии счёта принимает банк. Цены указаны как минимальные и уточняются после разбора ситуации.</p>
  </div>
</footer>'''


TEXT_FIX = [
    ("Не берём всю сумму вперёд: часть на старте, остальное после результата.", "Оплата по этапам: каждый этап оплачивается перед его началом, всю сумму сразу вносить не нужно."),
    ("Нет. Оплата по этапам: часть на старте, остальное после результата.", "Не обязательно всё сразу. Оплата по этапам: каждый этап оплачивается перед его началом."),
    ("Оплата по этапам: часть на старте, остальное после результата.", "Оплата по этапам: каждый этап оплачивается перед его началом."),
    ("Оплата по этапам, всю сумму вперёд не берём.", "Оплата по этапам, каждый этап перед его началом."),
    ("Часть на старте, остальное после результата.", "Оплата вперёд, но по этапам."),
    ("Почему у вас нет офиса и телефона?", "Как встретиться с командой?"),
    ("Клиенты у нас по всему миру, поэтому работаем через Telegram и Zoom, так быстрее и вся переписка сохраняется. Мы постоянно в Дубае и по договорённости встречаемся лично.",
     "Мы больше работаем онлайн: Telegram, WhatsApp, Zoom. Так быстрее, и вся переписка остаётся у вас. Если вы в Дубае, встретимся по запросу: просто напишите нам, и договоримся."),
    ("Встречаемся лично в Дубае</h3><p>Мы постоянно в Дубае. Если вам важно увидеть нас вживую, договоримся о встрече. Часть шагов в банке всё равно проходит лично, и на них мы рядом.",
     "Встречаемся в Дубае</h3><p>Наша команда постоянно в Дубае, встречи по согласованию. Не всё проходит удалённо: для части счетов нужна личная встреча с банкиром, в офисе или в отделении банка. Мы её организуем и заранее подготовим вас."),
    ("Личный счёт можно, в некоторых банках. Например, открывали Emirates NBD удалённо за 2 недели.",
     "Да. Мы постоянно открываем счета удалённо для резидентов и нерезидентов ОАЭ, например в Emirates NBD и FAB. Срок 1–2 недели."),
    ("Личный счёт можно в некоторых банках, например Emirates NBD мы открывали удалённо за 2 недели. Корпоративный обычно требует присутствия владельца.",
     "Да. Мы постоянно открываем счета удалённо для резидентов и нерезидентов ОАЭ, например в Emirates NBD и FAB. Срок 1–2 недели. Если для счёта нужна личная встреча с банкиром, организуем её."),
]


def clean(s):
    """Правки текста по оплате; убрать Telegram-канал и Instagram (там пока пусто)."""
    for a, b in TEXT_FIX:
        s = s.replace(a, b)
    s = re.sub(r'<div class="social">.*?</div>\s*(?=</div>)', "", s, flags=re.S)
    s = re.sub(r'<p class="small"[^>]*>[^<]*<a href="https://t.me/fortex_uae"[^>]*>[^<]*</a>\s*</p>', "", s)
    s = re.sub(r'<a [^>]*href="https://(t.me/fortex_uae|www.instagram.com/fortex__uae/)"[^>]*>.*?</a>', "", s, flags=re.S)
    s = s.replace(', "https://t.me/fortex_uae", "https://www.instagram.com/fortex__uae/"', "")
    return s


def relink(s):
    pages = r'(?:schet-v-banke-oae|rezidentstvo-oae|kompaniya-v-dubae|articles|privacy|spasibo)'
    s = re.sub(r'href="/(' + pages + r'[^"]*)"', lambda m: f'href="{B}/{m.group(1)}"', s)
    s = re.sub(r'href="/(#[^"]*)?"', lambda m: f'href="{B}/{m.group(1) or ""}"', s)
    return s


def prefix_custom(src):
    """Классы из home_src.html → x-класс, чтобы не пересекались со старыми стилями."""
    toks = set()
    for cl in re.findall(r'class="([^"]+)"', src):
        toks.update(cl.split())
    toks |= {"on", "in"}
    css = re.search(r"<style>(.*?)</style>", src, re.S).group(1)
    for t in sorted(toks, key=len, reverse=True):
        css = re.sub(r"\.(" + re.escape(t) + r")(?![\w-])", r".x-\1", css)
    def cls(m):
        return 'class="' + " ".join("x-" + c for c in m.group(1).split()) + '"'
    body = re.sub(r'class="([^"]+)"', cls, src)
    return css, body


def home(orig):
    src = open(os.path.join(HERE, "home_src.html"), encoding="utf-8").read()
    css, body = prefix_custom(src)
    css = re.sub(r"^:root\{", ":root{--xx:0;", css, flags=re.M)
    lines = body.split("\n")
    def block(a, b):
        return "\n".join(lines[a - 1:b])
    find = lambda pat: next(i + 1 for i, l in enumerate(lines) if l.startswith(pat))
    h0 = find('<div class="x-hero">'); w1 = find('<div class="x-wrap x-build"'); w2 = w1 + [i for i, l in enumerate(lines[w1:]) if l.startswith('<div class="x-wrap">')][0] + 1
    dk = find('<div class="x-dark">'); w3 = find('  <section id="faq">') - 1; fin = find('<div class="x-final">'); sc = find("<script>")
    hero_part = block(h0, w1 - 1).replace('<div class="x-hero">', '<div class="x-hero nx-dark">', 1)
    build_part = block(w1, w2 - 1)
    trust_cases = block(w2, dk - 1)
    team = block(dk, w3 - 1).replace('<div class="x-dark">', '<div class="x-dark nx-dark">', 1)
    final = block(fin, sc - 1).replace('<div class="x-final">', '<div class="x-final nx-final nx-dark">', 1)
    js = block(sc, len(lines))
    js = js.split("</script>")[0] + "</script>"
    # убрать логику старой шапки, обновить имена классов в скрипте
    js = re.sub(r"// header color.*?setHdr\(\);\n", "", js, flags=re.S)
    js = (js.replace("'.reveal'", "'.x-reveal'").replace("add('in')", "add('x-in')").replace("toggle('on'", "toggle('x-on'")
            .replace("'.lbl'", "'.x-lbl'").replace("add('on')", "add('x-on')").replace("'#prog div'", "'#prog div'"))
    m = re.search(r"<main[^>]*>(.*)</main>", orig, re.S).group(1)
    sec = lambda sid: re.search(r'<section class="sec[^"]*" id="' + sid + r'">.*?</section>', m, re.S).group(0)
    kb = re.findall(r'<section class="sec">.*?</section>', m, re.S)[-1]
    main = "\n".join([hero_part, build_part, sec("who"), trust_cases, team, sec("faq"), kb, final])
    main = main.replace('href="#svc"', f'href="{B}/#directions"').replace('id="svc"', 'id="directions"')
    return f"<style>{css}</style>\n<main>\n{main}\n</main>\n{js}"


def page(path):
    s = open(path, encoding="utf-8").read()
    if "<main" not in s:
        return None
    rel = os.path.relpath(path, PUB)
    s = s.replace("<head>", '<head>\n<meta name="robots" content="noindex,nofollow">', 1)
    s = s.replace('family=Onest:wght@400;500;600&family=Unbounded:wght@500;600', 'family=Onest:wght@400;500;600;700&family=Unbounded:wght@500;600;700;800;900&family=Manrope:wght@500;600;700;800')
    s = s.replace('<link rel="stylesheet" href="/style.css">', f'<link rel="stylesheet" href="/style.css">\n<link rel="stylesheet" href="{B}/nx.css">')
    s = re.sub(r'<header class="top">.*?</header>', header(), s, count=1, flags=re.S)
    s = re.sub(r'<footer class="foot">.*?</footer>', footer(), s, count=1, flags=re.S)
    if rel == "index.html":
        s = re.sub(r"<main[^>]*>.*</main>", lambda _: home(open(path, encoding="utf-8").read()), s, count=1, flags=re.S)
        s = s.replace("<body", '<body data-nx="home"', 1)
    else:
        s = s.replace("<body", '<body data-nx="page"', 1)
        s = s.replace('<section class="svc-sec"', '<section class="svc-sec nx-dark"')
        s = s.replace('<section class="hero">', '<section class="hero nx-dark">', 1).replace('<section class="portal-hero">', '<section class="portal-hero nx-dark">', 1)
    s = s.replace('<script src="/video.js" defer></script>', "").replace('<script src="/video.js"></script>', "")
    s = re.sub(r'<script[^>]*src="/(video|bank).js"[^>]*></script>', "", s)
    s = s.replace("</body>", NX_JS + "\n</body>", 1)
    s = clean(relink(s))
    out = os.path.join(OUT, rel)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    open(out, "w", encoding="utf-8").write(s)
    return rel


if __name__ == "__main__":
    collect_articles()
    os.makedirs(OUT, exist_ok=True)
    done = [r for p in sorted(glob.glob(os.path.join(PUB, "**", "index.html"), recursive=True))
            if not p.startswith(os.path.join(PUB, "v")) and "/draft/" not in p and (r := page(p))]
    open(os.path.join(OUT, "nx.css"), "w", encoding="utf-8").write(open(os.path.join(HERE, "nx.css"), encoding="utf-8").read())
    print(len(done), "pages:", ", ".join(done))
