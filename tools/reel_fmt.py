"""Рилсы без голоса: живые стоковые кадры (Pexels) под бит музыки + текст поверх.

Форматы (поле "format" в ig/reels/src/<slug>.json, "v": 2):

vibe   — одна фраза-мем сверху, 8–12 красивых кадров быстро под бит.
  {"format": "vibe", "text": "Сначала ты приезжаешь в Дубай, а потом все остальные города кажутся обычными",
   "clips": ["dubai fountain night", "burj khalifa lights", ...], "music": "...", "caption": "..."}

event  — событие: крупно название, ниже даты и место; в конце «Подробности в описании».
  {"format": "event", "title": "DUBAI FASHION WEEK", "sub": "22-26 октября, d3", "clips": [...], "music": "...", "caption": "..."}

pov    — диалог-мем из двух частей, смена текста на сильную долю.
  {"format": "pov", "setup": "Друг: там вышел новый айфон, тоже такой хочешь?", "punch": "Единственная карта, которую я хочу:",
   "clips_setup": [...], "clips_punch": [...], "music": "...", "caption": "..."}

Клип: строка (поисковый запрос Pexels, по-английски) или {"q": "...", "prompt": "<англ. сцена для Kling, если на Pexels ничего нет>"}.
Ключи: PEXELS_API_KEY или PIXABAY_API_KEY (видео), ELEVENLABS_API_KEY (музыка), FAL_KEY (запасной AI-клип).
"""
import json, os, random, subprocess, tempfile, urllib.parse

import numpy as np

import reel_v2 as R

W, H, FPS = R.W, R.H, R.FPS
PEXELS_KEY = os.environ.get("PEXELS_API_KEY", "")
PIXABAY_KEY = os.environ.get("PIXABAY_API_KEY", "")
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}
USED_P = os.path.join(R.ROOT, "ig", "reels", "stock_used.json")


# ---------- стоковые видео ----------
def pexels_pick(query, used, min_secs):
    hd = {"Authorization": PEXELS_KEY, "User-Agent": "fortex-reels/1.0"}
    q = urllib.parse.quote(query)
    best = None
    for orient in ("portrait", None):
        url = f"https://api.pexels.com/videos/search?query={q}&per_page=30&size=medium" + (f"&orientation={orient}" if orient else "")
        try:
            res = R.http(url, headers=hd, timeout=60)
        except Exception as e:
            R.log("pexels", query, e)
            return None
        for v in res.get("videos", []):
            if str(v["id"]) in used or v.get("duration", 0) < min_secs:
                continue
            files = [f for f in v.get("video_files", []) if f.get("width") and f.get("height")]
            port = [f for f in files if f["height"] >= f["width"] and f["height"] >= 1280]
            pool = port or ([f for f in files if f["height"] >= 1080] if orient is None else [])
            if not pool:
                continue
            f = sorted(pool, key=lambda f: abs(f["height"] - 1920))[0]
            best = (str(v["id"]), f["link"], v.get("user", {}).get("name", ""))
            break
        if best:
            return best
    return None


STOP = {"in", "of", "the", "a", "at", "and", "with", "on", "view", "night", "day", "shot", "video"}
DUBAI_TAGS = ("dubai", "uae", "emirates", "burj", "abu dhabi", "arab")


DUBAI_ONLY = {"on": False}
LANDMARKS = ("palm", "jumeirah", "marina", "burj", "khalifa", "jbr", "difc", "creek", "frame")


def relevant(tags, query):
    t = tags.lower()
    words = [w for w in query.lower().replace(",", " ").split() if w not in STOP and len(w) > 2]
    need_dubai = DUBAI_ONLY["on"] or "dubai" in query.lower() or "uae" in query.lower() or any(l in query.lower() for l in LANDMARKS)
    if need_dubai and not any(d in t for d in DUBAI_TAGS):
        return -1
    other = [w for w in words if w not in ("dubai", "uae")]
    hits = sum(1 for w in other if w.rstrip("s") in t)
    need_hits = 2 if len(other) >= 3 else (1 if other else 0)
    if hits < need_hits and not (need_dubai and hits >= 1):
        return -1
    return hits


