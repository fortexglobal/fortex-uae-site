"""Пробный «Дубай-фантазия» без больших трат.
stage=img: 4 картинки (Gemini image через OpenRouter, ~4 цента каждая) -> research/fantasy/img-<k>.jpg
stage=vid: оживляем выбранные картинки (Kling 2.5 turbo image-to-video, 5 с, ~35 центов) и склеиваем -> research/fantasy/test.mp4
"""
import base64, json, os, subprocess, sys, time, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "research", "fantasy")
STYLE = ("Ultra photorealistic vertical 9:16 smartphone-style documentary photo, hazy warm Dubai golden hour, cinematic, "
         "real people in the foreground for scale, natural skin, no text, no logos, no watermarks. Scene: ")
SCENES = [
    "a gigantic camel the size of a skyscraper walks slowly between the glass towers of Downtown Dubai at sunrise, tiny cars on Sheikh Zayed Road below, people on a footbridge in the foreground filming it on their phones",
    "a giant flamingo taller than the buildings wades through Dubai Marina canal, people at cafe tables on the promenade in the foreground look up in amazement and take photos",
    "a colossal Arabian oryx stands inside the golden Dubai Frame like a picture, families in Zabeel Park in the foreground point at it and film",
    "a huge desert fennec fox peeks over the dunes behind a luxury desert resort pool, guests at breakfast tables in the foreground turn around in shock",
]


SCENES_TOPIC = [
    "a gigantic glowing golden bank card the size of a skyscraper stands upright between the towers of Downtown Dubai at golden hour like a monument, people on the boulevard in the foreground stop and film it on their phones",
    "a colossal burgundy passport floats slowly above Dubai Marina like an airship, its pages gently opening, people on yachts and the promenade below look up and take photos",
    "an enormous round steel bank vault door slowly opens in the middle of the golden desert dunes outside Dubai, warm light pours out, a small group of business people in the foreground walks toward it",
    "a whole glass office tower flies like an airplane over the Persian Gulf toward the Dubai skyline at sunset, people on Palm Jumeirah beach in the foreground point at it in amazement",
]


HERO = ("a Russian-looking businessman around 38 years old, short dark hair with light stubble, white linen shirt, navy chinos, "
        "brown leather watch, calm confident face")
STORY = [
    "arrives at Dubai International Airport arrivals hall, pulling a carry-on suitcase, looking around, shot from the side at medium distance",
    "sits in a government service center in Dubai at a biometrics counter, presses his fingers on a glowing fingerprint scanner while an officer at the desk looks at a monitor, close-medium shot focusing on hands and scanner, his face in three-quarter view",
    "in a modern premium bank office in Dubai with a view of skyscrapers, a smiling bank manager hands him a new dark bank card across the desk, he takes it and smiles, medium shot",
]
REAL = ("Ultra photorealistic vertical 9:16 photo shot on a modern smartphone, natural light, real skin texture, documentary style, "
        "candid moment, Dubai, no text, no logos, no brand names, no watermarks. ")


def http(url, data=None, headers=None, timeout=300):
    req = urllib.request.Request(url, json.dumps(data).encode() if data is not None else None,
                                 {"Content-Type": "application/json", **(headers or {})})
    return json.load(urllib.request.urlopen(req, timeout=timeout))


def img(scenes=None, prefix="img"):
    key = os.environ["OPENROUTER_API_KEY"]
    os.makedirs(OUT, exist_ok=True)
    for k, sc in enumerate(scenes or SCENES):
        try:
            r = http("https://openrouter.ai/api/v1/chat/completions",
                     {"model": "google/gemini-2.5-flash-image", "modalities": ["image", "text"],
                      "image_config": {"aspect_ratio": "9:16"},
                      "messages": [{"role": "user", "content": STYLE + sc}]},
                     {"Authorization": f"Bearer {key}"})
            url = r["choices"][0]["message"]["images"][0]["image_url"]["url"]
            open(os.path.join(OUT, f"{prefix}-{k}.jpg"), "wb").write(base64.b64decode(url.split(",", 1)[1]))
            print("img", k, "ok")
        except Exception as e:
            print("img", k, "error", e)


