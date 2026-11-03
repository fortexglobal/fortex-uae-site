const { chromium } = require('playwright'); const fs = require('fs');
const R = process.argv[2], F = R + '/fonts/node_modules/@fontsource/manrope/files', C = R + '/cards';
const ff = w => ['cyrillic','latin'].map(s => `@font-face{font-family:M;font-weight:${w};src:url(data:font/woff2;base64,${fs.readFileSync(`${F}/manrope-${s}-${w}-normal.woff2`).toString('base64')}) format('woff2')}`).join('');
const b64 = f => `data:image/jpeg;base64,${fs.readFileSync(f).toString('base64')}`;
const HL = [['СЧЕТА','#fff'],['КОМПАНИИ','#fff'],['ВИЗЫ','#fff'],['КЕЙСЫ','#0B1626'],['ВОПРОСЫ','#fff'],['О НАС','#fff']];
const pin = `<svg viewBox="0 0 24 24" width="34" height="34" style="position:absolute;top:14px;right:14px;filter:drop-shadow(0 1px 2px rgba(0,0,0,.5))"><path fill="#fff" d="M16 3l5 5-3 1-4 4 1 5-2 2-4-4-5 5-1-1 5-5-4-4 2-2 5 1 4-4z"/></svg>`;
const tiles = [0,1,2].map(i => `<div style="position:relative"><img src="${b64(`${C}/${process.argv[3]}_${i}.jpg`)}">${pin}</div>`).join('') +
  (process.argv[5] ? JSON.parse(fs.readFileSync(process.argv[5])) : Array.from({length:9},(_, i) => `s${String(i).padStart(2,'0')}`)).map(n => `<div><img src="${b64(`${C}/${n}.jpg`)}"></div>`).join('');
const html = `<html><head><style>${[300,400,600,700,800].map(ff).join('')}
*{box-sizing:border-box;margin:0}body{width:1080px;background:#fff;font-family:M;color:#111}
.top{padding:40px 40px 10px;display:flex;align-items:center;gap:60px}
.av{width:190px;height:190px;border-radius:50%;background:#0B1626;display:flex;align-items:center;justify-content:center;color:#C9A45C;font-weight:800;font-size:96px;box-shadow:0 0 0 6px #fff,0 0 0 8px #ddd}
.st{display:flex;gap:70px;text-align:center}.st b{display:block;font-size:40px;font-weight:700}.st span{font-size:28px;color:#555}
.bio{padding:20px 40px 0;font-size:30px;line-height:1.45}.bio .n{font-weight:700}.bio a{color:#00376B;font-weight:600;text-decoration:none}
.btns{display:flex;gap:14px;padding:26px 40px}.btns div{flex:1;background:#EFEFEF;border-radius:14px;text-align:center;padding:18px;font-weight:600;font-size:28px}
.hl{display:flex;gap:30px;padding:16px 40px 30px}.hl div{text-align:center;font-size:24px;color:#111}
.c{width:136px;height:136px;border-radius:50%;border:2px solid #ddd;padding:5px;margin-bottom:10px}
.c i{display:flex;width:100%;height:100%;border-radius:50%;align-items:center;justify-content:center;font-style:normal;font-weight:800;font-size:20px;letter-spacing:.5px;color:#8A6A3A}
.tabs{border-top:1px solid #ddd;display:flex;justify-content:space-around;padding:20px 0;font-size:26px;font-weight:700;color:#999}.tabs .on{color:#111}
.g{display:grid;grid-template-columns:repeat(3,1fr);gap:3px}.g img{width:100%;aspect-ratio:3/4;object-fit:cover;display:block}
</style></head><body>
<div class="top"><div class="av">F</div><div><div style="font-size:34px;font-weight:700;margin-bottom:22px">fortex__uae</div><div class="st"><div><b>58</b><span>публикаций</span></div><div><b>1 250</b><span>подписчиков</span></div><div><b>180</b><span>подписок</span></div></div></div></div>
<div class="bio"><div class="n">Счета в банках ОАЭ | Fortex UAE</div>
▪️ Личные и корпоративные счета в ОАЭ<br>▪️ Компании, рабочие визы, Emirates ID<br>▪️ Сложные случаи и отказы банков<br>▪️ В Дубае с 2022 года<br><a>🌐 fortex-uae.com</a></div>
<div class="btns"><div>Подписаться</div><div>Написать</div><div>Контакты</div></div>
<div class="hl">${HL.map(([t,bg]) => `<div><div class="c"><i style="background:${bg};${bg!=='#fff'?'color:#C9A45C':''}">${t}</i></div>${t[0]+t.slice(1).toLowerCase()}</div>`).join('')}</div>
<div class="tabs"><span class="on">▦ ПУБЛИКАЦИИ</span><span>▶ REELS</span><span>☺ ОТМЕТКИ</span></div>
<div class="g">${tiles}</div></body></html>`;
(async () => {
  const b = await chromium.launch(); const p = await b.newPage({ viewport: { width: 1080, height: 800 } });
  await p.setContent(html); await p.evaluate(() => document.fonts.ready);
  await p.screenshot({ path: `${R}/${process.argv[4]}`, type: 'jpeg', quality: 88, fullPage: true });
  await b.close();
})();
