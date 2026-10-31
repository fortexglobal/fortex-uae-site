"""Картинки документов для блока «Собираем инфраструктуру» (паспорт, Emirates ID, карта). GitHub Actions → research/docs/."""
import base64, json, os, sys, urllib.request
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
KEY = os.environ["OPENROUTER_API_KEY"]
OUT = os.path.join(ROOT, "research", "docs"); os.makedirs(OUT, exist_ok=True)
BG = "on a seamless perfectly uniform flat light grey studio background (#e6e9ee), soft even diffused light, a very subtle soft contact shadow, ultra sharp, high detail, top-down view, the object lies perfectly straight and axis-aligned (not rotated, not tilted), centered, filling about 75% of the frame, no hands, no other objects, no props."
JOBS = {
 "passport": ("3:4", "Studio product photo of a closed Russian Federation biometric international passport: deep burgundy red textured leatherette cover, gold foil embossed double-headed eagle coat of arms in a shield frame in the middle, gold text 'РОССИЙСКАЯ ФЕДЕРАЦИЯ' and 'RUSSIAN FEDERATION' at the top, gold text 'ПАСПОРТ' and 'PASSPORT' below the emblem, small gold biometric chip symbol at the bottom, slightly rounded corners. " + BG),
 "eid": ("4:3", "Studio product photo of a generic United Arab Emirates resident identity card mockup: credit-card shaped plastic card with rounded corners, pale lavender and light blue guilloche security pattern, a small gold falcon emblem at top center, header text 'UNITED ARAB EMIRATES' and 'Resident Identity Card' on the left top, the photo box on the left shows only a neutral grey head-and-shoulders silhouette icon, all personal data fields are empty light lines with no names, no numbers, no dates and no signature. " + BG),
 "card": ("4:3", "Studio product photo of a premium matte black metal bank card with rounded corners and a subtle navy-to-emerald gradient sheen across it, gold EMV chip, small contactless symbol, card number shown only as four groups of dots, thin gold wordmark 'FORTEX' in the top left, no bank logos and no payment network logos. " + BG),
}
which = sys.argv[1:] or list(JOBS)
for name in which:
    ar, prompt = JOBS[name]
    for v in (1, 2):
        body = json.dumps({"model": "google/gemini-3-pro-image-preview", "modalities": ["image", "text"],
                           "image_config": {"aspect_ratio": ar},
                           "messages": [{"role": "user", "content": prompt}]}).encode()
        req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", body, {
            "Authorization": f"Bearer {KEY}", "Content-Type": "application/json", "HTTP-Referer": "https://fortex-uae.com", "X-Title": "Fortex docs"})
        try:
            r = json.load(urllib.request.urlopen(req, timeout=240))
            imgs = r["choices"][0]["message"].get("images") or []
            if not imgs:
                print(name, v, "no image", str(r)[:300]); continue
            open(os.path.join(OUT, f"{name}{v}.png"), "wb").write(base64.b64decode(imgs[0]["image_url"]["url"].split(",", 1)[1]))
            print("ok", name, v)
        except Exception as e:
            print(name, v, "error", getattr(e, "read", lambda: b"")()[:300] or e)
