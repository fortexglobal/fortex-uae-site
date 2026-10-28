"""Рилсы v2: AI-видео с людьми (fal / Kling) + голос ElevenLabs + караоке-субтитры + музыка + CTA.

ig/reels/src/<slug>.json с "v": 2:
{
 "v": 2, "status": "approved", "publish_at": "2026-10-27T19:00+04:00",
 "caption": "...",
 "hook": "В Дубае теперь штрафуют за это",      # крупно сверху первые ~2.5 сек
 "accent": "штрафуют",                          # слово в хуке золотом (необязательно)
 "music": "tense modern trap beat, 100 bpm, ...",  # промпт музыки (без вокала)
 "voice_id": "...",                             # необязательно
 "shots": [
   {"prompt": "<англ. сцена для видео, с людьми, движение камеры>", "say": "<фраза диктора, 6-14 слов>"},
   ...
 ],
 "cta": {"title": "Подпишись", "text": "Новости Дубая каждый день", "say": "Подписывайся, чтобы не пропустить."}
}
Результат: ig/reels/<slug>/<hash>.mp4, cover.jpg, render.json (формат как у v1, публикует tools/ig.py).
Ключи: FAL_KEY, ELEVENLABS_API_KEY. REEL_DRY=1: тестовый прогон без API.
"""
import base64, math, concurrent.futures, glob, hashlib, json, os, re, subprocess, sys, tempfile, time, urllib.request, urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

W, H, FPS = 1080, 1920, 30
FAL_KEY = os.environ.get("FAL_KEY", "")
EL_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
DRY = os.environ.get("REEL_DRY") == "1"
FAL_MODELS = ["fal-ai/kling-video/v2.5-turbo/pro/text-to-video", "fal-ai/kling-video/v1.6/standard/text-to-video"]
VOICE_SPEED = 1.05  # Brian на 1.05 читает естественно, интонация в конце фразы вниз
VOICE_TEMPO = 1.10  # ускорение готового голоса без изменения тембра
DEFAULT_VOICE = os.environ.get("REEL_VOICE_ID", "nPczCjzI2devNBz1zQrb")  # Brian: утверждён Александром 26.10 (Adam читал плохо)
VOICE_SETTINGS = {"stability": 0.6, "similarity_boost": 0.8, "style": 0.1, "use_speaker_boost": True}
STYLE = (", vertical 9:16 framing, photorealistic, cinematic, natural skin, realistic people, dynamic camera movement, "
         "shallow depth of field, premium Dubai atmosphere, no text, no captions, no logos, no watermarks")
NEG = "text, letters, subtitles, watermark, logo, blurry, distorted face, extra fingers, cartoon, low quality"
FONTDIR = os.path.join(ROOT, "tools", "fonts")
LOG = []
LOG_PATH = [None]


def log(*a):
    s = " ".join(str(x) for x in a)
    print(s, flush=True)
    LOG.append(time.strftime("%H:%M:%S ") + s)
    if LOG_PATH[0]:
        try:
            open(LOG_PATH[0], "w").write("\n".join(LOG) + "\n")
        except Exception:
            pass


def http(url, data=None, headers=None, method=None, raw=False, timeout=180):
    body = json.dumps(data).encode() if isinstance(data, (dict, list)) else data
    h = {"Content-Type": "application/json"} if isinstance(data, (dict, list)) else {}
    h.update(headers or {})
    req = urllib.request.Request(url, data=body, headers=h, method=method or ("POST" if body is not None else "GET"))
    with urllib.request.urlopen(req, timeout=timeout) as r:
        b = r.read()
    return b if raw else json.loads(b)


def ff(args):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error"] + args, check=True)


def probe_dur(p):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", p],
                         capture_output=True, text=True).stdout.strip()
    return float(out or 0)


