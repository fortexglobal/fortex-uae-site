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
import base64, concurrent.futures, glob, hashlib, json, os, re, subprocess, sys, tempfile, time, urllib.request, urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

W, H, FPS = 1080, 1920, 30
FAL_KEY = os.environ.get("FAL_KEY", "")
EL_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
DRY = os.environ.get("REEL_DRY") == "1"
FAL_MODELS = ["fal-ai/kling-video/v2.5-turbo/pro/text-to-video", "fal-ai/kling-video/v1.6/standard/text-to-video"]
DEFAULT_VOICE = os.environ.get("REEL_VOICE_ID", "pNInz6obpgDQGcFmaJgB")  # Adam: глубокий мужской, хорошо читает по-русски на multilingual_v2
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
              "voice_settings": {"stability": 0.38, "similarity_boost": 0.8, "style": 0.35, "use_speaker_boost": True, "speed": 1.08}},
             {"xi-api-key": EL_KEY}, timeout=300)
    open(out_mp3, "wb").write(base64.b64decode(r["audio_base64"]))
    return r.get("alignment") or r.get("normalized_alignment")


# ---------- музыка ----------
def music(prompt, secs, out_mp3):
    if DRY or not prompt:
        return False
    p = prompt + ". Instrumental only, no vocals, punchy intro in the first second, modern, for a short vertical video"
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


def chunks_of(words):
    res, cur = [], []
    for w in words:
        cur.append(w)
        text_len = sum(len(x["w"]) + 1 for x in cur)
        if len(cur) >= 3 or text_len >= 17 or re.search(r"[.,!?:;…]$", w["w"]):
            res.append(cur); cur = []
    if cur:
        res.append(cur)
    return res


def t_ass(t):
    t = max(0, t)
    return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"


def esc(s):
    return s.replace("\\", "").replace("{", "(").replace("}", ")")


def build_ass(words, hook, accent, hook_end, cap_end, total):
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,Inter Display ExtraBold,86,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,6,0,5,80,80,0,1
Style: Hook,Inter Display ExtraBold,92,&H00FFFFFF,&H00FFFFFF,&H00261610,&H00000000,0,0,0,0,100,100,-1,0,3,26,0,8,90,90,330,1
Style: Brand,Inter Display ExtraBold,34,&H3061A2C9,&H3061A2C9,&H00000000,&H00000000,0,0,0,0,100,100,4,0,1,2,0,7,76,76,250,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ev = [f"Dialogue: 0,{t_ass(0)},{t_ass(cap_end)},Brand,,0,0,0,,FORTEX UAE"]
    if hook:
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
                parts.append("{\\c" + gold + "\\fscx108\\fscy108}" + t + "{\\c&HFFFFFF&\\fscx100\\fscy100}" if j == i else t)
            pop = "{\\pos(540,1150)" + ("\\fscx88\\fscy88\\t(0,90,\\fscx100\\fscy100)" if i == 0 else "") + "}"
            ev.append(f"Dialogue: 1,{t_ass(s)},{t_ass(e)},Cap,,0,0,0,,{pop}{' '.join(parts)}")
    return head + "\n".join(ev) + "\n"


