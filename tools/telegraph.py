"""Публикация статей в Telegraph (внешние площадки со ссылкой на сайт, решение Александра 18.11).
Каждый telegraph/<slug>.html, которого нет в telegraph/published.json, публикуется один раз.
Первая строка файла: заголовок. Дальше простой HTML: <p>, <h3>, <h4>, <ul>/<ol>/<li>, <b>, <i>, <a href>, <blockquote>."""
import glob, json, os, urllib.parse, urllib.request
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


def main():
    pub = json.load(open(PUB)) if os.path.exists(PUB) else {}
    todo = [f for f in sorted(glob.glob("telegraph/*.html")) if os.path.basename(f)[:-5] not in pub]
    if not todo:
        print("nothing to publish")
        return
    acc = call("createAccount", short_name="FortexUAE", author_name="Fortex UAE", author_url="https://fortex-uae.com/")
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
