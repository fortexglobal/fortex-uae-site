#!/usr/bin/env python3
"""Сборка сайта Fortex UAE без внешних зависимостей.

content/articles/*.md  ->  public/articles/<slug>/index.html
content/site.py         ->  главная страница
Запуск: python3 build.py   (Netlify делает это сам при каждом обновлении)
"""
import html, json, os, re, shutil, datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "public")
SITE = "https://fortex-uae.com"
TG = "https://t.me/FortexGlobal"
CHANNEL = "https://t.me/fortex_uae"
CAL = "https://calendly.com/fortex-uae/30min"
EMAIL = "alexey@fortex-uae.com"
MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"]


def esc(s):
    return html.escape(s or "", quote=True)


def ru_date(d):
    return f"{d.day} {MONTHS[d.month - 1]} {d.year}"


# ---------- tiny markdown ----------
def inline(t):
    t = esc(t)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<em>\1</em>", t)
    t = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", lambda m: f'<a href="{m.group(2)}">{m.group(1)}</a>', t)
    return t


def md(text):
    out, para, lst, ltype = [], [], [], None

    def flush():
        nonlocal para, lst, ltype
        if para:
            out.append("<p>" + inline(" ".join(para)) + "</p>")
            para = []
        if lst:
            out.append(f"<{ltype}>" + "".join(f"<li>{inline(i)}</li>" for i in lst) + f"</{ltype}>")
            lst, ltype = [], None

    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip():
            flush(); continue
        m = re.match(r"^(#{2,4})\s+(.*)", line)
        if m:
            flush(); n = len(m.group(1)); out.append(f"<h{n}>{inline(m.group(2))}</h{n}>"); continue
        m = re.match(r"^\s*[-*]\s+(.*)", line)
        if m:
            if para: flush()
            if ltype not in (None, "ul"): flush()
            ltype = "ul"; lst.append(m.group(1)); continue
        m = re.match(r"^\s*\d+[.)]\s+(.*)", line)
        if m:
            if para: flush()
            if ltype not in (None, "ol"): flush()
            ltype = "ol"; lst.append(m.group(1)); continue
        if line.startswith("> "):
            flush(); out.append("<blockquote>" + inline(line[2:]) + "</blockquote>"); continue
        if lst: flush()
        para.append(line.strip())
    flush()
    return "\n".join(out)


def read_articles():
    arts = []
    d = os.path.join(ROOT, "content", "articles")
    for fn in sorted(os.listdir(d)):
        if not fn.endswith(".md"):
            continue
        raw = open(os.path.join(d, fn), encoding="utf-8").read()
        m = re.match(r"^---\n(.*?)\n---\n(.*)$", raw, re.S)
        meta, body = {}, raw
        if m:
            for l in m.group(1).splitlines():
                if ":" in l:
                    k, v = l.split(":", 1); meta[k.strip()] = v.strip().strip('"')
            body = m.group(2)
        meta.setdefault("slug", fn[:-3])
        meta["date_obj"] = datetime.date.fromisoformat(meta.get("date", "2026-10-20"))
        if meta["date_obj"] > datetime.date.today():
            continue  # запланированная статья, ещё не публикуем
        meta["html"] = md(body)
        meta["words"] = len(re.findall(r"\w+", body))
        arts.append(meta)
    arts.sort(key=lambda a: a["date_obj"], reverse=True)
    return arts


# ---------- layout ----------
CSS = open(os.path.join(ROOT, "static", "style.css"), encoding="utf-8").read() if os.path.exists(os.path.join(ROOT, "static", "style.css")) else ""


def page(title, desc, body, path="/", jsonld=None, og_type="website"):
    url = SITE + path
    ld = "".join(f'<script type="application/ld+json">{json.dumps(j, ensure_ascii=False)}</script>' for j in (jsonld or []))
    return f"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{url}">
<link rel="icon" href="/favicon.png">
<meta property="og:type" content="{og_type}">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{url}">
<meta property="og:image" content="{SITE}/img/og.jpg">
<meta property="og:locale" content="ru_RU">
<meta name="twitter:card" content="summary_large_image">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Onest:wght@400;500;600&family=Unbounded:wght@500;600&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/style.css">
<script src="/form.js" defer></script>
<script src="/motion.js" defer></script>
<script src="/video.js"></script>
<script src="/bank.js" defer></script>
<meta name="theme-color" content="#F2F5F8">
{ld}
</head>
<body>
<header class="top">
  <div class="wrap top-in">
    <a class="brand" href="/"><img src="/img/mark.png" alt="" width="34" height="34"><span>FORTEX <b>UAE</b></span></a>
    <nav class="nav">
      <a href="/schet-v-banke-oae/">Счета</a><a href="/rezidentstvo-oae/">Резидентство</a><a href="/kompaniya-v-dubae/">Компании</a><a href="/#cases">Кейсы</a><a href="/articles/">Статьи</a>
    </nav>
    <a class="btn btn-sm" href="#form">Оставить заявку</a>
  </div>
