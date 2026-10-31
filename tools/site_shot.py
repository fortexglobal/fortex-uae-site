"""Скриншоты сайта для разбора дизайна: python3 tools/site_shot.py <url> <name> → research/<name>/"""
import os, sys
from playwright.sync_api import sync_playwright
url, name = sys.argv[1], sys.argv[2]
d = f"research/{name}"; os.makedirs(d, exist_ok=True)
with sync_playwright() as pw:
    b = pw.chromium.launch()
    for pre, w, h in (("s", 1440, 900), ("m", 390, 844)):
        p = b.new_page(viewport={"width": w, "height": h})
        try:
            p.goto(url, wait_until="networkidle", timeout=90000)
        except Exception as e:
            print("goto", e)
        p.wait_for_timeout(4000)
        H = p.evaluate("document.documentElement.scrollHeight")
        y = 0
        while y < H:
            p.evaluate(f"window.scrollTo(0,{y})"); p.wait_for_timeout(300); y += int(h * 0.6)
        for i in range(min(14, -(-H // h))):
            p.evaluate(f"window.scrollTo(0,{i*h})"); p.wait_for_timeout(1200)
            p.screenshot(path=f"{d}/{pre}{i:02d}.png")
        if pre == "s":
            open(f"{d}/page.html", "w").write(p.content())
            css = p.evaluate("""[...document.styleSheets].map(s=>{try{return [...s.cssRules].map(r=>r.cssText).join('\\n')}catch(e){return ''}}).join('\\n')""")
            open(f"{d}/styles.css", "w").write(css)
        print(pre, H)
        p.close()
    b.close()