# ---------- сборка ----------
def render_one(slug, src, browser):
    out_dir = os.path.join(ROOT, "ig", "reels", slug)
    os.makedirs(out_dir, exist_ok=True)
    shots = src["shots"][:7]
    cta = src.get("cta") or {"title": "Подпишись", "text": "Новости Дубая для предпринимателей каждый день", "say": "Подписывайся, чтобы быть в курсе."}
    h = key(src.get("hook"), src.get("accent"), shots, cta, src.get("music"), src.get("voice_id"), "v2.5", DRY)[:10]
    meta_p = os.path.join(out_dir, "render.json")
    if os.path.exists(meta_p) and json.load(open(meta_p)).get("hash") == h:
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
    vk = key(text, vid, DRY)
    voice_mp3 = os.path.join(out_dir, "voice.mp3")
    if cache.get("voice") == vk and os.path.exists(voice_mp3) and cache.get("align"):
        al = cache["align"]
    else:
        al = tts(text, vid, voice_mp3)
        cache.update(voice=vk, align=al)
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

    def get(i):
        need = shot_seg[i][1] - shot_seg[i][0]
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

    with concurrent.futures.ThreadPoolExecutor(4) as ex:
        list(ex.map(get, range(n_shot)))
    json.dump(cache, open(cache_p, "w"), ensure_ascii=False)

    # 3. музыка
    music_mp3 = os.path.join(out_dir, "music.mp3")
    mk = key(src.get("music"), round(total))
    has_music = cache.get("music") == mk and os.path.exists(music_mp3)
    if not has_music:
        has_music = music(src.get("music"), total, music_mp3)
        if has_music:
            cache["music"] = mk
    json.dump(cache, open(cache_p, "w"), ensure_ascii=False)

    # 4. нарезка кадров под фразы
    XF = 0.28
    TRANS = ["smoothleft", "zoomin", "smoothup", "slideleft", "smoothright", "circleopen"]
    parts = []
    for i, (a, b) in enumerate(shot_seg):
        d = b - a + (XF if i + 1 < len(shot_seg) else 0)
        cl = probe_dur(paths[i]) or 5
        slow = min(max(d / cl, 1.0), 1.5)
        part = os.path.join(tmp, f"p{i}.mp4")
        punch = "1.0+0.04*t/%.2f" % d
        ff(["-i", paths[i], "-vf",
            f"setpts={slow:.3f}*PTS,scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,fps={FPS},"
            f"tpad=stop_mode=clone:stop_duration=6,"
            f"scale=w='iw*({punch})':h='ih*({punch})':eval=frame,crop={W}:{H},"
            f"eq=contrast=1.06:saturation=1.08,format=yuv420p",
            "-t", f"{d:.3f}", "-an", "-r", str(FPS), "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", part])
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
    pg = browser.new_page(viewport={"width": W, "height": H})
    pg.set_content(reel_render.scene_html({"type": "cta", "title": cta["title"], "text": cta.get("text", "")})); pg.wait_for_timeout(250)
    pg.screenshot(path=ov, omit_background=True); pg.close()
    hook_end = min(2.8, shot_seg[1][0] if n_shot > 1 else 2.8)
    ass = os.path.join(tmp, "subs.ass")
    open(ass, "w", encoding="utf-8").write(build_ass(words_from(al, alts), src.get("hook"), src.get("accent"), hook_end, cta_start, total))

    for old in glob.glob(os.path.join(out_dir, "*.mp4")):
        os.remove(old)
    video = f"{h}.mp4"
    inputs = ["-i", base, "-loop", "1", "-t", f"{total:.2f}", "-i", ov, "-i", voice_mp3]
    vf = (f"[0]drawbox=x=0:y=0:w=iw:h=ih:color=black@0.38:t=fill:enable='gte(t,{cta_start:.2f})'[bd];"
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
        vol = 0.9 if name == "click" else 0.55
        sfx_f.append(f"[{nxt}]aresample=44100,volume={vol},adelay={int(t * 1000)}:all=1[s{nxt}]")
        nxt += 1
    labels = "".join(f"[s{k}]" for k in range(4 if has_music else 3, nxt))
    sfx_mix = (";".join(sfx_f) + f";{labels}amix=inputs={len(sfx_f)}:duration=longest:normalize=0[fx]") if sfx_f else ""
    if has_music:
        inputs += ["-stream_loop", "-1", "-i", music_mp3]
        af = (f"[2]aresample=44100,apad,asplit=2[vo][sc];"
              f"[3]aresample=44100,volume=0.30,afade=t=in:d=0.3,afade=t=out:st={total - 1.2:.2f}:d=1.2[mu];"
              f"[mu][sc]sidechaincompress=threshold=0.02:ratio=9:attack=15:release=350[duck];")
        mix_in = "[vo][duck]"; n_in = 2
    else:
        af = "[2]aresample=44100,apad[vo];"
        mix_in = "[vo]"; n_in = 1
    if sfx_mix:
        af += sfx_mix + ";"
        mix_in += "[fx]"; n_in += 1
    af += f"{mix_in}amix=inputs={n_in}:duration=first:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=11[a]"
    inputs += sfx_in
    ff(inputs + ["-filter_complex", vf + ";" + af, "-map", "[v]", "-map", "[a]", "-t", f"{total:.2f}",
                 "-c:v", "libx264", "-preset", "medium", "-crf", "22", "-maxrate", "4.5M", "-bufsize", "9M", "-pix_fmt", "yuv420p",
                 "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-movflags", "+faststart", os.path.join(out_dir, video)])
    ff(["-ss", "0.9", "-i", os.path.join(out_dir, video), "-frames:v", "1", "-q:v", "3", os.path.join(out_dir, "cover.jpg")])
    json.dump({"hash": h, "video": video, "cover": "cover.jpg", "v": 2, "duration": round(total, 1)}, open(meta_p, "w"), indent=1)
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