</header>
{body}
{FORM}
<footer class="foot">
  <div class="wrap foot-in">
    <div>
      <a class="brand" href="/"><img src="/img/mark.png" alt="" width="30" height="30"><span>FORTEX <b>UAE</b></span></a>
      <p class="muted">Банковские счета и финансовая инфраструктура в ОАЭ. Направление компании Fortex Global, Дубай.</p>
    </div>
    <div class="foot-links">
      <a href="{TG}">Telegram @FortexGlobal</a>
      <a href="{CHANNEL}">Канал Fortex UAE</a>
      <a href="{CAL}">Записаться на звонок</a>
      <a href="mailto:{EMAIL}">{EMAIL}</a>
      <a href="/articles/">Статьи</a>
    </div>
  </div>
  <div class="wrap fine">Fortex UAE не является банком и не принимает депозиты. Решение об открытии счёта принимает банк. Цены указаны как минимальные и уточняются после разбора ситуации.</div>
</footer>
</body>
</html>"""


FORM = f"""<section class="sec form-sec" id="form"><div class="wrap form-in">
  <div>
    <h2 class="h2">Расскажите о задаче, ответим в Telegram</h2>
    <p class="lead">Обычно отвечаем в течение 30 минут в рабочее время. Или сразу напишите нам: <a href="{TG}">@FortexGlobal</a>, либо <a href="{CAL}">запишитесь на звонок</a>.</p>
  </div>
  <form class="lead-form" name="lead" method="POST" data-netlify="true" netlify-honeypot="company_site" action="/spasibo/">
    <input type="hidden" name="form-name" value="lead">
    <p class="hp"><label>Не заполняйте <input name="company_site"></label></p>
    <label>Имя<input name="name" required autocomplete="name" placeholder="Как к вам обращаться"></label>
    <label>Telegram<input name="telegram" required placeholder="@username или телефон"></label>
    <label><span>Задача <span class="opt">необязательно</span></span><textarea name="task" rows="3" placeholder="Например: нужен корпоративный счёт, компания во фризоне, был отказ в банке"></textarea></label>
    <input type="hidden" name="page">
    <button class="btn" type="submit">Отправить заявку</button>
    <p class="form-msg" role="status"></p>
    <p class="small">Нажимая кнопку, вы соглашаетесь, что мы свяжемся с вами по указанным контактам.</p>
  </form>
</div></section>"""


def article_card(a):
    return f"""<a class="card art" href="/articles/{a['slug']}/">
  <span class="tag">{esc(a.get('topic', 'Статья'))}</span>
  <h3>{esc(a['title'])}</h3>
  <p>{esc(a.get('description', ''))}</p>
  <span class="meta">{ru_date(a['date_obj'])} · {max(2, round(a['words'] / 150))} мин</span>
</a>"""


def build():
    if os.path.exists(OUT):
        shutil.rmtree(OUT)
    shutil.copytree(os.path.join(ROOT, "static"), OUT)
    arts = read_articles()

    # ---- home ----
    from content.site import HOME, FAQ
    faq_html = "".join(f"<details><summary>{esc(q)}</summary><p>{esc(a)}</p></details>" for q, a in FAQ)
    latest = "".join(article_card(a) for a in arts[:3])
    body = HOME.replace("{{FAQ}}", faq_html).replace("{{LATEST}}", latest).replace("{{TG}}", TG).replace("{{CAL}}", CAL)
    org = {"@context": "https://schema.org", "@type": "ProfessionalService", "name": "Fortex UAE", "url": SITE,
           "logo": SITE + "/img/mark.png", "image": SITE + "/img/og.jpg", "areaServed": "AE",
           "address": {"@type": "PostalAddress", "addressLocality": "Dubai", "addressCountry": "AE"},
           "description": "Открытие корпоративных и личных счетов в банках ОАЭ для владельцев российского паспорта, компании на mainland и во фризонах, ВНЖ Virtual Work и рабочие визы, Emirates ID. Работаем в Дубае с 2022 года.",
           "sameAs": [TG, CHANNEL], "knowsLanguage": ["ru", "en"], "foundingDate": "2022",
           "slogan": "С 2022 года в Дубае: ВНЖ, банки, компании и финансовые вопросы",
           "makesOffer": [
               {"@type": "Offer", "name": "Корпоративный счёт в банке ОАЭ", "priceCurrency": "USD", "price": "5000", "description": "от 5 000 USD"},
               {"@type": "Offer", "name": "Личный счёт в банке ОАЭ", "priceCurrency": "USD", "price": "1500", "description": "от 1 500 USD"},
               {"@type": "Offer", "name": "ВНЖ Virtual Work + Emirates ID", "priceCurrency": "USD", "price": "2000", "description": "от 2 000 USD"},
               {"@type": "Offer", "name": "Рабочая виза + Emirates ID", "priceCurrency": "USD", "price": "5500", "description": "от 5 500 USD"}]}
    faq_ld = {"@context": "https://schema.org", "@type": "FAQPage",
              "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in FAQ]}
    open(os.path.join(OUT, "index.html"), "w", encoding="utf-8").write(
        page("Счёт в банке ОАЭ для россиян, компании и визы в Дубае | Fortex UAE",
             "Открываем корпоративные и личные счета в банках ОАЭ владельцам российского паспорта, компании на mainland и во фризонах, Virtual Work и рабочие визы. Под ключ, со всеми банками ОАЭ.",
             body, "/", [org, faq_ld]))

    # ---- service pages ----
    from content.pages import PAGES
    for pg in PAGES:
        faq_html = "".join(f"<details><summary>{esc(q)}</summary><p>{esc(a)}</p></details>" for q, a in pg["faq"])
        rel = "".join(article_card(a) for a in arts[:3])
        body = f"""<main><section class="sec page-hero"><div class="wrap narrow">
