"""Монтаж теста рилса Buzzy: сток (первые секунды) + ИИ-герой под озвучку, субтитры по 2–3 слова, звуки.
python3 tools/reel_buzzy_edit.py hero.mp4 stock.mp4 voice.mp3 out.mp4"""
import subprocess, sys, os, tempfile

hero, stock, voice, out = sys.argv[1:5]
CUT = 2.39  # смена кадра: сток -> герой
W, H = 1080, 1920
Y = "&H0000D7FF&"  # жёлтый (BGR)
# (начало, конец, текст); {Y}…{W} = жёлтым
SUBS = [
    (0.00, 0.75, "СЧЁТ В ДУБАЕ,"),
    (0.75, 1.30, "НЕ ПРИЛЕТАЯ"),
    (1.30, 2.30, "В ДУБАЙ?"),
    (2.39, 3.05, "{Y}РЕАЛЬНО{W}"),
    (3.08, 3.95, "{Y}EMIRATES NBD{W}"),
    (3.95, 4.80, "ОТКРЫЛИ УДАЛЁННО"),
    (4.80, 5.90, "ЗА {Y}2 НЕДЕЛИ{W}"),
    (5.96, 7.00, "БЕЗ EMIRATES ID"),
    (7.00, 8.10, "И {Y}БЕЗ ПОЕЗДКИ{W}"),
    (8.15, 9.15, "ПИШИТЕ В TELEGRAM"),
    (9.15, 10.4, "{Y}@FORTEX_DUBAI{W}"),
]
POP_AT = 4.80


def ts(t):
    return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"


tmp = tempfile.mkdtemp()
ass = os.path.join(tmp, "s.ass")
with open(ass, "w", encoding="utf-8") as f:
    f.write(f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: S,Inter ExtraBold,86,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,6,3,5,80,80,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
""")
    for a, b, t in SUBS:
        t = t.replace("{Y}", "{\\c" + Y + "}").replace("{W}", "{\\c&H00FFFFFF&}")
        # позиция: 62% высоты (выше подписи и кнопок Reels), лёгкий «поп» при появлении
        f.write(f"Dialogue: 0,{ts(a)},{ts(b)},S,,0,0,0,,{{\\pos({W // 2},{int(H * 0.62)})\\fscx88\\fscy88\\t(0,90,\\fscx100\\fscy100)}}{t}\n")

# звуки: whoosh на смене кадра, «поп» на «2 недели», тихий фон
wh = os.path.join(tmp, "wh.wav"); pop = os.path.join(tmp, "pop.wav"); bg = os.path.join(tmp, "bg.wav")
subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "anoisesrc=d=0.45:c=pink:a=0.6",
                "-af", "highpass=f=400,lowpass=f=6000,afade=t=in:d=0.3,afade=t=out:st=0.3:d=0.15,volume=0.35", wh], check=True)
subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=f=880:d=0.09",
                "-af", "afade=t=out:st=0.02:d=0.07,volume=0.5", pop], check=True)
subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=f=110:d=10.5", "-f", "lavfi", "-i", "sine=f=164.8:d=10.5",
                "-f", "lavfi", "-i", "sine=f=220:d=10.5", "-filter_complex",
                "[0][1][2]amix=inputs=3,tremolo=f=0.25:d=0.4,lowpass=f=900,afade=t=in:d=1,afade=t=out:st=9.5:d=1,volume=0.06", bg], check=True)

dur = 10.4
fc = (
    f"[1:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps=30,trim=0:{CUT},setpts=PTS-STARTPTS,"
    f"eq=brightness=0.04:saturation=1.1[s];"
    f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps=30,trim={CUT}:{dur},setpts=PTS-STARTPTS[h];"
    f"[s][h]concat=n=2:v=1:a=0,ass={ass}[v];"
    f"[2:a]volume=1.0[vo];[3:a]adelay={int((CUT - 0.25) * 1000)}|{int((CUT - 0.25) * 1000)}[w];"
    f"[4:a]adelay={int(POP_AT * 1000)}|{int(POP_AT * 1000)}[p];"
    f"[vo][w][p][5:a]amix=inputs=4:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=9[a]"
)
subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", hero, "-i", stock, "-i", voice, "-i", wh, "-i", pop, "-i", bg,
                "-filter_complex", fc, "-map", "[v]", "-map", "[a]", "-t", str(dur),
                "-c:v", "libx264", "-crf", "19", "-preset", "medium", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
                "-movflags", "+faststart", out], check=True)
print("ok", out)