def pixabay_pick(query, used, min_secs):
    q = urllib.parse.quote(query)
    try:
        res = R.http(f"https://pixabay.com/api/videos/?key={PIXABAY_KEY}&q={q}&per_page=80&safesearch=true", headers=UA, timeout=60)
    except Exception as e:
        R.log("pixabay", query, e)
        return None
    cands = []
    for rank, v in enumerate(res.get("hits", [])):
        if f"px{v['id']}" in used or v.get("duration", 0) < min_secs:
            continue
        rel = relevant(v.get("tags", ""), query)
        if rel < 0:
            continue
        files = [f for f in (v.get("videos") or {}).values() if f and f.get("url") and f.get("height")]
        port = [f for f in files if f["height"] >= f["width"] and f["height"] >= 1280]
        land = [f for f in files if f["height"] >= 1080]
        pool = port or land
        if not pool:
            continue
        f = sorted(pool, key=lambda f: -f["height"])[0]
        cands.append((-rel, 0 if port else 1, rank, f"px{v['id']}", f["url"], v.get("user", ""), v.get("tags", "")))
    if not cands:
        return None
    cands.sort()
    c = cands[0]
    return c[3], c[4], f"{c[5]} [{c[6][:40]}]"


AI_BUDGET = {"left": 4}


def get_clip(item, path, used, min_secs, idx):
    q = item if isinstance(item, str) else item.get("q", "")
    prompt = None if isinstance(item, str) else item.get("prompt")
    if R.DRY:
        R.ff(["-f", "lavfi", "-i", f"testsrc2=size=1080x1920:rate=30:duration=6", "-vf", f"hue=h={idx * 47}", "-pix_fmt", "yuv420p", path])
        return "dry", "dry"
    if PEXELS_KEY and q:
        for attempt in (q, q.split(",")[0] + " dubai" if "dubai" not in q.lower() else None):
            if not attempt:
                continue
            got = pexels_pick(attempt, used, min_secs)
            if got:
                vid, link, author = got
                open(path, "wb").write(R.http(link, raw=True, timeout=300))
                used[vid] = 1
                R.log(f"clip {idx}: pexels {vid} ({author}) «{attempt}»")
                return f"pexels:{vid}", author
    if PIXABAY_KEY and q:
        for attempt in (q,):
            got = pixabay_pick(attempt, used, min_secs)
            if got:
                vid, link, author = got
                open(path, "wb").write(R.http(link, headers=UA, raw=True, timeout=300))
                used[vid] = 1
                R.log(f"clip {idx}: pixabay {vid} ({author}) «{attempt}»")
                return f"pixabay:{vid}", author
    if R.FAL_KEY and AI_BUDGET["left"] > 0:
        AI_BUDGET["left"] -= 1
        p = prompt or f"{q}, in Dubai UAE, cinematic vertical video, realistic, premium lifestyle, natural motion"
        url = R.gen_clip(p, 5, path, idx)
        return url, "ai"
    raise RuntimeError(f"нет клипа для «{q}»")


# ---------- бит ----------
def beats_of(mp3):
    """Простой бит-трекер: огибающая атак → темп по автокорреляции → фаза. Возвращает (темп, [время долей])."""
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", mp3, "-ac", "1", "-ar", "22050", "-f", "f32le", "-"], capture_output=True).stdout
    y = np.frombuffer(raw, dtype=np.float32)
    if len(y) < 22050 * 3:
        return 120.0, list(np.arange(0, 60, 0.5))
    n, hop = 1024, 512
    frames = np.lib.stride_tricks.sliding_window_view(y, n)[::hop] * np.hanning(n)
    mag = np.log1p(10 * np.abs(np.fft.rfft(frames, axis=1)))
    flux = np.maximum(0, np.diff(mag, axis=0)).sum(axis=1)
    flux = (flux - flux.mean()) / (flux.std() + 1e-9)
    sr_env = 22050 / hop
    lags = np.arange(int(sr_env * 60 / 180), int(sr_env * 60 / 70) + 1)
    ac = np.array([np.dot(flux[:-l], flux[l:]) for l in lags])
    bpm_of = 60 * sr_env / lags
    ac = ac * np.exp(-0.5 * (np.log2(bpm_of / 120) / 0.9) ** 2)
    lag = int(lags[np.argmax(ac)])
    phase = int(np.argmax([flux[p::lag].sum() for p in range(lag)]))
    times = [(phase + k * lag) / sr_env for k in range(int((len(flux) - phase) / lag))]
    return 60 * sr_env / lag, times


def cut_points(beat_times, period, n_clips, target, first_len=None):
    """Точки смены кадров по долям: шаг 2 доли (или 1/4 при медленном темпе), чтобы клип был ~0.8–1.6 с."""
    k = max(1, int(round(1.15 / period)))
    grid = [t for t in beat_times[::k]]
    if not grid or grid[0] > 0.6:
        grid = [0.0] + grid
    grid[0] = 0.0
    if len(grid) < n_clips + 1:
        step = target / n_clips
        return [i * step for i in range(n_clips + 1)]
    return grid[:n_clips + 1]