<h1 class="h1">{esc(pg['h1'])}</h1><p class="lead">{esc(pg['lead'])}</p>
<div class="row"><a class="btn" href="#form">Оставить заявку</a><a class="btn btn-ghost" href="{TG}">Написать в Telegram</a></div></div></section>
<section class="sec alt"><div class="wrap narrow"><div class="prose">{md(pg['body'])}</div></div></section>
<section class="sec"><div class="wrap narrow"><h2 class="h2">Частые вопросы</h2><div class="faq">{faq_html}</div></div></section>
<section class="sec alt"><div class="wrap"><div class="head-row"><h2 class="h2">Статьи по теме</h2><a class="link" href="/articles/">Все статьи</a></div><div class="grid3">{rel}</div></div></section></main>"""
        svc = {"@context": "https://schema.org", "@type": "Service", "name": pg["service"], "serviceType": pg["service"],
               "provider": {"@type": "Organization", "name": "Fortex UAE", "url": SITE}, "areaServed": "AE", "audience": {"@type": "Audience", "audienceType": "Владельцы российского паспорта"},
               "offers": {"@type": "Offer", "priceCurrency": pg.get("currency", "USD"), "price": pg["price"]}}
        fq = {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in pg["faq"]]}
        bc = {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [{"@type": "ListItem", "position": 1, "name": "Главная", "item": SITE + "/"}, {"@type": "ListItem", "position": 2, "name": pg["h1"], "item": f"{SITE}/{pg['slug']}/"}]}
        os.makedirs(os.path.join(OUT, pg["slug"]), exist_ok=True)
        open(os.path.join(OUT, pg["slug"], "index.html"), "w", encoding="utf-8").write(page(pg["title"], pg["description"], body, f"/{pg['slug']}/", [svc, fq, bc]))

    # ---- thank you ----
    os.makedirs(os.path.join(OUT, "spasibo"), exist_ok=True)
    open(os.path.join(OUT, "spasibo", "index.html"), "w", encoding="utf-8").write(page("Заявка отправлена | Fortex UAE", "Спасибо, мы свяжемся с вами в Telegram.",
        f"<main><section class='sec'><div class='wrap narrow'><h1 class='h1'>Спасибо, заявка отправлена</h1><p class='lead'>Свяжемся с вами в Telegram в ближайшее время. Если срочно, напишите сами: <a href='{TG}'>@FortexGlobal</a></p><a class='btn' href='/'>На главную</a></div></section></main>", "/spasibo/"))

    # ---- articles ----
    os.makedirs(os.path.join(OUT, "articles"), exist_ok=True)
    cards = "".join(article_card(a) for a in arts) or "<p class='muted'>Скоро здесь появятся статьи.</p>"
    idx = f"""<main><section class="sec"><div class="wrap">
