// Фон: прогулка по банку. Лёгкая линейная 3D-сцена на canvas, камера идёт вперёд вместе со скроллом.
// Вход → операционный зал с кассами → переговорные → хранилище в конце зала. Весит несколько килобайт, без картинок.
(function () {
  var cv = document.createElement("canvas");
  cv.className = "bank-bg"; cv.setAttribute("aria-hidden", "true");
  var ctx = cv.getContext("2d");
  if (!ctx) return;
  var reduce = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;

  var L = [];   // отрезки: [x1,y1,z1,x2,y2,z2,accent]
  var C = [];   // окружности в плоскости z: [x,y,z,r,accent]
  function seg(a, b, c, d, e, f, k) { L.push([a, b, c, d, e, f, k ? 1 : 0]); }
  function rect(x1, y1, x2, y2, z, k) { seg(x1, y1, z, x2, y1, z, k); seg(x2, y1, z, x2, y2, z, k); seg(x2, y2, z, x1, y2, z, k); seg(x1, y2, z, x1, y1, z, k); }
  function box(x1, y1, z1, x2, y2, z2, k) {
    rect(x1, y1, x2, y2, z1, k); rect(x1, y1, x2, y2, z2, k);
    seg(x1, y1, z1, x1, y1, z2, k); seg(x2, y1, z1, x2, y1, z2, k); seg(x1, y2, z1, x1, y2, z2, k); seg(x2, y2, z1, x2, y2, z2, k);
  }
  var W = 6, H = 4.4, END = 96, z, i;

  // зал: стены, пол, потолок
  seg(-W, 0, 0, -W, 0, END); seg(W, 0, 0, W, 0, END); seg(-W, H, 0, -W, H, END); seg(W, H, 0, W, H, END);
  for (i = -W + 1; i < W; i += 2) seg(i, 0, 0, i, 0, END);            // плитка вдоль
  for (z = 0; z <= END; z += 3) seg(-W, 0, z, W, 0, z);                 // плитка поперёк
  for (z = 6; z < END; z += 7) rect(-1.6, H, 1.6, H, z), seg(-1.6, H, z, -1.6, H, z + 3), seg(1.6, H, z, 1.6, H, z + 3), seg(-1.6, H, z + 3, 1.6, H, z + 3); // светильники
  for (z = 10; z < END - 6; z += 12) { box(-W, 0, z, -W + .7, H, z + .7); box(W - .7, 0, z, W, H, z + .7); } // колонны

  // вход: портал и стеклянные двери
  rect(-3.4, 0, 3.4, 3.6, 3, 1); rect(-3.4, 3.6, 3.4, 4.2, 3);
  seg(0, 0, 3, 0, 3.6, 3); seg(-1.7, 0, 3, -1.7, 3.6, 3); seg(1.7, 0, 3, 1.7, 3.6, 3);
  seg(-W, 3.6, 3, -3.4, 3.6, 3); seg(3.4, 3.6, 3, W, 3.6, 3);

  // операционный зал: кассы слева
  for (z = 16; z < 34; z += 3.6) {
    box(-W, 0, z, -3.6, 1.1, z + 3.2);                // стойка
    rect(-3.6, 1.1, -3.6, 2.3, z); seg(-3.6, 1.1, z, -3.6, 2.3, z); seg(-3.6, 2.3, z, -3.6, 2.3, z + 3.2); seg(-3.6, 1.1, z + 3.2, -3.6, 2.3, z + 3.2); // стекло
    rect(-4.9, 2.9, -4.9, 3.3, z + 1); seg(-4.9, 2.9, z + 1, -4.9, 2.9, z + 2.2, 1); seg(-4.9, 3.3, z + 1, -4.9, 3.3, z + 2.2, 1); // табло кассы
  }
  // стойки с лентами для очереди
  for (z = 17; z < 32; z += 3) {
    seg(-1.6, 0, z, -1.6, 1, z); seg(-.2, 0, z, -.2, 1, z);
    seg(-1.6, .9, z, -1.6, .9, z + 3, 1);
  }
  // диваны ожидания справа
  for (z = 18; z < 32; z += 6) { box(3.6, 0, z, 5.2, .45, z + 3.4); box(4.9, .45, z, 5.2, 1, z + 3.4); }

  // переговорные справа: стеклянные комнаты со столом
  for (z = 42; z < 66; z += 8) {
    box(2.2, 0, z, W, 3, z + 7, 1);
    box(3.2, .72, z + 2, 5, .78, z + 5);               // стол
    for (i = 0; i < 3; i++) { box(2.9, 0, z + 2.3 + i * 1.1, 3.1, .9, z + 2.6 + i * 1.1); box(5.1, 0, z + 2.3 + i * 1.1, 5.3, .9, z + 2.6 + i * 1.1); }
  }
  // банкоматы слева
  for (z = 44; z < 64; z += 4) { box(-W, 0, z, -5.2, 1.9, z + 1.6); rect(-5.2, 1.1, -5.2, 1.6, z + .3); seg(-5.2, 1.2, z + .3, -5.2, 1.2, z + 1.3, 1); }

  // хранилище: стена и круглая дверь
  seg(-W, 0, END, W, 0, END); seg(-W, H, END, W, H, END); seg(-W, 0, END, -W, H, END); seg(W, 0, END, W, H, END);
  rect(-2.6, 0, 2.6, 4, END);
  C.push([0, 2, END - .05, 1.8, 1], [0, 2, END - .05, 1.45, 0], [0, 2, END - .05, .35, 1]);
  for (i = 0; i < 6; i++) { var a = i * Math.PI / 3; seg(.35 * Math.cos(a), 2 + .35 * Math.sin(a), END - .05, 1.1 * Math.cos(a), 2 + 1.1 * Math.sin(a), END - .05, 1); }
  for (i = 0; i < 12; i++) { var b = i * Math.PI / 6; seg(1.45 * Math.cos(b), 2 + 1.45 * Math.sin(b), END - .05, 1.8 * Math.cos(b), 2 + 1.8 * Math.sin(b), END - .05); }

  var w, h, dpr, F, cx, cy, EYE = 1.65, NEAR = .6, camZ = 0, ticking = false;
  function resize() {
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    w = window.innerWidth; h = window.innerHeight;
    cv.width = w * dpr; cv.height = h * dpr; cv.style.width = w + "px"; cv.style.height = h + "px";
    F = Math.max(w, h * 1.1) * .62; cx = w / 2; cy = h * .5;
    draw();
  }
  function fog(d) { var t = d / 55; return Math.max(0, Math.min(1, 1 - t)) * Math.min(1, (d - NEAR) / 2.5); }
  function draw() {
    ticking = false;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    ctx.lineWidth = 1;
    for (var k = 0; k < L.length; k++) {
      var s = L[k], z1 = s[2] - camZ, z2 = s[5] - camZ;
      if (z1 < NEAR && z2 < NEAR) continue;
      var x1 = s[0], y1 = s[1], x2 = s[3], y2 = s[4];
      if (z1 < NEAR) { var t = (NEAR - z1) / (z2 - z1); x1 += (x2 - x1) * t; y1 += (y2 - y1) * t; z1 = NEAR; }
      else if (z2 < NEAR) { var u = (NEAR - z2) / (z1 - z2); x2 += (x1 - x2) * u; y2 += (y1 - y2) * u; z2 = NEAR; }
      var a = fog((z1 + z2) / 2);
      if (a <= .01) continue;
      ctx.strokeStyle = s[6] ? "rgba(14,122,130," + (a * .42).toFixed(3) + ")" : "rgba(14,27,44," + (a * .22).toFixed(3) + ")";
      ctx.beginPath();
      ctx.moveTo(cx + x1 / z1 * F, cy - (y1 - EYE) / z1 * F);
      ctx.lineTo(cx + x2 / z2 * F, cy - (y2 - EYE) / z2 * F);
      ctx.stroke();
    }
    for (var m = 0; m < C.length; m++) {
      var c = C[m], dz = c[2] - camZ;
      if (dz < NEAR) continue;
      var al = fog(Math.min(dz, 40));
      ctx.strokeStyle = c[4] ? "rgba(14,122,130," + (al * .4).toFixed(3) + ")" : "rgba(14,27,44," + (al * .2).toFixed(3) + ")";
      ctx.beginPath(); ctx.arc(cx + c[0] / dz * F, cy - (c[1] - EYE) / dz * F, c[3] / dz * F, 0, Math.PI * 2); ctx.stroke();
    }
  }
  function onScroll() {
    var max = Math.max(1, document.documentElement.scrollHeight - window.innerHeight);
    camZ = reduce ? 0 : Math.min(1, window.scrollY / max) * (END - 9);
    if (!ticking) { ticking = true; requestAnimationFrame(draw); }
  }
  document.addEventListener("DOMContentLoaded", function () {
    document.body.insertBefore(cv, document.body.firstChild);
    resize(); onScroll();
    window.addEventListener("resize", function () { resize(); onScroll(); });
    if (!reduce) window.addEventListener("scroll", onScroll, { passive: true });
  });
})();