# ---------- обложка ----------
def best_cover(video, t_from, t_to, out_jpg):
    from PIL import Image, ImageFilter, ImageStat
    best, best_t = -1, t_from + 0.5
    tmp = tempfile.mkdtemp()
    t = t_from + 0.3
    while t < t_to - 0.2:
        p = os.path.join(tmp, "f.jpg")
        R.ff(["-ss", f"{t:.2f}", "-i", video, "-frames:v", "1", "-vf", "scale=270:-2", p])
        im = Image.open(p).convert("RGB")
        sharp = ImageStat.Stat(im.convert("L").filter(ImageFilter.FIND_EDGES)).var[0]
        sat = ImageStat.Stat(im.convert("HSV")).mean[1]
        bright = ImageStat.Stat(im.convert("L")).mean[0]
        score = sharp * (0.6 + sat / 255) * (1 if 50 < bright < 215 else 0.5)
        if score > best:
            best, best_t = score, t
        t += 0.35
    R.ff(["-ss", f"{best_t:.2f}", "-i", video, "-frames:v", "1", "-q:v", "2", out_jpg])
    return best_t


# ---------- текст ----------
ASS_HEAD = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Line,Inter Display Bold,50,&H00FFFFFF,&H00FFFFFF,&H00000000,&H78000000,0,0,0,0,100,100,0,0,1,1.2,2.5,8,130,130,470,1
Style: Title,Inter Display ExtraBold,88,&H00FFFFFF,&H00FFFFFF,&H00000000,&H78000000,0,0,0,0,100,100,3,0,1,1.5,3,5,90,90,0,1
Style: Sub,Inter Display SemiBold,50,&H00FFFFFF,&H00FFFFFF,&H00000000,&H78000000,0,0,0,0,100,100,1,0,1,1,2.5,5,90,90,0,1
Style: End,Inter Display Bold,46,&H00FFFFFF,&H00FFFFFF,&H00000000,&H78000000,0,0,0,0,100,100,0,0,1,1,2.5,5,110,110,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def ev(style, a, b, text, tags=""):
    return f"Dialogue: 0,{R.t_ass(a)},{R.t_ass(b)},{style},,0,0,0,,{{{tags}}}{R.esc(text)}"


def build_text(fmt, src, cuts, total):
    lines = []
    if fmt == "vibe":
        lines.append(ev("Line", 0, total, src["text"], "\\fad(250,0)"))
    elif fmt == "event":
        end_t = max(total - 2.2, total * 0.72)
        lines.append(ev("Title", 0, end_t, src["title"].upper(), "\\pos(540,900)\\fad(200,150)"))
        if src.get("sub"):
            lines.append(ev("Sub", 0, end_t, src["sub"], "\\pos(540,1010)\\fad(200,150)"))
        lines.append(ev("End", end_t + 0.1, total, src.get("end_text", "Подробности в описании"), "\\pos(540,1180)\\fad(200,0)"))
    elif fmt == "pov":
        sw = cuts[len(src["clips_setup"])]
        lines.append(ev("Line", 0, sw, src["setup"]))
        lines.append(ev("Line", sw, total, src["punch"], "\\t(0,120,\\fscx106\\fscy106)\\t(120,240,\\fscx100\\fscy100)"))
    return ASS_HEAD + "\n".join(lines) + "\n"


