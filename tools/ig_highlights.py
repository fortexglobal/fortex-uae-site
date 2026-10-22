"""Обложки для Актуального Instagram (1080x1920, тёмно-синий и золото). Результат: ig/highlights/<n>.png"""
import os
from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S = 'fill="none" stroke="url(#g)" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"'
ICONS = {
    "1-scheta": f'<rect x="14" y="30" width="92" height="62" rx="10" {S}/><path d="M14 50h92M28 76h22" {S}/>',
    "2-vizy": f'<rect x="28" y="14" width="64" height="92" rx="8" {S}/><circle cx="60" cy="52" r="16" {S}/><path d="M44 52h32M60 36c-7 8-7 24 0 32M60 36c7 8 7 24 0 32M44 86h32" {S}/>',
    "3-kompanii": f'<path d="M22 106V30l38-16 38 16v76M10 106h100M40 46h8M72 46h8M40 64h8M72 64h8M52 106V84h16v22" {S}/>',
    "4-keisy": f'<rect x="12" y="36" width="96" height="66" rx="10" {S}/><path d="M44 36V26a6 6 0 0 1 6-6h20a6 6 0 0 1 6 6v10M12 62h96M56 62v10h8V62" {S}/>',
    "5-kak-rabotaem": f'<path d="M14 26h62a8 8 0 0 1 8 8v30a8 8 0 0 1-8 8H42L26 86V72H14a8 8 0 0 1-8-8V34a8 8 0 0 1 8-8z" {S}/><path d="M92 46h14a8 8 0 0 1 8 8v26a8 8 0 0 1-8 8h-6v12L86 88H64" {S}/>',
    "6-voprosy": f'<circle cx="60" cy="60" r="46" {S}/><path d="M46 48a14 14 0 1 1 20 12c-4 2-6 5-6 9v3" {S}/><circle cx="60" cy="86" r="2.5" fill="#D4B061"/>',
}


def html(svg):
    return f'''<!doctype html><html><body style="margin:0;width:1080px;height:1920px;background:radial-gradient(900px 900px at 50% 45%,#1A2E48 0%,#0B1626 70%);display:flex;align-items:center;justify-content:center">
<div style="width:820px;height:820px;border-radius:50%;border:5px solid rgba(212,176,97,.55);display:flex;align-items:center;justify-content:center;background:radial-gradient(circle,#16294A,#0B1626)">
<svg width="470" height="470" viewBox="0 0 120 120"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#F3E6C4"/><stop offset="1" stop-color="#C9A24B"/></linearGradient></defs>{svg}</svg></div></body></html>'''


with sync_playwright() as p:
    b = p.chromium.launch()
    for name, svg in ICONS.items():
        pg = b.new_page(viewport={"width": 1080, "height": 1920})
        pg.set_content(html(svg)); pg.wait_for_timeout(150)
        pg.screenshot(path=os.path.join(ROOT, "ig", "highlights", name + ".png")); pg.close()
    b.close()
