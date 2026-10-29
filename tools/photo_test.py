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
    ("man", "he sits at a small wooden table in a stylish cafe in Dubai Design District, flat white with latte art, phone and sunglasses on the table, looks to the side out of the window, late morning light"),
    ("man", "he walks out of a glass office tower in DIFC carrying a thin leather folder, mid-step, shot from across the street, afternoon sun, palm trees and taxis"),
    ("woman", "she walks through Dubai International Airport arrivals hall pulling a cabin suitcase, holding a phone, shot from slightly behind and to the side, morning"),
    ("man", "he sits on a terrace in Dubai Marina at golden hour with a laptop open and a glass of water, yachts behind, relaxed, looking at the screen"),
]


def gen(model, hero, scene):
    h = H[hero]
    ref = base64.b64encode(open(os.path.join(ROOT, h["file"]), "rb").read()).decode()
    content = [{"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + ref}},
               {"type": "text", "text": "Keep exactly the same person as in the reference photo (same face, hair, age, build): " + h["desc"] + ". " + LOOK + scene}]
    body = json.dumps({"model": model, "modalities": ["image", "text"], "image_config": {"aspect_ratio": "4:5"},
                       "messages": [{"role": "user", "content": content}]}).encode()
    r = json.load(urllib.request.urlopen(urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", body,
                                                                {"Authorization": "Bearer " + KEY, "Content-Type": "application/json"}), timeout=240))
    return base64.b64decode(r["choices"][0]["message"]["images"][0]["image_url"]["url"].split(",", 1)[1])


os.makedirs(OUT, exist_ok=True)
for k, (hero, sc) in enumerate(SCENES):
    for tag, m in (("flash", "google/gemini-2.5-flash-image"), ("pro", "google/gemini-3-pro-image-preview")):
        if tag == "pro" and k > 1:
            continue
        try:
            open(os.path.join(OUT, f"{k}-{tag}.jpg"), "wb").write(gen(m, hero, sc)); print(k, tag, "ok")
        except Exception as e:
            print(k, tag, "error", str(e)[:200])
