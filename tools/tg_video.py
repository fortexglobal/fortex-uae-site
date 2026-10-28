"""Отправка рилса Александру в Telegram правильно: вертикальное превью 9:16 (width/height/duration + миниатюра до 320 px).
Без width/height Telegram показывает ролик квадратом и «растянутым».
python3 tools/tg_video.py <slug> "<подпись>" [--approve]   (--approve: кнопки ✅ Утверждаю / ✏️ Доработать для рилса со status wait)
Токен бота: переменная TG_BOT_TOKEN или аргумент --token=..., chat_id 5887750248."""
import io, json, os, subprocess, sys, urllib.request, uuid
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = [a for a in sys.argv[1:] if a.startswith("--")]
    slug, cap = args[0], args[1]
    token = next((f.split("=", 1)[1] for f in flags if f.startswith("--token=")), os.environ.get("TG_BOT_TOKEN"))
    d = os.path.join(ROOT, "ig", "reels", slug)
    m = json.load(open(os.path.join(d, "render.json")))
    vid = os.path.join(d, m["video"])
    w, h = [int(x) for x in subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                                           "-of", "csv=p=0", vid], capture_output=True, text=True).stdout.strip().split(",")]
    im = Image.open(os.path.join(d, "cover.jpg")).convert("RGB"); im.thumbnail((180, 320))
    th = io.BytesIO(); im.save(th, "JPEG", quality=85)
    b = uuid.uuid4().hex
    f = lambda n, v: (f"--{b}\r\nContent-Disposition: form-data; name=\"{n}\"\r\n\r\n{v}\r\n").encode()
    fl = lambda n, name, data, ct: (f"--{b}\r\nContent-Disposition: form-data; name=\"{n}\"; filename=\"{name}\"\r\nContent-Type: {ct}\r\n\r\n").encode() + data + b"\r\n"
    body = f("chat_id", "5887750248") + f("caption", cap[:1024]) + f("supports_streaming", "true") + f("width", w) + f("height", h) + f("duration", int(m.get("duration", 0)))
    if "--approve" in flags:
        body += f("reply_markup", json.dumps({"inline_keyboard": [[{"text": "✅ Утверждаю", "callback_data": f"crlok:{slug}"[:64]},
                                                                   {"text": "✏️ Доработать", "callback_data": f"crlfix:{slug}"[:64]}]]}))
    body += fl("video", m["video"], open(vid, "rb").read(), "video/mp4") + fl("thumbnail", "th.jpg", th.getvalue(), "image/jpeg") + f"--{b}--\r\n".encode()
    r = json.load(urllib.request.urlopen(urllib.request.Request(f"https://api.telegram.org/bot{token}/sendVideo", body,
                                                                {"Content-Type": f"multipart/form-data; boundary={b}"}), timeout=300))
    v = r["result"]["video"]
    print("ok", v["width"], v["height"], v["duration"])


if __name__ == "__main__":
    main()
