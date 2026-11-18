"""Публикация статей в Telegraph (внешние площадки со ссылкой на сайт, решение Александра 18.11).
Каждый telegraph/<slug>.html, которого нет в telegraph/published.json, публикуется один раз.
Первая строка файла: заголовок. Дальше простой HTML: <p>, <h3>, <h4>, <ul>/<ol>/<li>, <b>, <i>, <a href>, <blockquote>."""
import glob, json, os, re, urllib.parse, urllib.request
from html.parser import HTMLParser

API = "https://api.telegra.ph/"
PUB = "telegraph/published.json"
OK_TAGS = {"p", "h3", "h4", "ul", "ol", "li", "b", "strong", "i", "em", "a", "blockquote", "br"}


def call(method, **data):
    body = urllib.parse.urlencode({k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v) for k, v in data.items()}).encode()
    r = json.load(urllib.request.urlopen(urllib.request.Request(API + method, data=body), timeout=60))
    if not r.get("ok"):
        raise RuntimeError(f"{method}: {r}")
    return r["result"]


class P(HTMLParser):
    def __init__(self):
        super().__init__()
        self.root = {"children": []}
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        if tag not in OK_TAGS:
            return
        n = {"tag": tag, "children": []}
        if tag == "a":
            n["attrs"] = {"href": dict(attrs).get("href", "")}
        self.stack[-1]["children"].append(n)
        if tag != "br":
            self.stack.append(n)

    def handle_endtag(self, tag):
        if tag in OK_TAGS and tag != "br" and len(self.stack) > 1 and self.stack[-1]["tag"] == tag:
            self.stack.pop()

    def handle_data(self, d):
        if d.strip() or (len(self.stack) > 1 and d):
            self.stack[-1]["children"].append(d if len(self.stack) > 1 else d.strip())


def clean(n):
    if isinstance(n, str):
        return n
    out = {"tag": n["tag"]}
    if n.get("attrs"):
        out["attrs"] = n["attrs"]
    ch = [clean(c) for c in n.get("children", []) if not (isinstance(c, str) and not c.strip() and n["tag"] in ("ul", "ol"))]
    if ch:
        out["children"] = ch
    return out


SITE = "https://fortex-uae.com"


def plain(t):
    t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", t)
    return re.sub(r"[*_`]+", "", t).strip()


def article_page(f):
    """Короткая версия статьи сайта для Telegraph: вступление, о чём статья, ссылка на полный текст (не копия, чтобы не было дубля)."""
    raw = open(f, encoding="utf-8").read()
    m = re.match(r"---\n(.*?)\n---\n(.*)", raw, re.S)
    if not m:
        return None
    meta = dict(l.split(":", 1) for l in m.group(1).splitlines() if ":" in l)
    meta = {k.strip(): v.strip() for k, v in meta.items()}
    if meta.get("status") == "draft":
        return None
    slug = os.path.basename(f)[:-3]
    url = f"{SITE}/articles/{slug}/?utm_source=telegraph&utm_campaign=article"
    body = m.group(2)
    paras = [plain(x) for x in body.split("\n\n") if x.strip() and not x.lstrip().startswith(("#", "|", "-", "1.", ">", "!"))][:2]
    heads = [plain(l[3:]) for l in body.splitlines() if l.startswith("## ") and "Что делаем мы" not in l][:8]
    nodes = [{"tag": "p", "children": [p]} for p in paras]
    if heads:
        nodes.append({"tag": "h4", "children": ["В полной статье разбираем:"]})
        nodes.append({"tag": "ul", "children": [{"tag": "li", "children": [h]} for h in heads]})
    nodes.append({"tag": "p", "children": [{"tag": "b", "children": ["Полная статья с расчётами и ответами на частые вопросы: "]},
                                            {"tag": "a", "attrs": {"href": url}, "children": [meta.get("title", "читать на сайте")]}]})
    nodes.append({"tag": "p", "children": ["Fortex UAE, команда в Дубае с 2022 года: визы, Emirates ID, счета, компании и рабочая виза под ипотеку. Вопросы в Telegram ",
                                            {"tag": "a", "attrs": {"href": "https://t.me/Fortex_Dubai"}, "children": ["@Fortex_Dubai"]}, "."]})
    return meta.get("title", slug), nodes


def main():
    pub = json.load(open(PUB)) if os.path.exists(PUB) else {}
    arts = [f for f in sorted(glob.glob("content/articles/*.md")) if "a:" + os.path.basename(f)[:-3] not in pub]
    todo = [f for f in sorted(glob.glob("telegraph/*.html")) if os.path.basename(f)[:-5] not in pub]
    if not todo and not arts:
        print("nothing to publish")
        return
    acc = call("createAccount", short_name="FortexUAE", author_name="Fortex UAE", author_url="https://fortex-uae.com/")
    for f in arts:
        r = article_page(f)
        if not r:
            continue
        title, nodes = r
        page = call("createPage", access_token=acc["access_token"], title=title[:256], author_name="Fortex UAE",
                    author_url="https://fortex-uae.com/", content=nodes)
        pub["a:" + os.path.basename(f)[:-3]] = {"url": page["url"], "title": title}
        print("article", f, page["url"])
        json.dump(pub, open(PUB, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for f in todo:
        slug = os.path.basename(f)[:-5]
        raw = open(f, encoding="utf-8").read().strip()
        title, html = raw.split("\n", 1)
        p = P(); p.feed(html)
        nodes = [clean(c) for c in p.root["children"] if not (isinstance(c, str) and not c.strip())]
        page = call("createPage", access_token=acc["access_token"], title=title.strip()[:256], author_name="Fortex UAE",
                    author_url="https://fortex-uae.com/", content=nodes)
        pub[slug] = {"url": page["url"], "title": title.strip()}
        print(slug, page["url"])
    json.dump(pub, open(PUB, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
