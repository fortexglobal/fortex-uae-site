"""Тест: фото «как с айфона» (стиль lifestyle-блогеров в Threads) с героем бренда, по нашей теме. -> research/photo/
Модели: flash (дёшево) и pro (дороже, реалистичнее), для сравнения."""
import base64, json, os, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "research", "photo")
KEY = os.environ["OPENROUTER_API_KEY"]
H = json.load(open(os.path.join(ROOT, "ig", "heroes", "heroes.json")))
LOOK = ("Candid lifestyle photo shot on an iPhone 15 Pro main camera by a friend, not a studio shoot, natural available light, "
        "slightly muted realistic colors, true-to-life skin texture with pores, imperfect framing, a bit of motion and depth, "
        "real-world clutter in the background, no beauty retouching, no cinematic color grading, no bokeh exaggeration, "
        "vertical 4:5 composition, Dubai, no text, no logos, no brand names, no watermarks. Scene: ")
SCENES = [
    (None, "a cafe table by a window in Dubai Design District: flat white with latte art, a passport in a leather cover, a phone face down, sunglasses, morning light and a blurred street outside"),
    (None, "view from a high-floor office window in DIFC at late afternoon, glass towers and the Sheikh Zayed Road below, a laptop and a printed document on the desk in the foreground"),
    (None, "Dubai Marina promenade early morning, yachts in the water, towers in soft haze, wet pavement after cleaning, a few people far away walking, shot at eye level"),
    (None, "a hand holding a new dark bank card above a marble table next to a coffee and car keys, Dubai apartment with a balcony view, natural light, no logos on the card"),
    (None, "inside a quiet modern Dubai metro carriage at sunset, golden light through the windows, city towers passing, a couple of passengers far away seen from behind"),
]


def gen(model, hero, scene):
    content = [{"type": "text", "text": LOOK.replace("Candid lifestyle photo", "Candid photo") + scene + ". No close-up people, no faces."}]
    body = json.dumps({"model": model, "modalities": ["image", "text"], "image_config": {"aspect_ratio": "4:5"},
                       "messages": [{"role": "user", "content": content}]}).encode()
    r = json.load(urllib.request.urlopen(urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", body,
                                                                {"Authorization": "Bearer " + KEY, "Content-Type": "application/json"}), timeout=240))
    return base64.b64decode(r["choices"][0]["message"]["images"][0]["image_url"]["url"].split(",", 1)[1])


os.makedirs(OUT, exist_ok=True)
for k, (hero, sc) in enumerate(SCENES):
    for tag, m in (("flash", "google/gemini-2.5-flash-image"), ("pro", "google/gemini-3-pro-image-preview")):
        if tag == "flash":
            continue
        try:
            open(os.path.join(OUT, f"{k}-{tag}.jpg"), "wb").write(gen(m, hero, sc)); print(k, tag, "ok")
        except Exception as e:
            print(k, tag, "error", str(e)[:200])
