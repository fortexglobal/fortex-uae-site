const { chromium } = require('playwright'); const fs = require('fs');
const R = process.argv[2], F = R + '/fonts/node_modules/@fontsource/manrope/files', C = R + '/cards';
const ff = w => ['cyrillic','latin'].map(s => `@font-face{font-family:M;font-weight:${w};src:url(data:font/woff2;base64,${fs.readFileSync(`${F}/manrope-${s}-${w}-normal.woff2`).toString('base64')}) format('woff2')}`).join('');
const css = `<style>${[300,400,600,700,800].map(ff).join('')}
*{box-sizing:border-box;margin:0}body{width:1080px;height:1440px;position:relative;overflow:hidden;font-family:M;color:#fff}
.ph{position:absolute;inset:0;background-size:cover;background-position:center}
.wm{font-weight:800;font-size:46px;letter-spacing:-1.5px}
.up{text-transform:uppercase;letter-spacing:1px;line-height:1.28}
.l{font-weight:300}.b{font-weight:800}
.gold{color:#8A6A3A}</style>`;
const img = n => `url(data:image/jpeg;base64,${fs.readFileSync(n.includes('/')?n:`${C}/p_${n}.jpg`).toString('base64')})`;
const tpl = {
 S1: c => `<div class="ph" style="background-image:${img(c.p)}"></div><div class="ph" style="background:linear-gradient(180deg,rgba(0,0,0,.42),rgba(0,0,0,0) 45%)"></div>
  <div style="position:absolute;top:90px;width:100%;text-align:center"><div class="wm">Fortex</div>
  <div class="up" style="margin:46px auto 0;width:840px;font-size:46px"><span class="l">${c.a}</span><br><span class="b">${c.b}</span></div>
  ${c.box?`<div style="display:inline-block;margin-top:40px;border:1.5px solid #fff;padding:14px 28px;font-size:26px;font-weight:400">${c.box}</div>`:''}</div>`,
 S2: c => `<div class="ph" style="background-image:${img(c.p)}"></div><div class="ph" style="background:linear-gradient(0deg,rgba(0,0,0,.7),rgba(0,0,0,0) 60%)"></div>
  <div style="position:absolute;left:90px;right:90px;bottom:110px;height:430px;border:1.5px solid rgba(255,255,255,.85)"></div>
  <div style="position:absolute;left:130px;right:130px;bottom:170px;text-align:center"><div class="up" style="font-size:44px"><span class="l">${c.a}</span><br><span class="b">${c.b}</span></div></div>
  <div class="wm" style="position:absolute;top:80px;width:100%;text-align:center">Fortex</div>`,
 S3: c => `<div class="ph" style="background:#F7F4EE"></div>
  <div class="wm gold" style="position:absolute;left:90px;top:70px;color:#1A1A1A">Fortex</div>
  <div style="position:absolute;left:290px;right:70px;top:100px;height:1.5px;background:#B89A63"></div>
  <div style="position:absolute;right:70px;top:100px;height:520px;width:1.5px;background:#B89A63"></div>
  <div style="position:absolute;left:90px;right:140px;top:190px"><div class="up gold" style="font-size:62px;line-height:1.12;letter-spacing:0"><span class="b">${c.a}</span><br><span class="l">${c.b}</span></div>
  <div style="margin-top:34px;font-size:30px;line-height:1.4;color:#333;font-weight:400">${c.sub||''}</div></div>
  <div class="ph" style="left:90px;right:90px;top:auto;bottom:90px;height:640px;background-image:${img(c.p)}"></div>`,
 S4: c => `<div class="ph" style="background-image:${img(c.p)}"></div><div class="ph" style="background:linear-gradient(0deg,rgba(0,0,0,.78),rgba(0,0,0,0) 55%)"></div>
  <div style="position:absolute;left:90px;right:90px;bottom:200px;text-align:center"><div class="up" style="font-size:46px"><span class="b">${c.a}</span><br><span class="l">${c.b}</span></div>
  ${c.sub?`<div style="margin-top:22px;font-size:28px;font-weight:300">${c.sub}</div>`:''}</div>
  <div class="wm" style="position:absolute;bottom:90px;width:100%;text-align:center;font-size:40px">Fortex</div>`,
};
const T = JSON.parse(fs.readFileSync(`${C}/${process.argv[3]||'sol_tiles.json'}`)); const PFX = process.argv[4]||'s';
(async () => {
  const b = await chromium.launch(); const p = await b.newPage({ viewport: { width: 1080, height: 1440 } });
  for (let i = 0; i < T.length; i++) {
    await p.setContent(`<html><head>${css}</head><body>${tpl[T[i].t](T[i])}</body></html>`);
    await p.evaluate(() => document.fonts.ready);
    await p.screenshot({ path: `${C}/${PFX}${String(i).padStart(2,'0')}.jpg`, type: 'jpeg', quality: 90 });
  }
  await b.close();
})();