def vid(which):
    key = os.environ["FAL_KEY"]
    hd = {"Authorization": f"Key {key}"}
    parts = []
    moves = ["slow cinematic push-in, the giant animal moves slowly and naturally, people in foreground react and film, handheld documentary camera",
             "the giant animal turns its head and steps forward slowly, crowd in foreground looks up, gentle handheld camera drift"]
    for n, k in enumerate(which):
        p = os.path.join(OUT, f"img-{k}.jpg")
        uri = "data:image/jpeg;base64," + base64.b64encode(open(p, "rb").read()).decode()
        q = http("https://queue.fal.run/fal-ai/kling-video/v2.5-turbo/pro/image-to-video",
                 {"prompt": moves[n % 2], "image_url": uri, "duration": "5", "negative_prompt": "blur, distortion, text, watermark", "cfg_scale": 0.5}, hd)
        t0 = time.time()
        while time.time() - t0 < 900:
            time.sleep(8)
            st = http(q["status_url"], headers=hd)
            if st.get("status") == "COMPLETED":
                break
        res = http(q["response_url"], headers=hd)
        out = os.path.join(OUT, f"clip-{k}.mp4")
        urllib.request.urlretrieve(res["video"]["url"], out)
        parts.append(out)
        print("clip", k, "ok")
    lst = os.path.join(OUT, "list.txt")
    open(lst, "w").write("".join(f"file '{x}'\n" for x in parts))
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c:v", "libx264", "-crf", "20",
                    "-pix_fmt", "yuv420p", "-an", os.path.join(OUT, "test.mp4")], check=True)
    os.remove(lst)


def story():
    """Герой + 2 сцены с тем же героем (картинка героя подаётся как образец) и оживление этих 2 сцен."""
    key = os.environ["OPENROUTER_API_KEY"]
    os.makedirs(OUT, exist_ok=True)

    def gen(prompt, ref=None):
        content = [{"type": "text", "text": prompt}]
        if ref:
            content.insert(0, {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(open(ref, "rb").read()).decode()}})
            content[1]["text"] = "Keep exactly the same man as in the reference photo (same face, hair, clothes). " + prompt
        r = http("https://openrouter.ai/api/v1/chat/completions",
                 {"model": "google/gemini-2.5-flash-image", "modalities": ["image", "text"], "image_config": {"aspect_ratio": "9:16"},
                  "messages": [{"role": "user", "content": content}]}, {"Authorization": f"Bearer {key}"})
        return base64.b64decode(r["choices"][0]["message"]["images"][0]["image_url"]["url"].split(",", 1)[1])

    hero = os.path.join(OUT, "story-0.jpg")
    open(hero, "wb").write(gen(REAL + "The man: " + HERO + ". He " + STORY[0]))
    print("hero ok")
    for k in (1, 2):
        open(os.path.join(OUT, f"story-{k}.jpg"), "wb").write(gen(REAL + "He " + STORY[k], hero))
        print("scene", k, "ok")
    # оживляем сцены 1 и 2
    global SCENE_MOVES
    hd = {"Authorization": f"Key {os.environ['FAL_KEY']}"}
    moves = {1: "he presses his fingers on the scanner, the scanner light flickers green, the officer nods, subtle natural movement, handheld camera",
             2: "the manager hands over the bank card, he takes it, looks at it and smiles, natural subtle movement, slow push-in"}
    parts = []
    for k in (1, 2):
        uri = "data:image/jpeg;base64," + base64.b64encode(open(os.path.join(OUT, f"story-{k}.jpg"), "rb").read()).decode()
        q = http("https://queue.fal.run/fal-ai/kling-video/v2.5-turbo/pro/image-to-video",
                 {"prompt": moves[k], "image_url": uri, "duration": "5", "negative_prompt": "blur, distortion, extra fingers, text, watermark", "cfg_scale": 0.5}, hd)
        t0 = time.time()
        while time.time() - t0 < 900:
            time.sleep(8)
            if http(q["status_url"], headers=hd).get("status") == "COMPLETED":
                break
        out = os.path.join(OUT, f"story-clip-{k}.mp4")
        urllib.request.urlretrieve(http(q["response_url"], headers=hd)["video"]["url"], out)
        parts.append(out)
        print("clip", k, "ok")
    lst = os.path.join(OUT, "list.txt")
    open(lst, "w").write("".join(f"file '{x}'\n" for x in parts))
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c:v", "libx264", "-crf", "20",
                    "-pix_fmt", "yuv420p", "-an", os.path.join(OUT, "story.mp4")], check=True)
    os.remove(lst)


if __name__ == "__main__":
    if sys.argv[1] == "img":
        img()
    elif sys.argv[1] == "story":
        story()
    elif sys.argv[1] == "topic":
        img(SCENES_TOPIC, "topic")
    else:
        vid([int(x) for x in sys.argv[2].split(",")])