<h1 class="h1">Банки, визы и компании в ОАЭ: разбираем по делу</h1>
<p class="lead">Как сейчас открывают счета владельцам российского паспорта, чем Virtual Work отличается от рабочей визы, почему банки отказывают и что с этим делать.</p>
<div class="grid3">{cards}</div></div></section></main>"""
    open(os.path.join(OUT, "articles", "index.html"), "w", encoding="utf-8").write(
        page("Статьи о банках, визах и компаниях в ОАЭ | Fortex UAE", "Практические статьи: счета в банках ОАЭ для россиян, Virtual Work, рабочая виза, Emirates ID, компании в Дубае.", idx, "/articles/"))
    for a in arts:
        p = f"/articles/{a['slug']}/"
        more = "".join(article_card(x) for x in [x for x in arts if x is not a][:3])
        body = f"""<main><article class="sec"><div class="wrap narrow">
<a class="back" href="/articles/">← Все статьи</a>
<p class="eyebrow">{esc(a.get('topic', 'Статья'))}, {ru_date(a['date_obj'])}</p>
<h1 class="h1">{esc(a['title'])}</h1>
<p class="lead">{esc(a.get('description', ''))}</p>
<div class="prose">{a['html']}</div>
<div class="cta-box"><h3>Разберём вашу ситуацию за 5 минут</h3><p>Напишите, какой у вас паспорт, есть ли компания в ОАЭ и были ли отказы банков. Скажем, какой банк сейчас реально откроет счёт.</p>
<div class="row"><a class="btn" href="{TG}">Написать в Telegram</a><a class="btn btn-ghost" href="{CAL}">Записаться на звонок</a></div></div>
<p class="small" style="margin-top:18px">Новые разборы по банкам и визам ОАЭ выходят в нашем канале <a href="{CHANNEL}" style="color:var(--red2)">t.me/fortex_uae</a></p>
</div></article>
{('<section class="sec alt"><div class="wrap"><h2 class="h2">Ещё статьи</h2><div class="grid3">' + more + '</div></div></section>') if more else ''}
</main>"""
        ld = {"@context": "https://schema.org", "@type": "Article", "headline": a["title"], "description": a.get("description", ""),
              "datePublished": a["date_obj"].isoformat(), "dateModified": a.get("updated", a["date_obj"].isoformat()),
              "inLanguage": "ru", "mainEntityOfPage": SITE + p, "image": SITE + "/img/og.jpg",
              "author": {"@type": "Organization", "name": "Fortex UAE", "url": SITE},
              "publisher": {"@type": "Organization", "name": "Fortex UAE", "logo": {"@type": "ImageObject", "url": SITE + "/img/mark.png"}}}
        os.makedirs(os.path.join(OUT, "articles", a["slug"]), exist_ok=True)
        open(os.path.join(OUT, "articles", a["slug"], "index.html"), "w", encoding="utf-8").write(
            page(a["title"] + " | Fortex UAE", a.get("description", ""), body, p, [ld], "article"))

    # ---- sitemap, robots, llms.txt ----
    urls = [("/", datetime.date.today())] + [(f"/{pg['slug']}/", datetime.date.today()) for pg in PAGES] + [("/articles/", arts[0]["date_obj"] if arts else datetime.date.today())] + [(f"/articles/{a['slug']}/", a["date_obj"]) for a in arts]
    sm = "".join(f"<url><loc>{SITE}{u}</loc><lastmod>{d.isoformat()}</lastmod></url>" for u, d in urls)
    open(os.path.join(OUT, "sitemap.xml"), "w").write(f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{sm}</urlset>')
    open(os.path.join(OUT, "robots.txt"), "w").write(f"User-agent: *\nAllow: /\nSitemap: {SITE}/sitemap.xml\n")
    llms = ["# Fortex UAE", "", "> Открытие корпоративных и личных счетов в банках ОАЭ для владельцев российского паспорта, компании на mainland и во фризонах, ВНЖ Virtual Work и рабочие визы, Emirates ID. В Дубае с 2022 года. Связь: Telegram @FortexGlobal.", "",
            "## Услуги и цены", "- Корпоративный счёт: от 5 000 USD", "- Личный счёт (в т.ч. удалённо): от 1 500 USD", "- ВНЖ Virtual Work + Emirates ID (самый доступный вариант, слабее в банках): от 2 000 USD", "- Рабочая виза + Emirates ID: от 5 500 USD", "- Компания во фризоне: от 14 000 AED; на mainland: от 22 000 AED", "",
            "## Страницы"] + [f"- [{pg['h1']}]({SITE}/{pg['slug']}/): {pg['description']}" for pg in PAGES] + ["", "## Статьи"] + [f"- [{a['title']}]({SITE}/articles/{a['slug']}/): {a.get('description', '')}" for a in arts]
    open(os.path.join(OUT, "llms.txt"), "w", encoding="utf-8").write("\n".join(llms) + "\n")
    print(f"built: {len(arts)} articles -> {OUT}")


if __name__ == "__main__":
    build()