# ---------- сборка ----------
def render(slug, src, out_dir, h):
    fmt = src["format"]
    DUBAI_ONLY["on"] = bool(src.get("dubai_only", fmt == "vibe"))
    clips = src["clips"] if fmt != "pov" else src["clips_setup"] + src["clips_punch"]
    clips = clips[:14]
    tmp = tempfile.mkdtemp()
    used = json.load(open(USED_P)) if os.path.exists(USED_P) else {}
    cache_p = os.path.join(out_dir, "assets.json")
    cache = json.load(open(cache_p)) if os.path.exists(cache_p) else {}
    target = float(src.get("seconds") or (13 if fmt != "event" else 15))

    # музыка
    music_mp3 = os.path.join(out_dir, "music.mp3")
    mk = R.key(src.get("music"), round(target))
    has_music = cache.get("music") == mk and os.path.exists(music_mp3)
    if not has_music:
        if R.DRY:
            R.ff(["-f", "lavfi", "-i", f"aevalsrc='0.6*sin(2*PI*60*t)*exp(-12*mod(t\\,0.5))':d={target + 3}:s=44100", music_mp3])
            has_music = True
        else:
            has_music = R.music(src.get("music"), target + 2, music_mp3)
        if has_music:
            cache["music"] = mk
    if not has_music:
        raise RuntimeError("нет музыки")
    bpm, beats = beats_of(music_mp3)
    cuts = cut_points(beats, 60 / bpm, len(clips), target)
    total = cuts[-1]
    R.log(f"{slug}: {fmt}, {bpm:.0f} bpm, {len(clips)} клипов, {total:.1f}s")

    # клипы
    src_cache = cache.setdefault("clips", {})
    paths = []
    for i, it in enumerate(clips):
        p = os.path.join(tmp, f"c{i}.mp4")
        ck = R.key(it)
        c = src_cache.get(str(i))
        d = cuts[i + 1] - cuts[i]
        ok = False
        if c and c.get("key") == ck and c.get("src", "").startswith("pexels:") and not R.DRY:
            try:
                vid = c["src"].split(":")[1]
                got = R.http(f"https://api.pexels.com/videos/videos/{vid}", headers={"Authorization": PEXELS_KEY}, timeout=60)
                files = [f for f in got["video_files"] if f.get("height", 0) >= 1080]
                f = sorted(files, key=lambda f: abs(f["height"] - 1920))[0]
                open(p, "wb").write(R.http(f["link"], raw=True, timeout=300))
                ok = True
            except Exception as e:
                R.log("clip cache miss", i, e)
        if not ok:
            try:
                s, author = get_clip(it, p, used, d + 1.0, i)
                src_cache[str(i)] = {"key": ck, "src": s, "author": author}
            except RuntimeError as e:
                if not paths:
                    raise
                R.log(f"clip {i}: {e}, повторяю кадр")
                import shutil
                shutil.copy(paths[-1 - (i % min(3, len(paths)))], p)
        paths.append(p)
    json.dump(cache, open(cache_p, "w"), ensure_ascii=False)
    if not R.DRY:
        json.dump(used, open(USED_P, "w"))

    # нарезка по долям: каждый клип с «панчем» на сильную долю
    parts = []
    for i, p in enumerate(paths):
        d = cuts[i + 1] - cuts[i]
        cl = R.probe_dur(p) or 6
        off = max(0.0, min(cl - d - 0.2, cl * 0.25))
        part = os.path.join(tmp, f"p{i}.mp4")
        punch = "if(lt(t,0.18),1.07-0.07*t/0.18,1.0)"
        R.ff(["-ss", f"{off:.2f}", "-i", p, "-vf",
              f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,fps={FPS},"
              f"tpad=stop_mode=clone:stop_duration=4,"
              f"scale=w='iw*({punch})':h='ih*({punch})':eval=frame,crop={W}:{H},"
              f"eq=contrast=1.05:saturation=1.12,format=yuv420p",
              "-t", f"{d:.3f}", "-an", "-r", str(FPS), "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", part])
        parts.append(part)
    lst = os.path.join(tmp, "list.txt")
    open(lst, "w").write("".join(f"file '{x}'\n" for x in parts))
    base = os.path.join(tmp, "base.mp4")
    R.ff(["-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", base])

    ass = os.path.join(tmp, "t.ass")
    open(ass, "w", encoding="utf-8").write(build_text(fmt, src, cuts, total))
    for old in [x for x in os.listdir(out_dir) if x.endswith(".mp4")]:
        os.remove(os.path.join(out_dir, old))
    video = f"{h}.mp4"
    out = os.path.join(out_dir, video)
    R.ff(["-i", base, "-i", music_mp3, "-filter_complex",
          f"[0]subtitles={ass}:fontsdir={R.FONTDIR},format=yuv420p[v];"
          f"[1]aresample=44100,afade=t=out:st={total - 0.8:.2f}:d=0.8,loudnorm=I=-13:TP=-1.2:LRA=9[a]",
          "-map", "[v]", "-map", "[a]", "-t", f"{total:.2f}",
          "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-maxrate", "6M", "-bufsize", "12M", "-pix_fmt", "yuv420p",
          "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out])
    ct = best_cover(out, 0, total * (0.7 if fmt == "event" else 0.95), os.path.join(out_dir, "cover.jpg"))
    authors = sorted({c.get("author") for c in src_cache.values() if c.get("author") not in (None, "", "ai", "dry")})
    json.dump({"hash": h, "video": video, "cover": "cover.jpg", "v": 2, "format": fmt, "duration": round(total, 1),
               "cover_t": round(ct, 2), "bpm": round(bpm), "stock_authors": authors}, open(os.path.join(out_dir, "render.json"), "w"),
              indent=1, ensure_ascii=False)
    R.log(f"rendered {fmt} {slug}: {total:.1f}s, {os.path.getsize(out) / 1e6:.1f} MB, cover at {ct:.1f}s")
    return True
