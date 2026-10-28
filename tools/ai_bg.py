"""Фон для обложки от нейросети через OpenRouter (запускается в GitHub Actions).
Берёт covers/requests/<slug>.json ({"prompt": "..."}), для которых ещё нет covers/bg/<slug>.jpg,
и сохраняет картинку. Ключ: переменная окружения OPENROUTER_API_KEY.
"""
import base64, glob, json, os, sys, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KEY = os.environ.get("OPENROUTER_API_KEY", "")
MODELS = ["google/gemini-2.5-flash-image", "google/gemini-3-pro-image-preview", "google/gemini-2.5-flash-image"]
STYLE = ("Photorealistic editorial photo, cinematic soft light, shallow depth of field, calm premium mood, "
         "muted teal and navy tones with warm highlights, no text, no letters, no logos, no watermarks, "
         "no recognizable people or faces, vertical composition with empty space for a headline. Subject: ")


def _log(msg):
    print(msg)
    os.makedirs(os.path.join(ROOT, "covers"), exist_ok=True)
    with open(os.path.join(ROOT, "covers", "last_errors.txt"), "a", encoding="utf-8") as f:
        f.write(msg + "\n")


COVER_MODELS = ["google/gemini-3-pro-image-preview", "google/gemini-2.5-flash-image"]  # обложка: лучшее качество
PHOTO_MODELS = ["google/gemini-2.5-flash-image"]                                      # фото внутри: дёшево


HEROES = json.load(open(os.path.join(ROOT, "ig", "heroes", "heroes.json"))) if os.path.exists(os.path.join(ROOT, "ig", "heroes", "heroes.json")) else {}


def gen(prompt, cover=False, hero=None):
    """hero: "man" или "woman" — постоянный герой бренда (ig/heroes), подаётся как образец, чтобы лицо было тем же."""
    for m in (COVER_MODELS if cover else PHOTO_MODELS):
        if hero and hero in HEROES:
            ref = base64.b64encode(open(os.path.join(ROOT, HEROES[hero]["file"]), "rb").read()).decode()
            style = STYLE.replace("no recognizable people or faces, ", "")
            content = [{"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + ref}},
                       {"type": "text", "text": "Keep exactly the same person as in the reference photo (same face, hair, age, build): "
                        + HEROES[hero]["desc"] + ". " + style + prompt}]
        else:
            content = STYLE + prompt
        body = json.dumps({"model": m, "modalities": ["image", "text"],
                           "messages": [{"role": "user", "content": content}]}).encode()
        req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", body, {
            "Authorization": f"Bearer {KEY}", "Content-Type": "application/json",
            "HTTP-Referer": "https://fortex-uae.com", "X-Title": "Fortex covers"})
        try:
            r = json.load(urllib.request.urlopen(req, timeout=180))
            if "choices" not in r:
                _log(f"{m} bad response: {str(r)[:400]}")
                continue
            imgs = r["choices"][0]["message"].get("images") or []
            if imgs:
                url = imgs[0]["image_url"]["url"]
                return base64.b64decode(url.split(",", 1)[1])
            _log(f"{m} no image: {str(r)[:400]}")
        except Exception as e:
            _log(f"{m} error: {getattr(e, 'read', lambda: b'')()[:400] or e}")
    return None


def main():
    if not KEY:
        sys.exit("OPENROUTER_API_KEY не задан")
    done = 0
    for f in sorted(glob.glob(os.path.join(ROOT, "covers", "requests", "*.json"))):
        slug = os.path.basename(f)[:-5]
        out = os.path.join(ROOT, "covers", "bg", slug + ".jpg")
        if os.path.exists(out):
            continue
        data = gen(json.load(open(f, encoding="utf-8"))["prompt"])
        if data:
            os.makedirs(os.path.dirname(out), exist_ok=True)
            open(out, "wb").write(data); done += 1; print("ok", slug)
        else:
            print("fail", slug)
    print("generated", done)


if __name__ == "__main__":
    main()
