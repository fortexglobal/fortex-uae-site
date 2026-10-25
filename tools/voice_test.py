"""Пробная озвучка: voice/src/<slug>.json -> voice/out/<slug>/<голос>_<n>.mp3 (ElevenLabs). Ничего не публикует."""
import glob, json, os, urllib.request

KEY = os.environ.get("ELEVENLABS_API_KEY", "")


def tts(text, vid, speed, out):
    req = urllib.request.Request(
        f"https://api.elevenlabs.io/v1/text-to-speech/{vid}?output_format=mp3_44100_192",
        data=json.dumps({"text": text, "model_id": "eleven_multilingual_v2", "seed": 7,
                         "voice_settings": {"stability": 0.4, "similarity_boost": 0.8, "style": 0.3,
                                            "use_speaker_boost": True, "speed": speed}}).encode(),
        headers={"xi-api-key": KEY, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r, open(out, "wb") as f:
        f.write(r.read())


for src in glob.glob("voice/src/*.json"):
    slug = os.path.splitext(os.path.basename(src))[0]
    cfg = json.load(open(src))
    od = f"voice/out/{slug}"
    os.makedirs(od, exist_ok=True)
    for name, vid in cfg["voices"].items():
        for i, line in enumerate(cfg["lines"], 1):
            out = f"{od}/{name}_{i}.mp3"
            if os.path.exists(out):
                continue
            try:
                tts(line, vid, cfg.get("speed", 1.1), out)
                print("ok", out)
            except Exception as e:
                print("fail", out, getattr(e, "code", ""), str(e)[:200])
