"""Поиск стоковых видео для рилсов с превью: research/stock/<n>.jpg (лист миниатюр с номерами) и index.json.
python3 tools/stock_search.py "dubai marina|documents desk|..."  (ключи PIXABAY_API_KEY, PEXELS_API_KEY)
Потом нужный клип закрепляется в шоте рилса полем "link" (прямая ссылка) и "site"."""
import io, json, os, sys, urllib.parse, urllib.request
from PIL import Image, ImageDraw

OUT = "research/stock"
UA = {"User-Agent": "Mozilla/5.0"}


def get(url, headers=None, raw=False):
    r = urllib.request.urlopen(urllib.request.Request(url, headers={**UA, **(headers or {})}), timeout=60).read()
    return r if raw else json.loads(r)


def search(q):
    res = []
    k = os.environ.get("PIXABAY_API_KEY")
    if k:
        for v in get(f"https://pixabay.com/api/videos/?key={k}&q={urllib.parse.quote(q)}&per_page=30&safesearch=true").get("hits", []):
            vs = v.get("videos") or {}
            files = [f for f in vs.values() if f and f.get("url") and f.get("height", 0) >= 1080]
            if not files:
                continue
            f = sorted(files, key=lambda f: -f["height"])[0]
            th = (vs.get("medium") or vs.get("small") or {}).get("thumbnail")
            res.append({"site": "pixabay", "id": f"px{v['id']}", "link": f["url"], "thumb": th, "w": f["width"], "h": f["height"],
                        "dur": v.get("duration"), "tags": v.get("tags", "")})
    k = os.environ.get("PEXELS_API_KEY")
    if k:
        try:
            for v in get(f"https://api.pexels.com/videos/search?query={urllib.parse.quote(q)}&per_page=20", {"Authorization": k}).get("videos", []):
                files = [f for f in v.get("video_files", []) if f.get("height") and f["height"] >= 1080 and f.get("file_type") == "video/mp4"]
                if not files:
                    continue
                f = sorted(files, key=lambda f: f["height"])[0]
                res.append({"site": "pexels", "id": f"pe{v['id']}", "link": f["link"], "thumb": v.get("image"), "w": f["width"], "h": f["height"],
                            "dur": v.get("duration"), "tags": v.get("url", "")[-60:]})
        except Exception as e:
            print("pexels", e)
    return res


def main():
    os.makedirs(OUT, exist_ok=True)
    index = {}
    for n, q in enumerate(sys.argv[1].split("|")):
        items = search(q.strip())[:24]
        index[q] = items
        sheet = Image.new("RGB", (6 * 240, 4 * 175), "white")
        d = ImageDraw.Draw(sheet)
        for i, it in enumerate(items):
            try:
                im = Image.open(io.BytesIO(get(it["thumb"], raw=True))).convert("RGB")
                im.thumbnail((236, 150))
                sheet.paste(im, ((i % 6) * 240, (i // 6) * 175))
            except Exception:
                pass
            d.rectangle(((i % 6) * 240, (i // 6) * 175, (i % 6) * 240 + 70, (i // 6) * 175 + 18), fill="black")
            d.text(((i % 6) * 240 + 3, (i // 6) * 175 + 3), f"{i} {it['site'][:2]} {it['dur']}s", fill="white")
            d.text(((i % 6) * 240 + 2, (i // 6) * 175 + 155), it["tags"][:38], fill="black")
        sheet.save(f"{OUT}/{n}.jpg", quality=80)
        print(n, q, len(items))
    json.dump(index, open(f"{OUT}/index.json", "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