def key(*parts):
    return hashlib.md5(json.dumps(parts, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:12]


# ---------- голос ----------
def tts(text, voice_id, out_mp3):
    """Голос + тайминги каждой буквы."""
    if DRY:
        dur = max(2.0, len(text) * 0.062)
        ff(["-f", "lavfi", "-i", f"sine=frequency=180:duration={dur:.2f}", "-af", "volume=0.05", out_mp3])
        n = len(text)
        return {"characters": list(text), "character_start_times_seconds": [i * dur / n for i in range(n)],
                "character_end_times_seconds": [(i + 1) * dur / n for i in range(n)]}
    r = http(f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/with-timestamps?output_format=mp3_44100_128",
             {"text": text, "model_id": "eleven_multilingual_v2",
              "voice_settings": {**VOICE_SETTINGS, "speed": VOICE_SPEED}, "seed": 11},
             {"xi-api-key": EL_KEY}, timeout=300)
    open(out_mp3, "wb").write(base64.b64decode(r["audio_base64"]))
    return r.get("alignment") or r.get("normalized_alignment")


def speech_check(mp3, expected):
    """Распознаём готовый голос (ElevenLabs Scribe) и сравниваем со сценарием по словам.
    Возвращает {"match": 0..1, "heard": текст, "diffs": [[ожидали, услышали], ...]}."""
    import difflib, uuid
    try:
        b = "----" + uuid.uuid4().hex
        body = (f"--{b}\r\nContent-Disposition: form-data; name=\"model_id\"\r\n\r\nscribe_v1\r\n"
                f"--{b}\r\nContent-Disposition: form-data; name=\"language_code\"\r\n\r\nrus\r\n"
                f"--{b}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"v.mp3\"\r\nContent-Type: audio/mpeg\r\n\r\n").encode() \
            + open(mp3, "rb").read() + f"\r\n--{b}--\r\n".encode()
        try:
            r = http("https://api.elevenlabs.io/v1/speech-to-text", body,
                     {"xi-api-key": EL_KEY, "Content-Type": f"multipart/form-data; boundary={b}"}, timeout=180)
            heard = r.get("text", "")
        except Exception as e:  # у ключа ElevenLabs может не быть права на распознавание: слушаем через OpenRouter
            log("stt elevenlabs", e)
            key = os.environ.get("OPENROUTER_API_KEY", "")
            heard = ""
            for m in ("google/gemini-2.5-flash", "google/gemini-2.5-pro"):
                try:
                    r = http("https://openrouter.ai/api/v1/chat/completions",
                             {"model": m, "temperature": 0, "messages": [{"role": "user", "content": [
                                 {"type": "text", "text": "Дословно запиши, что говорит диктор, по-русски. Числа пиши словами так, как они прозвучали. Только текст, без комментариев."},
                                 {"type": "input_audio", "input_audio": {"data": base64.b64encode(open(mp3, "rb").read()).decode(), "format": "mp3"}}]}]},
                             {"Authorization": f"Bearer {key}"}, timeout=180)
                    heard = r["choices"][0]["message"]["content"].strip()
                    break
                except Exception as e2:
                    log("stt openrouter", m, e2)
            if not heard:
                raise RuntimeError("распознавание недоступно")
    except Exception as e:
        log("stt error", e)
        return {"error": str(e)[:200]}
    norm = lambda t: re.sub(r"[^а-яёa-z0-9 ]", " ", t.lower().replace("ё", "е").replace("\u0301", "")).split()
    a, bw = norm(expected), norm(heard)
    sm = difflib.SequenceMatcher(None, a, bw)
    diffs = [[" ".join(a[i1:i2]), " ".join(bw[j1:j2])] for op, i1, i2, j1, j2 in sm.get_opcodes() if op != "equal"]
    log(f"stt match {sm.ratio():.2f}, diffs {diffs[:8]}")
    return {"match": round(sm.ratio(), 3), "heard": heard, "diffs": diffs[:30]}


# ---------- музыка ----------
BANNED_MUSIC = ["corporate", "upbeat", "inspiring", "motivational", "uplifting", "happy", "background music",
                "positive", "epic cinematic", "commercial", "luxury"]


def clean_music_prompt(prompt):
    """Слова, которые дают стоковый звук, убираем; просим разреженную середину под голос."""
    p = prompt
    for w in BANNED_MUSIC:
        p = re.sub(r"\b" + re.escape(w) + r"\b", "", p, flags=re.I)
    p = re.sub(r"\s*,\s*(,\s*)+", ", ", re.sub(r"\s{2,}", " ", p)).strip(" ,.")
    return (p + ". Instrumental only, no vocals. Sparse arrangement under a spoken voice: keep the 1-4 kHz midrange open, "
            "weight on sub bass, kick, snare and crisp high percussion, short melodic hits only in the gaps. "
            "Distinct signature sound, not generic stock music. Punchy start in the first second")


def music(prompt, secs, out_mp3):
    if DRY or not prompt:
        return False
    p = clean_music_prompt(prompt)
    ms = int(min(max(secs + 1.5, 10), 90) * 1000)
    if EL_KEY:
        try:
            b = http("https://api.elevenlabs.io/v1/music?output_format=mp3_44100_128",
                     {"prompt": p, "music_length_ms": ms, "force_instrumental": True}, {"xi-api-key": EL_KEY}, raw=True, timeout=300)
            if len(b) > 10000:
                open(out_mp3, "wb").write(b)
                log("music: elevenlabs ok")
                return True
        except urllib.error.HTTPError as e:
            log("music elevenlabs", e.code, e.read()[:300])
        except Exception as e:
            log("music elevenlabs", e)
    if FAL_KEY:
        try:
            r = fal_run("fal-ai/elevenlabs/music", {"prompt": p, "music_length_ms": ms, "force_instrumental": True})
            open(out_mp3, "wb").write(http(r["audio"]["url"], raw=True))
            log("music: fal ok")
            return True
        except Exception as e:
            log("music fal", e)
    return False


# ---------- видео ----------
def fal_run(model, payload, max_wait=900):
    hd = {"Authorization": f"Key {FAL_KEY}"}
    q = http(f"https://queue.fal.run/{model}", payload, hd)
    st_url, res_url = q["status_url"], q["response_url"]
    t0 = time.time()
    while time.time() - t0 < max_wait:
        time.sleep(6)
        st = http(st_url, headers=hd)
        if st.get("status") == "COMPLETED":
            return http(res_url, headers=hd)
        if int(time.time() - t0) % 120 < 6:
            log(f"  {model.split('/')[-2]}: {st.get('status')} {int(time.time() - t0)}s")
        if st.get("status") in ("FAILED", "ERROR"):
            raise RuntimeError(f"fal failed: {st}")
    raise TimeoutError(model)


def gen_clip(prompt, secs, out_mp4, idx):
    if DRY:
        ff(["-f", "lavfi", "-i", f"testsrc2=size=720x1280:rate=30:duration={5 if secs <= 5 else 10}",
            "-vf", f"hue=h={idx * 60}", "-pix_fmt", "yuv420p", out_mp4])
        return "dry"
    dur = "5" if secs <= 7.0 else "10"
    last = None
    for m in FAL_MODELS:
        try:
            r = fal_run(m, {"prompt": prompt + STYLE, "duration": dur, "aspect_ratio": "9:16", "negative_prompt": NEG, "cfg_scale": 0.5})
            url = r["video"]["url"]
            open(out_mp4, "wb").write(http(url, raw=True, timeout=300))
            log(f"clip {idx}: {m.split('/')[2]} {dur}s ok")
            return url
        except urllib.error.HTTPError as e:
            last = f"{m} {e.code} {e.read()[:300]}"
        except Exception as e:
            last = f"{m} {e}"
        log(f"clip {idx} fail:", last)
    raise RuntimeError(last)


# ---------- герой бренда: фото с образцом лица + оживление (Kling image-to-video) ----------
HERO_LOOK = ("Ultra photorealistic vertical 9:16 photo shot on a modern smartphone, bright daytime, soft natural sunlight, "
             "airy light palette with warm cream, beige and soft sky-blue tones, real skin texture, candid documentary moment, "
             "Dubai, no text, no logos, no brand names, no watermarks. Scene: ")


def hero_image(hero, prompt, out_jpg):
    heroes = json.load(open(os.path.join(ROOT, "ig", "heroes", "heroes.json")))
    h = heroes[hero]
    ref = base64.b64encode(open(os.path.join(ROOT, h["file"]), "rb").read()).decode()
    content = [{"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + ref}},
               {"type": "text", "text": "Keep exactly the same person as in the reference photo (same face, hair, age, build): "
                + h["desc"] + ". " + HERO_LOOK + prompt}]
    last = None
    for _ in range(2):
        try:
            r = http("https://openrouter.ai/api/v1/chat/completions",
                     {"model": "google/gemini-2.5-flash-image", "modalities": ["image", "text"], "image_config": {"aspect_ratio": "9:16"},
                      "messages": [{"role": "user", "content": content}]},
                     {"Authorization": "Bearer " + os.environ.get("OPENROUTER_API_KEY", "")})
            url = r["choices"][0]["message"]["images"][0]["image_url"]["url"]
            open(out_jpg, "wb").write(base64.b64decode(url.split(",", 1)[1]))
            return
        except Exception as e:
            last = e
            log("hero image retry:", e)
    raise RuntimeError(f"hero image failed: {last}")


def hero_clip(sh, out_mp4, out_dir, i, ck):
    img = os.path.join(out_dir, f"hero-{i}-{ck[:6]}.jpg")
    if not os.path.exists(img):
        for old in glob.glob(os.path.join(out_dir, f"hero-{i}-*.jpg")):
            os.remove(old)
        hero_image(sh["hero"], sh["img"], img)
        log(f"hero image {i} ok")
    uri = "data:image/jpeg;base64," + base64.b64encode(open(img, "rb").read()).decode()
    r = fal_run("fal-ai/kling-video/v2.5-turbo/pro/image-to-video",
                {"prompt": sh.get("move") or "subtle natural movement, slow push-in, handheld camera", "image_url": uri,
                 "duration": "5", "negative_prompt": NEG + ", distorted hands, morphing face", "cfg_scale": 0.5})
    url = r["video"]["url"]
    open(out_mp4, "wb").write(http(url, raw=True, timeout=300))
    log(f"hero clip {i} ok")
    return url


# ---------- звуковые эффекты ----------
SFX = {
    "whoosh1": ("fast cinematic whoosh swipe transition, short airy swoosh, clean, no music", 0.6),
    "whoosh2": ("quick swipe whoosh, smartphone screen swipe sound, crisp, no music", 0.5),
    "click": ("single crisp computer mouse click, close up, clean, no reverb", 0.5),
    "pop": ("soft modern UI pop notification sound, bright, short, clean", 0.6),
}


def sfx_path(name):
    d = os.path.join(ROOT, "ig", "sfx")
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, name + ".mp3")
    if os.path.exists(p):
        return p
    prompt, dur = SFX[name]
    if DRY:
        ff(["-f", "lavfi", "-i", f"anoisesrc=d={dur}:c=pink:a=0.4", "-af", f"afade=t=out:st=0:d={dur}", p])
        return p
    if not EL_KEY:
        return None
    try:
        b = http("https://api.elevenlabs.io/v1/sound-generation?output_format=mp3_44100_128",
                 {"text": prompt, "duration_seconds": dur, "prompt_influence": 0.7}, {"xi-api-key": EL_KEY}, raw=True, timeout=120)
        if len(b) > 2000:
            open(p, "wb").write(b)
            log("sfx generated:", name)
            return p
    except urllib.error.HTTPError as e:
        log("sfx", name, e.code, e.read()[:200])
    except Exception as e:
        log("sfx", name, e)
    return None


# ---------- субтитры ----------
ALT_RE = re.compile(r"\{([^{}|]+)\|([^{}]+)\}")


def parse_say(say):
    """«{375 тысяч|триста семьдесят пять тысяч}»: в субтитрах цифры, диктор читает словами."""
    spoken, alts, pos = "", [], 0
    for m in ALT_RE.finditer(say):
        spoken += say[pos:m.start()]
        a = len(spoken)
        spoken += m.group(2).strip()
        alts.append((a, len(spoken), m.group(1).strip()))
        pos = m.end()
    spoken += say[pos:]
    return spoken, alts


def words_from(al, alts=()):
    chars, st, en = al["characters"], al["character_start_times_seconds"], al["character_end_times_seconds"]
    out, cur = [], None
    for idx, (c, s, e) in enumerate(zip(chars, st, en)):
        if c.isspace():
            if cur:
                out.append(cur); cur = None
            continue
        if cur is None:
            cur = {"w": c, "s": s, "e": e, "i": idx}
        else:
            cur["w"] += c; cur["e"] = e
    if cur:
        out.append(cur)
    if not alts:
        return out
    merged, k = [], 0
    for w in out:
        hit = next(((a, b, d) for a, b, d in alts if a <= w["i"] < b), None)
        if hit:
            tail = ""
            m = re.search(r"[.,!?:;…]+$", w["w"])
            if m and w["i"] + len(w["w"]) >= hit[1]:
                tail = m.group(0)
            if merged and merged[-1].get("alt") == hit:
                merged[-1]["e"] = w["e"]
                merged[-1]["w"] = hit[2] + tail
            else:
                merged.append({"w": hit[2] + tail, "s": w["s"], "e": w["e"], "i": w["i"], "alt": hit})
        else:
            merged.append(w)
    return merged


# Сейф-зона Instagram 1080x1920: низ (рядом кнопки) x 70-910, y 1065-1485. Субтитры по центру этой полосы.
CAP_X, CAP_Y = 490, 1170
CAP_MAX_W = 760          # 840 ширина полосы минус обводка и запас
NUM_SCALE = 1.22         # цифры и суммы в активный момент крупнее
_FONT = {}


def text_w(t, size=80):
    try:
        from PIL import ImageFont
        if size not in _FONT:
            _FONT[size] = ImageFont.truetype(os.path.join(FONTDIR, "InterDisplay-ExtraBold.otf"), size)
        return _FONT[size].getlength(t)
    except Exception:
        return len(t) * size * 0.62


def is_num(w):
    return bool(w.get("alt")) and bool(re.search(r"\d", w["w"]))


def chunk_w(ch):
    """Ширина строки в худший момент: активное слово увеличено."""
    base = [text_w(x["w"]) for x in ch]
    sp = text_w(" ") * (len(ch) - 1)
    worst = 0
    for i, x in enumerate(ch):
        k = NUM_SCALE if is_num(x) else 1.08
        worst = max(worst, sum(base) + sp + base[i] * (k - 1))
    return worst


def chunks_of(words):
    res, cur = [], []
    for w in words:
        if cur and chunk_w(cur + [w]) > CAP_MAX_W:
            res.append(cur); cur = []
        cur.append(w)
        text_len = sum(len(x["w"]) + 1 for x in cur)
        if len(cur) >= 3 or text_len >= 17 or re.search(r"[.,!?:;…]$", w["w"]):
            res.append(cur); cur = []
    if cur:
        res.append(cur)
    return res


def safe_report(words, cap_end):
    """Проверка сейф-зоны для отчёта: самая широкая строка субтитров и запас до края."""
    chs = chunks_of([w for w in words if w["s"] < cap_end])
    widest = max((chunk_w(c) for c in chs), default=0)
    bad = [" ".join(x["w"] for x in c) for c in chs if chunk_w(c) > 840 - 2 * 6]
    return {"cap_widest_px": round(widest), "cap_limit_px": 828, "cap_box": [CAP_X - 420, CAP_Y - 60, CAP_X + 420, CAP_Y + 60],
            "overflow": bad, "ok": not bad}


def t_ass(t):
    t = max(0, t)
    return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"


def esc(s):
    return s.replace("\\", "").replace("{", "(").replace("}", ")")


def build_ass(words, hook, accent, hook_end, cap_end, total, light=False):
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,Inter Display ExtraBold,80,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,6,0,5,80,80,0,1
Style: Hook,Inter Display ExtraBold,92,&H00FFFFFF,&H00FFFFFF,&H00261610,&H00000000,0,0,0,0,100,100,-1,0,3,26,0,8,124,124,330,1
Style: HookL,Playfair Display Medium,84,&H0026160B,&H0026160B,&H00E6EFF4,&H00000000,0,0,0,0,100,100,0,0,3,30,0,8,124,124,330,1
Style: Brand,Inter Display ExtraBold,34,&H3061A2C9,&H3061A2C9,&H00000000,&H00000000,0,0,0,0,100,100,4,0,1,2,0,7,76,76,250,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ev = [f"Dialogue: 0,{t_ass(0)},{t_ass(cap_end)},Brand,,0,0,0,,FORTEX UAE"]
    if hook and light:  # кремовая плашка, шрифт с засечками, акцент курсивом золотом (как обложки ленты)
        ht = esc(hook)
        if accent and accent in hook:
            ht = ht.replace(esc(accent), "{\\i1\\c&H337A9C&}" + esc(accent) + "{\\i0\\c&H26160B&}", 1)
        ev.append(f"Dialogue: 2,{t_ass(0)},{t_ass(hook_end)},HookL,,0,0,0,,{{\\fad(120,180)}}{ht}")
    elif hook:
        ht = esc(hook)
        if accent and accent in hook:
            ht = ht.replace(esc(accent), "{\\c&H77C8E6&}" + esc(accent) + "{\\c&HFFFFFF&}", 1)
        ev.append(f"Dialogue: 2,{t_ass(0)},{t_ass(hook_end)},Hook,,0,0,0,,{{\\fad(0,180)\\t(0,160,\\fscx104\\fscy104)\\t(160,320,\\fscx100\\fscy100)}}{ht}")
    gold = "&H77C8E6&"
    chs = chunks_of([w for w in words if w["s"] < cap_end])
    for ci, ch in enumerate(chs):
        nxt = chs[ci + 1][0]["s"] if ci + 1 < len(chs) else cap_end
        for i, w in enumerate(ch):
            s = w["s"] if i else ch[0]["s"]
            e = ch[i + 1]["s"] if i + 1 < len(ch) else min(ch[-1]["e"] + 0.12, nxt)
            if s >= cap_end:
                break
            e = min(e, cap_end)
            parts = []
            for j, x in enumerate(ch):
                t = esc(x["w"])
                if j == i and is_num(x):  # цифра: крупнее, золотом, с «прыжком»
                    sc = int(NUM_SCALE * 100)
                    parts.append("{\\c" + gold + f"\\fscx{sc - 14}\\fscy{sc - 14}\\t(0,110,\\fscx{sc}\\fscy{sc})" + "}" + t + "{\\c&HFFFFFF&\\fscx100\\fscy100}")
                elif j == i:
                    parts.append("{\\c" + gold + "\\fscx108\\fscy108}" + t + "{\\c&HFFFFFF&\\fscx100\\fscy100}")
                elif is_num(x):
                    parts.append("{\\c" + gold + "}" + t + "{\\c&HFFFFFF&}")
                else:
                    parts.append(t)
            pop = f"{{\\pos({CAP_X},{CAP_Y})" + ("\\fscx88\\fscy88\\t(0,90,\\fscx100\\fscy100)" if i == 0 else "") + "}"
            ev.append(f"Dialogue: 1,{t_ass(s)},{t_ass(e)},Cap,,0,0,0,,{pop}{' '.join(parts)}")
    return head + "\n".join(ev) + "\n"


# ---------- готовое видео + музыка ----------
def render_motion(slug, src, out_dir):
    """{"v": 2, "format": "motion", "video": "ig/motion/how-9x16.mp4", "music": "...", "cover_at": 2.0}
    Анимация уже собрана (tools/motion_how.py): добавляем музыку ElevenLabs под её звуки, громкость -14 LUFS, обложку."""
    vid = os.path.join(ROOT, src["video"])
    h = key(src["video"], os.path.getsize(vid), src.get("music"), src.get("premixed"), "m1", DRY)[:10]
    meta_p = os.path.join(out_dir, "render.json")
    if os.path.exists(meta_p) and json.load(open(meta_p)).get("hash") == h:
        return False
    if not DRY and not EL_KEY and not src.get("premixed"):
        log("no ELEVENLABS_API_KEY, skip", slug)
        return False
    total = probe_dur(vid)
    cache_p = os.path.join(out_dir, "assets.json")
    cache = json.load(open(cache_p)) if os.path.exists(cache_p) else {}
    music_mp3 = os.path.join(out_dir, "music.mp3")
    mk = key(src.get("music"), round(total))
    has_music = cache.get("music") == mk and os.path.exists(music_mp3)
    if src.get("premixed"):  # видео уже с голосом и музыкой: только перекодируем
        has_music = False
    elif not has_music:
        has_music = music(src.get("music"), total, music_mp3)
        if has_music:
            cache["music"] = mk
            json.dump(cache, open(cache_p, "w"), ensure_ascii=False)
    for old in glob.glob(os.path.join(out_dir, "*.mp4")):
        os.remove(old)
    video = f"{h}.mp4"
    out = os.path.join(out_dir, video)
    if has_music:
        af = (f"[1]aresample=44100,volume=0.8,afade=t=in:d=0.2,afade=t=out:st={total - 1.5:.2f}:d=1.5[mu];"
              f"[0:a]aresample=44100,volume=1.4[fx];[mu][fx]amix=inputs=2:duration=first:normalize=0,"
              f"atrim=0:{total:.2f},loudnorm=I=-14:TP=-1.5:LRA=11[a]")
        ff(["-i", vid, "-stream_loop", "-1", "-i", music_mp3, "-filter_complex", af, "-map", "0:v", "-map", "[a]",
            "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-maxrate", "6M", "-bufsize", "12M", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-t", f"{total:.2f}", out])
    else:
        ff(["-i", vid, "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart", out])
    ff(["-ss", str(src.get("cover_at", 2.0)), "-i", out, "-frames:v", "1", "-q:v", "2", os.path.join(out_dir, "cover.jpg")])
    meta = {"stt": stt, "hash": h, "video": video, "cover": "cover.jpg", "v": 2, "duration": round(total, 1), "ai_clips": ai_used,
            "stock": {k: v for k, v in clips.items() if v.get("key") == "stock"}, "music": has_music}
    try:
        import reel_qa
        if not DRY:
            reel_qa.normalize(out)
        meta["qa"] = reel_qa.run(out, os.path.join(out_dir, "qa"))
    except Exception as e:
        log("qa error", e)
    json.dump(meta, open(meta_p, "w"), indent=1, ensure_ascii=False)
    log(f"rendered motion {slug}: {total:.1f}s, music={has_music}")
    return True


# ---------- сборка ----------
def render_one(slug, src, browser):
    out_dir = os.path.join(ROOT, "ig", "reels", slug)
    os.makedirs(out_dir, exist_ok=True)
    if src.get("format") == "motion":
        return render_motion(slug, src, out_dir)
    if src.get("format") in ("vibe", "event", "pov"):
        import reel_fmt
        reel_fmt.R = sys.modules[__name__]
        body = {k: v for k, v in src.items() if k not in ("status", "publish_at", "caption")}
        h = key(body, "f1", DRY)[:10]
        meta_p = os.path.join(out_dir, "render.json")
        if os.path.exists(meta_p) and json.load(open(meta_p)).get("hash") == h:
            return False
        if not DRY and not (EL_KEY and (os.environ.get("PEXELS_API_KEY") or os.environ.get("PIXABAY_API_KEY"))):
            print("no ELEVENLABS_API_KEY / PEXELS_API_KEY yet, skip", slug)
            return False
        return reel_fmt.render(slug, src, out_dir, h)
    shots = src["shots"][:7]
    cta = src.get("cta") or {"title": "Подпишись", "text": "Новости Дубая для предпринимателей каждый день", "say": "Подписывайся, чтобы быть в курсе."}
    h = key(src.get("hook"), src.get("accent"), shots, cta, src.get("music"), src.get("voice_id"), src.get("look"), src.get("cover_shot"), "v2.13", DRY)[:10]
    meta_p = os.path.join(out_dir, "render.json")
    if os.path.exists(meta_p) and json.load(open(meta_p)).get("hash") == h:
        meta = json.load(open(meta_p))
        vm = os.path.join(out_dir, "voice.mp3")
        if not DRY and EL_KEY and (not meta.get("stt") or meta["stt"].get("error")) and os.path.exists(vm):
            sp = " ".join(parse_say(x.strip())[0] for x in [sh["say"] for sh in shots] + [cta.get("say", "")] if x.strip())
            meta["stt"] = speech_check(vm, sp)
            json.dump(meta, open(meta_p, "w"), indent=1, ensure_ascii=False)
            return True
        return False
    if not DRY and not (FAL_KEY and EL_KEY):
        log("no FAL_KEY / ELEVENLABS_API_KEY, skip", slug)
        return False
    cache_p = os.path.join(out_dir, "assets.json")
    cache = json.load(open(cache_p)) if os.path.exists(cache_p) else {}
    tmp = tempfile.mkdtemp()

    # 1. голос
    raw = [s["say"].strip() for s in shots] + [cta.get("say", "").strip()]
    raw = [l for l in raw if l]
    lines, alts, off = [], [], 0
    for r_ in raw:
        sp, al_ = parse_say(r_)
        lines.append(sp)
        alts += [(a + off, b + off, d) for a, b, d in al_]
        off += len(sp) + 1
    text = " ".join(lines)
    vid = src.get("voice_id") or DEFAULT_VOICE
    vk = key(text, vid, VOICE_SPEED, VOICE_SETTINGS, DRY)  # сырой голос; ускорение ниже
    voice_mp3 = os.path.join(out_dir, "voice.mp3")
    if cache.get("voice") == vk and os.path.exists(voice_mp3) and cache.get("align"):
        al = cache["align"]
    else:
        al = tts(text, vid, voice_mp3)
        cache.update(voice=vk, align=al)
    if VOICE_TEMPO != 1.0:
        fast = os.path.join(tmp, "voice_fast.wav")
        ff(["-i", voice_mp3, "-af", f"atempo={VOICE_TEMPO}", fast])
        voice_mp3 = fast
        al = {k: ([t / VOICE_TEMPO for t in v] if k.endswith("seconds") else v) for k, v in al.items()}
    stt = cache.get("stt") if cache.get("stt_key") == vk and not (cache.get("stt") or {}).get("error") else None
    if stt is None and not DRY:
        stt = speech_check(voice_mp3, text)
        cache.update(stt=stt, stt_key=vk)
    vdur = probe_dur(voice_mp3)
    # время начала каждой фразы
    starts, pos = [], 0
    cst = al["character_start_times_seconds"]
    for l in lines:
        i = text.find(l, pos)
        starts.append(cst[min(i, len(cst) - 1)] if i >= 0 else (starts[-1] + 2 if starts else 0))
        pos = max(pos, i + len(l))
    starts[0] = 0.0
    total = vdur + 0.9
    seg = [(starts[k], starts[k + 1] if k + 1 < len(starts) else total) for k in range(len(starts))]
    n_shot = len(shots)
    shot_seg = seg[:n_shot]
    if len(seg) > n_shot:  # CTA идёт поверх последнего кадра: продлеваем последний шот
        cta_start = seg[n_shot][0]
        shot_seg[-1] = (shot_seg[-1][0], total)
    else:
        cta_start = max(total - 2.5, shot_seg[-1][0])
    log(f"{slug}: voice {vdur:.1f}s, shots {[round(b - a, 1) for a, b in shot_seg]}")

    # 2. клипы (параллельно)
    clips = cache.setdefault("clips", {})
    paths = [os.path.join(tmp, f"c{i}.mp4") for i in range(n_shot)]

    import reel_fmt
    reel_fmt.R = sys.modules[__name__]
    used = json.load(open(reel_fmt.USED_P)) if os.path.exists(reel_fmt.USED_P) else {}
    ai_used = []

    def get(i):
        need = shot_seg[i][1] - shot_seg[i][0]
        if shots[i].get("hero"):  # постоянный герой бренда (ig/heroes): фото с образцом лица, потом оживление
            ck = key("hero", shots[i]["hero"], shots[i]["img"], shots[i].get("move"), DRY)
            c = clips.get(str(i)) or {}
            if c.get("key") == ck and c.get("url"):
                try:
                    open(paths[i], "wb").write(http(c["url"], raw=True, timeout=300))
                    ai_used.append(i)
                    return
                except Exception as e:
                    log(f"hero {i} cache miss: {e}")
            url = hero_clip(shots[i], paths[i], out_dir, i, ck)
            clips[str(i)] = {"key": ck, "url": url, "hero": shots[i]["hero"]}
            ai_used.append(i)
            return
        if shots[i].get("link"):  # закреплённый стоковый клип (подобран через tools/stock_search.py)
            hd = reel_fmt.UA if "pixabay" in shots[i]["link"] else {}
            open(paths[i], "wb").write(http(shots[i]["link"], headers=hd, raw=True, timeout=300))
            clips[str(i)] = {"key": "stock", "q": shots[i].get("q", ""), "src": shots[i]["link"], "author": "pinned",
                             "link": shots[i]["link"], "site": "pixabay" if "pixabay" in shots[i]["link"] else "pexels"}
            return
        if shots[i].get("q"):  # живое стоковое видео (Pexels/Pixabay); ИИ-клип только если сток ничего не нашёл
            c = clips.get(str(i)) or {}
            if c.get("key") == "stock" and c.get("q") == shots[i]["q"] and c.get("link"):  # тот же запрос: тот же кадр
                try:
                    hd = reel_fmt.UA if c.get("site") == "pixabay" else {}
                    open(paths[i], "wb").write(http(c["link"], headers=hd, raw=True, timeout=300))
                    return
                except Exception as e:
                    log(f"stock {i} cache miss: {e}")
            if i == 0:
                reel_fmt.AI_BUDGET["left"] = 0  # первый кадр всегда живой
            try:
                sid, author = reel_fmt.get_clip({"q": shots[i]["q"], "prompt": shots[i].get("prompt")}, paths[i], used, min(need, 6), i)
            except RuntimeError:
                reel_fmt.AI_BUDGET["left"] = 2
                sid, author = reel_fmt.get_clip({"q": shots[i]["q"].split(",")[0] + " dubai", "prompt": shots[i].get("prompt")}, paths[i], used, 3, i)
            if i == 0:
                reel_fmt.AI_BUDGET["left"] = 2
            if author == "ai":
                ai_used.append(i)
            link, site = reel_fmt.LAST_LINK.get(i, (None, None)) if author != "ai" else (None, None)
            clips[str(i)] = {"key": "stock", "q": shots[i]["q"], "src": sid, "author": author, "link": link, "site": site}
            return
        ck = key(shots[i]["prompt"], need > 7.0, DRY)
        c = clips.get(str(i))
        if c and c.get("key") == ck and c.get("url") and c["url"] != "dry":
            try:
                open(paths[i], "wb").write(http(c["url"], raw=True, timeout=300))
                return
            except Exception as e:
                log(f"clip {i} cache miss: {e}")
        url = gen_clip(shots[i]["prompt"], need, paths[i], i)
        clips[str(i)] = {"key": ck, "url": url}

    get(0)  # первый кадр отдельно: для него запрет на ИИ
    with concurrent.futures.ThreadPoolExecutor(4) as ex:
        list(ex.map(get, range(1, n_shot)))
    json.dump(used, open(reel_fmt.USED_P, "w"))
    json.dump(cache, open(cache_p, "w"), ensure_ascii=False)

    # 3. музыка
    music_mp3 = os.path.join(out_dir, "music.mp3")
    mk = key(src.get("music"), round(total))
    has_music = cache.get("music") == mk and os.path.exists(music_mp3)
    if src.get("premixed"):  # видео уже с голосом и музыкой: только перекодируем
        has_music = False
    elif not has_music:
        has_music = music(src.get("music"), total, music_mp3)
        if has_music:
            cache["music"] = mk
    json.dump(cache, open(cache_p, "w"), ensure_ascii=False)

    # 4. нарезка кадров под фразы
    XF = 0.28
    LIGHT = src.get("look") == "light"  # светлый журнальный стиль ленты (ig/feed/STYLE.md)
    GRADE = ("eq=contrast=0.98:brightness=0.035:saturation=0.9:gamma=1.04,colorbalance=rm=0.03:gm=0.01:bm=-0.03"
             if LIGHT else "eq=contrast=1.06:saturation=1.08")
    TRANS = ["smoothleft", "zoomin", "smoothup", "slideleft", "smoothright", "circleopen"]
    parts = []
    for i, (a, b) in enumerate(shot_seg):
        d = b - a + (XF if i + 1 < len(shot_seg) else 0)
        cl = probe_dur(paths[i]) or 5
        part = os.path.join(tmp, f"p{i}.mp4")
        # без замедления: фразу режем на куски ~2 с из разных моментов ролика (динамика как в топовых рилсах)
        n = max(1, int(math.ceil(d / 2.2)))
        piece = d / n
        subs = []
        for k in range(n):
            off = 0.0 if cl <= piece + 0.1 else (cl - piece - 0.05) * (k / max(1, n - 1) if n > 1 else 0.15)
            z0, z1 = (1.0, 1.06) if k % 2 == 0 else (1.10, 1.04)  # чередуем лёгкий наезд и отъезд
            zz = f"{z0}+({z1}-{z0})*t/{piece:.3f}"
            sp = os.path.join(tmp, f"p{i}_{k}.mp4")
            ff(["-ss", f"{off:.3f}", "-stream_loop", "-1", "-i", paths[i], "-t", f"{piece:.3f}", "-vf",
                f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,fps={FPS},"
                f"scale=w='iw*({zz})':h='ih*({zz})':eval=frame,crop={W}:{H},"
                f"{GRADE},format=yuv420p",
                "-an", "-r", str(FPS), "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", sp])
            subs.append(sp)
        if len(subs) == 1:
            os.replace(subs[0], part)
        else:
            lst = os.path.join(tmp, f"p{i}.txt")
            open(lst, "w").write("".join(f"file '{x}'\n" for x in subs))
            ff(["-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", part])
        parts.append(part)
    base = os.path.join(tmp, "base.mp4")
    if len(parts) == 1:
        base = parts[0]
    else:
        args, chain, prev = [], [], "[0]"
        for p_ in parts:
            args += ["-i", p_]
        for k in range(1, len(parts)):
            outl = f"[x{k}]" if k + 1 < len(parts) else "[vout]"
            chain.append(f"{prev}[{k}]xfade=transition={TRANS[(k - 1) % len(TRANS)]}:duration={XF}:offset={shot_seg[k][0]:.3f}{outl}")
            prev = outl
        ff(args + ["-filter_complex", ";".join(chain), "-map", "[vout]", "-an", "-r", str(FPS),
                   "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-pix_fmt", "yuv420p", base])

    # 5. CTA-карточка и субтитры
    import reel_render
    ov = os.path.join(tmp, "cta.png")
    if LIGHT:
        import reel_cover
        reel_cover.render_cta_light(cta["title"], cta.get("text", ""), ov, browser)
    else:
        pg = browser.new_page(viewport={"width": W, "height": H})
        pg.set_content(reel_render.scene_html({"type": "cta", "title": cta["title"], "text": cta.get("text", "")})); pg.wait_for_timeout(250)
        pg.screenshot(path=ov, omit_background=True); pg.close()
    hook_end = min(2.8, shot_seg[1][0] if n_shot > 1 else 2.8)
    ass = os.path.join(tmp, "subs.ass")
    open(ass, "w", encoding="utf-8").write(build_ass(words_from(al, alts), src.get("hook"), src.get("accent"), hook_end, cta_start, total, LIGHT))

    for old in glob.glob(os.path.join(out_dir, "*.mp4")):
        os.remove(old)
    video = f"{h}.mp4"
    inputs = ["-i", base, "-loop", "1", "-t", f"{total:.2f}", "-i", ov, "-i", voice_mp3]
    vf = (f"[0]drawbox=x=0:y=0:w=iw:h=ih:color={'0xF4EFE6@0.30' if LIGHT else 'black@0.38'}:t=fill:enable='gte(t,{cta_start:.2f})'[bd];"
          f"[1]format=rgba,fade=t=in:st={cta_start:.2f}:d=0.25:alpha=1[cta];"
          f"[bd][cta]overlay=0:0:enable='gte(t,{cta_start:.2f})',"
          f"subtitles={ass}:fontsdir={FONTDIR},format=yuv420p[v]")
    # эффекты: клик на хуке, свайп на каждой смене кадра, «поп» на CTA
    events = [("click", 0.05)] + [(f"whoosh{1 + k % 2}", max(0, shot_seg[k][0] - 0.12)) for k in range(1, n_shot)] + [("pop", cta_start)]
    sfx_in, sfx_f = [], []
    nxt = 4 if has_music else 3
    for name, t in events:
        sp = sfx_path(name)
        if not sp:
            continue
        sfx_in += ["-i", sp]
        vol = 0.45 if name == "click" else 0.28  # эффекты минимум на 12 дБ ниже голоса
        sfx_f.append(f"[{nxt}]aresample=44100,volume={vol},adelay={int(t * 1000)}:all=1[s{nxt}]")
        nxt += 1
    labels = "".join(f"[s{k}]" for k in range(4 if has_music else 3, nxt))
    sfx_mix = (";".join(sfx_f) + f";{labels}amix=inputs={len(sfx_f)}:duration=longest:normalize=0[fx]") if sfx_f else ""
    if has_music:
        inputs += ["-stream_loop", "-1", "-i", music_mp3]
        af = (f"[2]aresample=44100,apad,asplit=2[vo][sc];"
              f"[3]aresample=44100,volume=0.30,equalizer=f=2400:t=o:w=1.6:g=-7,afade=t=in:d=0.3,afade=t=out:st={total - 1.2:.2f}:d=1.2[mu];"
              f"[mu][sc]sidechaincompress=threshold=0.02:ratio=9:attack=15:release=350[duck];")
        mix_in = "[vo][duck]"; n_in = 2
    else:
        af = "[2]aresample=44100,apad[vo];"
        mix_in = "[vo]"; n_in = 1
    if sfx_mix:
        af += sfx_mix + ";"
        mix_in += "[fx]"; n_in += 1
    af += f"{mix_in}amix=inputs={n_in}:duration=first:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=11[a]"  # итог -14 LUFS, пик не выше -1 dBTP
    inputs += sfx_in
    ff(inputs + ["-filter_complex", vf + ";" + af, "-map", "[v]", "-map", "[a]", "-t", f"{total:.2f}",
                 "-c:v", "libx264", "-preset", "medium", "-crf", "22", "-maxrate", "4.5M", "-bufsize", "9M", "-pix_fmt", "yuv420p",
                 "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-movflags", "+faststart", os.path.join(out_dir, video)])
    try:
        import reel_fmt, reel_cover
        reel_fmt.R = sys.modules[__name__]
        frame = os.path.join(tmp, "frame.jpg")
        cs = src.get("cover_shot")
        if isinstance(cs, int) and 0 <= cs < n_shot:
            reel_fmt.best_cover(base, shot_seg[cs][0] + 0.1, shot_seg[cs][1] - 0.1, frame)
        else:
            reel_fmt.best_cover(base, 0.2, min(cta_start, total) - 0.3, frame)  # чистый кадр без текста
        if LIGHT:
            reel_cover.render_light(frame, src.get("cover_title") or src.get("hook"), src.get("cover_accent") or src.get("accent"),
                                    os.path.join(out_dir, "cover.jpg"), browser)
        else:
            reel_cover.render(frame, src.get("cover_title") or src.get("hook"), src.get("accent"),
                              src.get("cover_note") or "Новости Дубая", os.path.join(out_dir, "cover.jpg"), browser)
    except Exception as e:
        log("cover fallback", e)
        ff(["-ss", "0.9", "-i", os.path.join(out_dir, video), "-frames:v", "1", "-q:v", "3", os.path.join(out_dir, "cover.jpg")])
    meta = {"stt": stt, "hash": h, "video": video, "cover": "cover.jpg", "v": 2, "duration": round(total, 1), "ai_clips": ai_used,
            "stock": {k: v for k, v in clips.items() if v.get("key") == "stock"},
            "safe_zone": safe_report(words_from(al, alts), cta_start)}
    try:
        import reel_qa
        if not DRY:
            reel_qa.normalize(os.path.join(out_dir, video))  # второй проход: -14 LUFS, пик ниже -1 dBTP
        cuts = [shot_seg[k][0] for k in range(1, n_shot)] + [cta_start]
        meta["qa"] = reel_qa.run(os.path.join(out_dir, video), os.path.join(out_dir, "qa"), cuts)
    except Exception as e:
        log("qa error", e)
    json.dump(meta, open(meta_p, "w"), indent=1, ensure_ascii=False)
    size = os.path.getsize(os.path.join(out_dir, video)) / 1e6
    log(f"rendered reel v2 {slug}: {total:.1f}s, {size:.1f} MB, music={has_music}")
    return True


def main(only=None):
    from playwright.sync_api import sync_playwright
    files = sorted(glob.glob(os.path.join(ROOT, "ig", "reels", "src", "*.json")))
    todo = []
    for f in files:
        slug = os.path.basename(f)[:-5]
        src = json.load(open(f, encoding="utf-8"))
        if src.get("v") == 2 and src.get("status") != "published" and (not only or slug == only):
            todo.append((slug, src))
    if not todo:
        return
    with sync_playwright() as p:
        b = p.chromium.launch()
        for slug, src in todo:
            LOG.clear()
            d = os.path.join(ROOT, "ig", "reels", slug)
            os.makedirs(d, exist_ok=True)
            LOG_PATH[0] = os.path.join(d, "log.txt")
            log("start", slug)
            try:
                render_one(slug, src, b)
            except Exception as e:
                import traceback
                log("reel v2 error", slug, repr(e), traceback.format_exc()[-1500:])
        b.close()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
