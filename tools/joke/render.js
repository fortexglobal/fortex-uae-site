const { chromium } = require('playwright');
const fs = require('fs');
const F = process.argv[2];
const spec = JSON.parse(fs.readFileSync(process.argv[3]));
const mr = ['cyrillic','latin'].map(s => `@font-face{font-family:'Manrope';font-weight:700;src:url(data:font/woff2;base64,${fs.readFileSync(`${F}/manrope/files/manrope-${s}-700-normal.woff2`).toString('base64')}) format('woff2')}`).join('');
const css = ['playfair-display/600.css','playfair-display/600-italic.css']
  .map(f => `<link rel="stylesheet" href="file://${F}/${f}">`).join('') + `<style>${mr}</style>`;
(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1080, height: 1920 } });
  for (const c of spec.cards) {
    const html = `<html><head>${css}<style>
      html,body{margin:0;background:transparent;width:1080px;height:1920px;overflow:hidden}
      .band{position:absolute;left:0;right:0;top:${c.y - 330}px;height:660px;
        background:radial-gradient(ellipse 75% 50% at 50% 50%,rgba(0,0,0,.62),rgba(0,0,0,.35) 55%,rgba(0,0,0,0) 100%)}
      .wrap{position:absolute;left:70px;right:70px;top:${c.y}px;transform:translateY(-50%);text-align:center;color:#fff}
      .rule{width:64px;height:2px;margin:0 auto 34px;background:linear-gradient(90deg,transparent,#E9C46A,transparent)}
      .l1{font-family:'Playfair Display';font-weight:600;font-size:${c.s1||74}px;line-height:1.12;letter-spacing:-.5px;text-shadow:0 2px 18px rgba(0,0,0,.55)}
      .l2{margin-top:14px;font-family:'Playfair Display';font-style:italic;font-weight:600;font-size:${c.s2||68}px;line-height:1.15;color:#EFCB7B;text-shadow:0 2px 18px rgba(0,0,0,.6)}
      .site{margin-top:40px;display:inline-block;font-family:'Manrope';font-weight:700;font-size:36px;letter-spacing:4px;text-transform:uppercase;color:#fff;
        padding:16px 34px;border:1.5px solid rgba(239,203,123,.85);border-radius:999px;background:rgba(0,0,0,.35)}
    </style></head><body><div class="band"></div><div class="wrap"><div class="rule"></div>
      <div class="l1">${c.l1}</div>${c.l2 ? `<div class="l2">${c.l2}</div>` : ''}${c.site ? `<div class="site">${c.site}</div>` : ''}</div></body></html>`;
    await p.setContent(html, { waitUntil: 'networkidle' });
    await p.evaluate(() => document.fonts.ready);
    await p.screenshot({ path: c.out, omitBackground: true });
  }
  await b.close();
})();
