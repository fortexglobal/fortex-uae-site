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


def http(url, data=None, headers=None, timeout=300):
    req = urllib.request.Request(url, json.dumps(data).encode() if data is not None else None,
                                 {"Content-Type": "application/json", **(headers or {})})
    return json.load(urllib.request.urlopen(req, timeout=timeout))


def img():
    key = os.environ["OPENROUTER_API_KEY"]
    os.makedirs(OUT, exist_ok=True)
    for k, sc in enumerate(SCENES):
        try:
            r = http("https://openrouter.ai/api/v1/chat/completions",
                     {"model": "google/gemini-2.5-flash-image", "modalities": ["image", "text"],
                      "image_config": {"aspect_ratio": "9:16"},
                      "messages": [{"role": "user", "content": STYLE + sc}]},
                     {"Authorization": f"Bearer {key}"})
            url = r["choices"][0]["message"]["images"][0]["image_url"]["url"]
            open(os.path.join(OUT, f"img-{k}.jpg"), "wb").write(base64.b64decode(url.split(",", 1)[1]))
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


if __name__ == "__main__":
    if sys.argv[1] == "img":
        img()
    else:
        vid([int(x) for x in sys.argv[2].split(",")])
