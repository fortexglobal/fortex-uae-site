import sys, numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance, ImageChops
src, out, F800, FL, FB, FILL = sys.argv[1:7]
W, H = 3240, 1440
def cover(im, w, h):
    r = max(w / im.width, h / im.height); im = im.resize((round(im.width * r), round(im.height * r)), Image.LANCZOS)
    l = (im.width - w) // 2; t = (im.height - h) // 2; return im.crop((l, t, l + w, t + h))
im = cover(Image.open(src).convert("RGB"), W, H)
g = np.asarray(im.filter(ImageFilter.GaussianBlur(2.5))).astype(float).mean(2)
e = np.maximum(np.abs(np.diff(g, axis=0, prepend=g[:1])), np.abs(np.diff(g, axis=1, prepend=g[:, :1])))
e = np.asarray(Image.fromarray(np.clip(e * 4, 0, 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(5))).astype(float) / 4
mask = np.zeros((H, W), np.uint8)
for x in range(W):
    hit = np.where(e[:, x] > 9)[0]; mask[:(hit[0] if len(hit) else H), x] = 255
sky = Image.fromarray(mask).filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(1.2))
T = Image.new("L", (W, H), 0); d = ImageDraw.Draw(T); f = ImageFont.truetype(F800, 760)
bb = d.textbbox((0, 0), "Fortex", font=f); x0 = (W - (bb[2] - bb[0])) // 2 - bb[0]; y0 = 100 - bb[1]
d.text((x0, y0), "Fortex", font=f, fill=255)
txt = ImageChops.multiply(T, sky)                      # буквы за небоскрёбами
edge = ImageChops.multiply(ImageChops.subtract(T.filter(ImageFilter.MaxFilter(7)), T.filter(ImageFilter.MinFilter(7))), sky)
def finish(base, name):
    base = base.convert("RGBA")
    grad = Image.new("L", (1, H)); [grad.putpixel((0, y), int(150 * max(0, (y - H * .62) / (H * .38)))) for y in range(H)]
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 255)); sh.putalpha(grad.resize((W, H))); base = Image.alpha_composite(base, sh)
    d = ImageDraw.Draw(base); fl = ImageFont.truetype(FL, 40); fb = ImageFont.truetype(FB, 40)
    for i, (a, b) in enumerate([("В ДУБАЕ", "С 2022 ГОДА"), ("СЧЕТА · КОМПАНИИ", "ВИЗЫ · EMIRATES ID"), ("ПИШИТЕ:", "FORTEX-UAE.COM")]):
        for j, (s, fn) in enumerate([(a, fl), (b, fb)]):
            q = d.textbbox((0, 0), s, font=fn); d.text((i * 1080 + 540 - (q[2] - q[0]) / 2, H - 200 + j * 56), s, font=fn, fill="white")
    base = base.convert("RGB"); base.save(f"{out}_{name}_pano.jpg", quality=92)
    for i in range(3): base.crop((i * 1080, 0, (i + 1) * 1080, H)).save(f"{out}_{name}_{i}.jpg", quality=92)
# A: внутри букв ночной Дубай (день снаружи, ночь внутри)
night = cover(Image.open(FILL).convert("RGB"), W, H)
night = ImageEnhance.Brightness(night).enhance(1.15)
a = im.copy(); a.paste(night, (0, 0), txt)
a.paste(Image.new("RGB", (W, H), (255, 255, 255)), (0, 0), edge.point(lambda v: v * .9))
finish(a, "night")
# B: матовое стекло
glass = ImageEnhance.Brightness(im.filter(ImageFilter.GaussianBlur(22))).enhance(1.18)
b = im.copy(); b.paste(glass, (0, 0), txt.point(lambda v: v * .92))
b.paste(Image.new("RGB", (W, H), (255, 255, 255)), (0, 0), edge.point(lambda v: v * .85))
finish(b, "glass")
# C: золото с мягким бликом
yy = np.linspace(0, 1, H)[:, None]
top, mid, bot = np.array([250, 236, 200]), np.array([214, 175, 98]), np.array([150, 108, 45])
col = np.where((yy < .45)[..., None], top + (mid - top) * (yy / .45)[..., None], mid + (bot - mid) * ((yy - .45) / .55)[..., None]).astype(float)
col = np.broadcast_to(col, (H, W, 3)).copy()
xx = np.linspace(0, 1, W)[None, :]; shine = np.exp(-((xx - .35 - yy * .4) ** 2) / .002)[..., None] * 70
gold = Image.fromarray(np.clip(col + shine, 0, 255).astype(np.uint8))
c = im.copy()
shadow = txt.filter(ImageFilter.GaussianBlur(14)).point(lambda v: v * .35)
c.paste(Image.new("RGB", (W, H), (60, 40, 10)), (12, 16), shadow)
c.paste(gold, (0, 0), txt)
finish(c, "gold")
print("ok")
