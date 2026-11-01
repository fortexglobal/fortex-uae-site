"""Библиотека живых фото Александра для Threads (threads/photos/).
Для каждого нового фото: HEIC → JPG, уменьшение до 1600 px, удаление EXIF (там GPS), описание нейросетью
(что на фото, где, настроение, есть ли лица, к каким темам подходит). Всё пишется в threads/photos/inbox.json.
Запускает GitHub Actions (workflow Photo library) при появлении фото и раз в 2 часа."""
import base64, io, json, os, sys, urllib.request
from PIL import Image, ImageOps
try:
    import pillow_heif; pillow_heif.register_heif_opener()
except Exception as e:
    print("no heif support:", e)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, "threads", "photos")
IP = os.path.join(D, "inbox.json")
KEY = os.environ.get("OPENROUTER_API_KEY", "")
PROMPT = """Ты помогаешь вести Threads компании Fortex UAE (Дубай: счета в банках ОАЭ, визы, Emirates ID, компании) и личный Threads её основателя Александра (жизнь в Дубае, бизнес, инвестиции, падел).
Это живое фото Александра. Опиши его и верни ТОЛЬКО JSON без пояснений:
{"desc": "одно предложение по-русски, что на фото", "place": "тип места (кафе, лобби отеля, офис, пляж, Марина, вид с высоты, улица, машина, спорт и т.п.)",
 "landmark": "узнаваемое место Дубая, если уверен, иначе пусто", "time": "утро|день|вечер|ночь|непонятно", "mood": "2-3 слова",
 "faces": число лиц, которые можно узнать, "text_visible": "заметные надписи/бренды или пусто", "quality": оценка 1-5 для соцсетей,
 "themes": ["2-5 тем из списка, к которым фото подходит: работа, встреча, кофе, офис, жизнь в Дубае, вид, вечерний Дубай, роскошь, переезд, деньги, инвестиции, недвижимость, банк, документы, спорт, падел, отдых, еда, машина, путешествия"],
 "ideas": ["2 короткие идеи подписи для Threads по-русски, до 80 знаков, без хэштегов"]}"""


def describe(jpg_bytes):
    if not KEY:
        return None
    body = json.dumps({"model": "google/gemini-2.5-flash", "max_tokens": 500, "messages": [{"role": "user", "content": [
        {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(jpg_bytes).decode()}},
        {"type": "text", "text": PROMPT}]}]}).encode()
    req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", body, {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"})
    try:
        t = json.load(urllib.request.urlopen(req, timeout=120))["choices"][0]["message"]["content"].strip()
        t = t[t.find("{"): t.rfind("}") + 1]
        return json.loads(t)
    except Exception as e:
        print("describe error", e)
        return None


def main():
    inbox = json.load(open(IP, encoding="utf-8")) if os.path.exists(IP) else []
    known = {x["file"] for x in inbox}
    # фото, которые лежат в папке, но не попали в очередь (например, после ошибок)
    for f in sorted(os.listdir(D)):
        p = f"threads/photos/{f}"
        if f.lower().rsplit(".", 1)[-1] in ("jpg", "jpeg", "png", "webp", "heic", "heif") and p not in known:
            inbox.append({"file": p, "caption": "", "album": "", "at": "", "used": False})
    changed = 0
    for x in inbox:
        if x.get("desc") and not x["file"].lower().endswith((".heic", ".heif", ".png", ".webp")):
            continue
        src = os.path.join(ROOT, x["file"])
        if not os.path.exists(src):
            continue
        try:
            im = ImageOps.exif_transpose(Image.open(src)).convert("RGB")
        except Exception as e:
            print("cannot open", src, e); continue
        im.thumbnail((1600, 1600))
        out = os.path.splitext(src)[0] + ".jpg"
        buf = io.BytesIO(); im.save(buf, "JPEG", quality=86, optimize=True)  # без EXIF: геолокация не уходит в соцсети
        open(out, "wb").write(buf.getvalue())
        if out != src:
            os.remove(src)
            x["file"] = os.path.relpath(out, ROOT)
        if not x.get("desc"):
            info = describe(buf.getvalue())
            if info:
                x.update({k: info.get(k) for k in ("desc", "place", "landmark", "time", "mood", "faces", "text_visible", "quality", "themes", "ideas")})
                print("described", x["file"], "|", info.get("desc"))
        changed += 1
    json.dump(inbox, open(IP, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("processed", changed, "total", len(inbox), "unused", sum(1 for x in inbox if not x.get("used")))


if __name__ == "__main__":
    main()
