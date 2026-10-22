"""Обложки постов целиком в GitHub Actions.

covers/requests/<slug>.json: {"prompt": "<сцена для нейросети, по-английски>", "title": "<основная мысль>", "topic": "<рубрика>"}
1) если нет covers/bg/<slug>.jpg — генерирует фон через OpenRouter (tools/ai_bg.py);
2) если заявка изменилась с прошлой отрисовки — рисует static/covers/<slug>.jpg и static/covers/tg/<slug>.jpg
   в стиле photo (размытый фон по теме, сверху крупно основная мысль).
Чтобы перерисовать с новым фоном, удалите covers/bg/<slug>.jpg или добавьте в заявку "new_bg": true.
"""
import glob, hashlib, json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import ai_bg  # noqa: E402
import cover  # noqa: E402
from PIL import Image  # noqa: E402


def main():
    for f in sorted(glob.glob(os.path.join(ROOT, "covers", "requests", "*.json"))):
        slug = os.path.basename(f)[:-5]
        req = json.load(open(f, encoding="utf-8"))
        bg = os.path.join(ROOT, "covers", "bg", slug + ".jpg")
        if req.get("new_bg") and os.path.exists(bg):
            os.remove(bg)
            req.pop("new_bg"); json.dump(req, open(f, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        if not os.path.exists(bg) and req.get("prompt"):
            data = ai_bg.gen(req["prompt"])
            if not data:  # модель отказала (например, из-за документов в описании): берём нейтральную сцену
                data = ai_bg.gen(req.get("fallback_prompt") or "modern Dubai business district at golden hour, glass towers, "
                                 "a laptop and coffee on a desk in the foreground, calm premium mood")
            if data:
                os.makedirs(os.path.dirname(bg), exist_ok=True)
                open(bg, "wb").write(data)
                Image.open(bg).convert("RGB").save(bg, "JPEG", quality=90)
                print("bg ok", slug)
            else:
                print("bg fail", slug)
        if not req.get("title"):
            continue
        h = hashlib.md5((json.dumps(req, sort_keys=True, ensure_ascii=False) + str(os.path.exists(bg) and os.path.getsize(bg))).encode()).hexdigest()
        mark = os.path.join(ROOT, "covers", "rendered", slug + ".txt")
        if os.path.exists(mark) and open(mark).read().strip() == h:
            continue
        if os.path.exists(bg):
            cover.render(slug, req["title"], req.get("topic", "Fortex UAE"), "photo", None, bg)
        else:
            cover.render(slug, req["title"], req.get("topic", "Fortex UAE"), "photo", req.get("scene", "city"), None)
        os.makedirs(os.path.dirname(mark), exist_ok=True)
        open(mark, "w").write(h)
        print("rendered", slug)


if __name__ == "__main__":
    ai_bg.KEY = os.environ.get("OPENROUTER_API_KEY", "")
    main()
