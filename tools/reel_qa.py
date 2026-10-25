"""Самопроверка готового рилса перед отправкой Александру.

python3 tools/reel_qa.py ig/reels/<slug>/<hash>.mp4  [папка_вывода]

Делает в <папка>/ (по умолчанию ig/reels/<slug>/qa/):
- sheet-1.jpg, sheet-2.jpg ...: кадры каждые 0,25 с с рамкой сейф-зоны Instagram (зелёная) и зоной кнопок (красная);
- cuts.jpg: каждая склейка, 3 кадра до и 3 после;
- в результате: громкость (LUFS, true peak), есть ли тишина посреди ролика, пути к листам.
Смотреть листы глазами (Read): текст не вылезает за зелёную рамку, не закрывает лица, слова не обрезаны на склейках.
"""
import json, os, re, subprocess, sys, tempfile

W, H = 1080, 1920
SAFE_TOP = (70, 210, 995, 1065)       # x0, y0, x1, y1
SAFE_BOTTOM = (70, 1065, 910, 1485)
TW, TH, COLS, ROWS = 180, 320, 10, 4  # миниатюры и сетка листа


def ff(args):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error"] + args, check=True)


def dur(p):
    o = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", p],
                       capture_output=True, text=True).stdout.strip()
    return float(o or 0)


def fps(p):
    o = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=r_frame_rate",
                        "-of", "default=nw=1:nk=1", p], capture_output=True, text=True).stdout.strip()
    try:
        a, b = o.split("/")
        return float(a) / float(b)
    except Exception:
        return 30.0


def thumb(img, label):
    from PIL import ImageDraw
    img = img.resize((TW, TH))
    d = ImageDraw.Draw(img)
    sx, sy = TW / W, TH / H
    for (x0, y0, x1, y1), c in ((SAFE_TOP, (40, 220, 90)), (SAFE_BOTTOM, (40, 220, 90))):
        d.rectangle([x0 * sx, y0 * sy, x1 * sx, y1 * sy], outline=c, width=1)
    d.rectangle([910 * sx, 1065 * sy, TW - 1, 1700 * sy], outline=(230, 50, 50), width=1)  # кнопки справа
    d.rectangle([0, 1485 * sy, TW - 1, TH - 1], outline=(230, 50, 50), width=1)           # подпись внизу
    d.rectangle([0, 0, 62, 14], fill=(0, 0, 0))
    d.text((3, 1), label, fill=(255, 255, 255))
    return img


def frames_at(video, times, tmp):
    from PIL import Image
    out = []
    for i, t in enumerate(times):
        p = os.path.join(tmp, f"f{i:04d}.jpg")
        try:
            ff(["-ss", f"{max(0, t):.3f}", "-i", video, "-frames:v", "1", "-vf", f"scale={W}:{H}", "-q:v", "4", p])
            out.append((t, Image.open(p).convert("RGB")))
        except Exception:
            pass
    return out


def sheet(items, path, cols=COLS):
    from PIL import Image
    rows = (len(items) + cols - 1) // cols
    canvas = Image.new("RGB", (cols * TW + (cols + 1) * 4, rows * TH + (rows + 1) * 4), (20, 20, 20))
    for k, (label, img) in enumerate(items):
        r, c = divmod(k, cols)
        canvas.paste(thumb(img, label), (4 + c * (TW + 4), 4 + r * (TH + 4)))
    canvas.save(path, "JPEG", quality=82)


def loudness(video):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", video, "-af", "loudnorm=I=-14:TP=-1:print_format=json", "-f", "null", "-"],
                       capture_output=True, text=True).stderr
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", r, re.S)
    if not m:
        return {}
    j = json.loads(m.group(0))
    return {"lufs": float(j["input_i"]), "true_peak": float(j["input_tp"]), "lra": float(j["input_lra"])}


def normalize(video, target=-13.4, tp=-1.6):
    """Второй проход по замеру: ровно -14 LUFS и пик с запасом (AAC добавляет до 1 дБ). Видео не перекодируется."""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", video, "-af", f"loudnorm=I={target}:TP={tp}:LRA=11:print_format=json",
                        "-f", "null", "-"], capture_output=True, text=True).stderr
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", r, re.S)
    if not m:
        return False
    j = json.loads(m.group(0))
    if j["input_i"] in ("-inf", "inf"):
        return False
    tmp = video + ".norm.mp4"
    af = (f"loudnorm=I={target}:TP={tp}:LRA=11:measured_I={j['input_i']}:measured_TP={j['input_tp']}:"
          f"measured_LRA={j['input_lra']}:measured_thresh={j['input_thresh']}:offset={j['target_offset']}:linear=true,"
          f"alimiter=limit=0.79:attack=2:release=60:level=disabled")
    ff(["-i", video, "-map", "0:v", "-map", "0:a", "-c:v", "copy", "-af", af, "-ar", "44100",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", tmp])
    os.replace(tmp, video)
    return True


def silences(video, total):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", video, "-af", "silencedetect=noise=-38dB:d=0.6", "-f", "null", "-"],
                       capture_output=True, text=True).stderr
    st = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", r)]
    return [round(t, 2) for t in st if 0.5 < t < total - 1.5]


def run(video, out_dir=None, cuts=()):
    out_dir = out_dir or os.path.join(os.path.dirname(video), "qa")
    os.makedirs(out_dir, exist_ok=True)
    for old in os.listdir(out_dir):
        if old.endswith(".jpg"):
            os.remove(os.path.join(out_dir, old))
    total, rate = dur(video), fps(video)
    tmp = tempfile.mkdtemp()
    times = [round(i * 0.25, 2) for i in range(int(total / 0.25) + 1)]
    fr = frames_at(video, times, tmp)
    per = COLS * ROWS
    sheets = []
    for k in range(0, len(fr), per):
        p = os.path.join(out_dir, f"sheet-{k // per + 1}.jpg")
        sheet([(f"{t:.2f}s", im) for t, im in fr[k:k + per]], p)
        sheets.append(os.path.relpath(p, os.path.dirname(out_dir)))
    res = {"duration": round(total, 2), "sheets": sheets}
    if cuts:
        items = []
        for c in cuts:
            ts = [c + d / rate for d in range(-3, 4)]
            for t, im in frames_at(video, ts, tmp):
                items.append((f"{t:.2f}s", im))
        p = os.path.join(out_dir, "cuts.jpg")
        sheet(items, p, cols=7)
        res["cuts"] = os.path.relpath(p, os.path.dirname(out_dir))
    lo = loudness(video)
    res.update(lo)
    res["silence_mid"] = silences(video, total)
    warn = []
    if lo and abs(lo["lufs"] + 14) > 1.5:
        warn.append(f"громкость {lo['lufs']} LUFS, нужно около -14")
    if lo and lo["true_peak"] > -1.0:
        warn.append(f"пик {lo['true_peak']} dBTP, нужно не выше -1")
    if res["silence_mid"]:
        warn.append(f"тишина посреди ролика: {res['silence_mid']}")
    res["warnings"] = warn
    json.dump(res, open(os.path.join(out_dir, "qa.json"), "w"), ensure_ascii=False, indent=1)
    return res


if __name__ == "__main__":
    print(json.dumps(run(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None), ensure_ascii=False, indent=1))
