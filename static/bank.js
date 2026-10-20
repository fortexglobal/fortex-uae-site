// Фон: прогулка по светлому банку. Объёмная сцена на canvas (заливки, свет, отражения в полу),
// камера идёт вперёд вместе со скроллом. Вход → кассы → переговорные → хранилище. Без картинок, ~10 КБ.
(function () {
  if (document.documentElement.classList.contains("has-video")) return; // есть видео-фон, рисованный зал не нужен
  var cv = document.createElement("canvas");
  cv.className = "bank-bg"; cv.setAttribute("aria-hidden", "true");
  var ctx = cv.getContext("2d");
  if (!ctx) return;
  var reduce = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;

  var W = 6, H = 4.6, END = 96, EYE = 1.65, NEAR = .5;
  var HAZE = [241, 238, 232];
  var ROOM = [], OBJ = [], LIGHTS = [];

  // грань: точки, цвет, прозрачность, нормаль наружу (null = видна с обеих сторон), свечение
  function face(list, pts, col, a, n, emit) { list.push({ p: pts, c: col, a: a == null ? 1 : a, n: n || null, e: emit || 0, r: list === ROOM }); }
  function quadZ(list, x1, y1, x2, y2, z, col, a, nz, e) { face(list, [[x1, y1, z], [x2, y1, z], [x2, y2, z], [x1, y2, z]], col, a, nz == null ? null : [0, 0, nz], e); }
  function box(x1, y1, z1, x2, y2, z2, col, a, shadow) {
    var L = OBJ;
    face(L, [[x1, y2, z1], [x2, y2, z1], [x2, y2, z2], [x1, y2, z2]], tone(col, 1.06), a, [0, 1, 0]);   // верх
    face(L, [[x1, y1, z1], [x2, y1, z1], [x2, y2, z1], [x1, y2, z1]], col, a, [0, 0, -1]);              // перед
    face(L, [[x1, y1, z2], [x2, y1, z2], [x2, y2, z2], [x1, y2, z2]], col, a, [0, 0, 1]);
    face(L, [[x1, y1, z1], [x1, y1, z2], [x1, y2, z2], [x1, y2, z1]], tone(col, .84), a, [-1, 0, 0]);
    face(L, [[x2, y1, z1], [x2, y1, z2], [x2, y2, z2], [x2, y2, z1]], tone(col, .78), a, [1, 0, 0]);
    if (shadow !== false && y1 < .01) { var s = .22; face(L, [[x1 - s, .002, z1 - s], [x2 + s, .002, z1 - s], [x2 + s, .002, z2 + s], [x1 - s, .002, z2 + s]], [60, 55, 50], .12, [0, 1, 0]); }
  }
  function tone(c, k) { return [Math.min(255, c[0] * k), Math.min(255, c[1] * k), Math.min(255, c[2] * k)]; }

  var STONE = [234, 229, 220], STONE2 = [226, 220, 210], WALL = [244, 241, 235], WALL2 = [238, 234, 227], CEIL = [247, 246, 242];
  var WOOD = [120, 90, 66], DARK = [96, 110, 126], NAVY = [33, 52, 77], TEAL = [14, 122, 130], GOLD = [196, 164, 106], GLASS = [196, 222, 228], STEEL = [184, 190, 197];
  var z, i, k;

  // пол: полированный камень в шахматку
  for (z = 0; z < END; z += 3) for (i = -W, k = 0; i < W; i += 2, k++) {
    face(ROOM, [[i, 0, z], [i + 2, 0, z], [i + 2, 0, z + 3], [i, 0, z + 3]], ((k + z / 3) % 2) ? STONE : STONE2, .86, [0, 1, 0]);
  }
  // стены панелями и окна под потолком (дневной свет)
  for (z = 0; z < END; z += 4) {
    var wc = (z / 4) % 2 ? WALL : WALL2;
    face(ROOM, [[-W, 0, z], [-W, 0, z + 4], [-W, H, z + 4], [-W, H, z]], tone(wc, .93), 1, [1, 0, 0]);
    face(ROOM, [[W, 0, z], [W, 0, z + 4], [W, H, z + 4], [W, H, z]], tone(wc, .88), 1, [-1, 0, 0]);
    face(ROOM, [[-W, H, z], [W, H, z], [W, H, z + 4], [-W, H, z + 4]], CEIL, 1, [0, -1, 0]);
  }
  for (z = 5; z < END - 8; z += 7) {
    face(ROOM, [[-W + .01, 2.9, z], [-W + .01, 2.9, z + 4.2], [-W + .01, 4.2, z + 4.2], [-W + .01, 4.2, z]], [255, 255, 255], 1, [1, 0, 0], 1);
    face(ROOM, [[W - .01, 2.9, z], [W - .01, 2.9, z + 4.2], [W - .01, 4.2, z + 4.2], [W - .01, 4.2, z]], [255, 255, 255], 1, [-1, 0, 0], 1);
  }
  // светильники на потолке
  for (z = 6; z < END - 4; z += 7) {
    face(ROOM, [[-1.8, H - .01, z], [1.8, H - .01, z], [1.8, H - .01, z + 2.4], [-1.8, H - .01, z + 2.4]], [255, 252, 240], 1, [0, -1, 0], 1);
    LIGHTS.push([0, H - .05, z + 1.2, 2.6]);
  }
  // задняя стена
  face(ROOM, [[-W, 0, END], [W, 0, END], [W, H, END], [-W, H, END]], [225, 219, 208], 1, [0, 0, -1]);

  // колонны с золотым цоколем
  for (z = 10; z < END - 8; z += 12) {
    box(-W, 0, z, -W + .8, H, z + .8, [232, 227, 218]); box(W - .8, 0, z, W, H, z + .8, [232, 227, 218]);
    box(-W, 0, z - .05, -W + .9, .35, z + .85, GOLD, 1, false); box(W - .9, 0, z - .05, W, .35, z + .85, GOLD, 1, false);
  }
  // вход: тёмная рама и стеклянные двери
  box(-3.6, 0, 3, -3.3, 3.8, 3.3, DARK); box(3.3, 0, 3, 3.6, 3.8, 3.3, DARK); box(-3.6, 3.6, 3, 3.6, 3.9, 3.3, DARK, 1, false);
  quadZ(OBJ, -3.3, 0, 3.3, 3.6, 3.15, GLASS, .22, null);
  box(-W, 3.6, 3, -3.6, H, 3.3, WALL2, 1, false); box(3.6, 3.6, 3, W, H, 3.3, WALL2, 1, false);
  box(-W, 0, 3, -3.6, 3.6, 3.3, WALL2, 1, false); box(3.6, 0, 3, W, 3.6, 3.3, WALL2, 1, false);

  // кассы слева: деревянная стойка, стекло, табло
  for (z = 16; z < 34; z += 3.6) {
    box(-W, 0, z, -3.7, 1.1, z + 3.3, WOOD);
    box(-W, 1.1, z, -3.6, 1.16, z + 3.3, [236, 231, 222], 1, false);
    quadZ(OBJ, -3.7, 1.16, -3.7, 2.3, z, GLASS, .3);
    face(OBJ, [[-3.7, 1.16, z], [-3.7, 1.16, z + 3.3], [-3.7, 2.3, z + 3.3], [-3.7, 2.3, z]], GLASS, .28, null);
    box(-W + .02, 2.75, z + .9, -W + .1, 3.25, z + 2.3, TEAL, 1, false);
  }
  // стойки очереди с лентой
  for (z = 17; z < 32; z += 3) {
    box(-1.65, 0, z, -1.55, 1, z + .1, GOLD); box(-.25, 0, z, -.15, 1, z + .1, GOLD);
    if (z + 3 < 32) box(-1.62, .86, z + .05, -1.58, .94, z + 3.05, TEAL, 1, false);
  }
  // диваны ожидания справа
  for (z = 18; z < 32; z += 6) { box(3.7, 0, z, 5.3, .46, z + 3.4, NAVY); box(5.0, .46, z, 5.3, 1.05, z + 3.4, NAVY, 1, false); }
  // переговорные справа: стекло, рамы, стол, кресла
  for (z = 42; z < 66; z += 8) {
    face(OBJ, [[2.3, 0, z], [2.3, 0, z + 7], [2.3, 3, z + 7], [2.3, 3, z]], GLASS, .26, null);
    quadZ(OBJ, 2.3, 0, W, 3, z, GLASS, .2, null);
    box(2.25, 0, z, 2.35, 3.05, z + .1, DARK, 1, false); box(2.25, 2.95, z, W, 3.05, z + 7, DARK, 1, false);
    box(3.3, .7, z + 2, 5, .78, z + 5, WOOD); box(4.05, 0, z + 3.2, 4.25, .7, z + 3.8, DARK, 1, false);
    for (i = 0; i < 3; i++) { box(2.85, 0, z + 2.25 + i * 1.05, 3.15, .95, z + 2.65 + i * 1.05, DARK); box(5.15, 0, z + 2.25 + i * 1.05, 5.45, .95, z + 2.65 + i * 1.05, DARK); }
  }
  // банкоматы слева
  for (z = 44; z < 64; z += 4) { box(-W, 0, z, -5.15, 1.9, z + 1.5, [52, 64, 79]); face(OBJ, [[-5.14, 1.15, z + .25], [-5.14, 1.15, z + 1.25], [-5.14, 1.6, z + 1.25], [-5.14, 1.6, z + .25]], TEAL, 1, [1, 0, 0], 1); }
  // растения в кадках вдоль зала
  for (z = 36; z < 80; z += 10) { box(-1.2, 0, z, -.6, .6, z + .6, [214, 207, 196]); box(-1.3, .6, z - .1, -.5, 1.5, z + .7, [96, 128, 104], 1, false); }

  // хранилище: портал и круглая стальная дверь
  box(-2.9, 0, END - .4, -2.5, 4.2, END, DARK, 1, false); box(2.5, 0, END - .4, 2.9, 4.2, END, DARK, 1, false); box(-2.9, 4, END - .4, 2.9, 4.3, END, DARK, 1, false);
  var VAULT = { x: 0, y: 2, z: END - .1 };

  // ---------- рендер ----------
  var w, h, dpr, F, cx, cy, camZ = 0, ticking = false;
  function resize() {
    dpr = Math.min(window.devicePixelRatio || 1, 1.75);
    w = window.innerWidth; h = window.innerHeight;
    cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr); cv.style.width = w + "px"; cv.style.height = h + "px";
    F = Math.max(w * .62, h * .78); cx = w / 2; cy = h * .47;
    draw();
  }
  function clip(pts) {
    var out = [], n = pts.length;
    for (var j = 0; j < n; j++) {
      var a = pts[j], b = pts[(j + 1) % n], da = a[2] - camZ - NEAR, db = b[2] - camZ - NEAR;
      if (da >= 0) out.push(a);
      if ((da >= 0) !== (db >= 0)) { var t = da / (da - db); out.push([a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t]); }
    }
    return out;
  }
  function fogK(d) { var t = Math.max(0, Math.min(1, (d - 3) / 75)); return Math.pow(t, .85) * .8; }
  function col(c, d, k) { var f = fogK(d); return "rgb(" + Math.round((c[0] * k) * (1 - f) + HAZE[0] * f) + "," + Math.round((c[1] * k) * (1 - f) + HAZE[1] * f) + "," + Math.round((c[2] * k) * (1 - f) + HAZE[2] * f) + ")"; }

  function prep(list, mirror) {
    var res = [];
    for (var j = 0; j < list.length; j++) {
      var f = list[j], p0 = f.p[0];
      if (f.n) {
        var vx = 0 - p0[0], vy = (mirror ? -EYE : EYE) - p0[1], vz = camZ - p0[2];
        if (f.n[0] * vx + f.n[1] * vy + f.n[2] * vz <= 0) continue;
      }
      var pts = clip(f.p);
      if (pts.length < 3) continue;
      var depth = 0;
      for (var q = 0; q < pts.length; q++) depth += pts[q][2] - camZ;
      depth /= pts.length;
      if (depth > 90) continue;
      var mn = 1e9; for (q = 0; q < pts.length; q++) mn = Math.min(mn, pts[q][2] - camZ);
      res.push({ f: f, pts: pts, d: depth, m: mn });
    }
    return res;
  }
  function paint(items, mirror, alphaMul) {
    for (var j = 0; j < items.length; j++) {
      var it = items[j], f = it.f, pts = it.pts;
      ctx.beginPath();
      for (var q = 0; q < pts.length; q++) {
        var dz = pts[q][2] - camZ, y = mirror ? -pts[q][1] : pts[q][1];
        var sx = cx + pts[q][0] / dz * F, sy = cy - (y - EYE) / dz * F;
        if (q) ctx.lineTo(sx, sy); else ctx.moveTo(sx, sy);
      }
      ctx.closePath();
      var near = Math.max(0, Math.min(1, (it.m - .6) / 3.5));
      if (!f.r && near <= 0.01) continue;
      ctx.globalAlpha = f.a * alphaMul * (f.r ? 1 : near);
      ctx.fillStyle = f.e ? col(f.c, it.d * .5, 1) : col(f.c, it.d, 1);
      ctx.fill();
    }
    ctx.globalAlpha = 1;
  }
  function byDepth(a, b) { return b.d - a.d; }

  function draw() {
    ticking = false;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.fillStyle = "rgb(" + HAZE.join(",") + ")"; ctx.fillRect(0, 0, w, h);

    var room = prep(ROOM, false), obj = prep(OBJ, false).sort(byDepth);
    // 1) отражения в полированном полу (зеркальная копия предметов под полом)
    var mir = prep(OBJ, true).sort(byDepth);
    paint(mir, true, .35);
    // 2) стены, потолок, затем полупрозрачный пол поверх отражений
    var floor = [], rest = [];
    for (var j = 0; j < room.length; j++) (room[j].f.n && room[j].f.n[1] === 1 ? floor : rest).push(room[j]);
    rest.sort(byDepth); floor.sort(byDepth);
    paint(rest, false, 1);
    paint(floor, false, 1);
    // 3) предметы
    paint(obj, false, 1);
    // 4) дверь хранилища
    var dz = VAULT.z - camZ;
    if (dz > NEAR) {
      var vx = cx + VAULT.x / dz * F, vy = cy - (VAULT.y - EYE) / dz * F, r = 1.75 / dz * F;
      var g = ctx.createRadialGradient(vx - r * .3, vy - r * .3, r * .1, vx, vy, r);
      g.addColorStop(0, col([214, 219, 224], dz, 1)); g.addColorStop(1, col(STEEL, dz, .86));
      ctx.fillStyle = g; ctx.beginPath(); ctx.arc(vx, vy, r, 0, 7); ctx.fill();
      ctx.lineWidth = Math.max(1, r * .05); ctx.strokeStyle = col([150, 156, 164], dz, 1);
      ctx.beginPath(); ctx.arc(vx, vy, r * .8, 0, 7); ctx.stroke();
      ctx.strokeStyle = col(GOLD, dz, 1); ctx.lineWidth = Math.max(1, r * .06);
      for (var s = 0; s < 6; s++) { var an = s * Math.PI / 3; ctx.beginPath(); ctx.moveTo(vx + Math.cos(an) * r * .18, vy + Math.sin(an) * r * .18); ctx.lineTo(vx + Math.cos(an) * r * .55, vy + Math.sin(an) * r * .55); ctx.stroke(); }
      ctx.fillStyle = col(GOLD, dz, 1); ctx.beginPath(); ctx.arc(vx, vy, r * .16, 0, 7); ctx.fill();
    }
    // 5) мягкое свечение светильников
    ctx.globalCompositeOperation = "lighter";
    for (var l = 0; l < LIGHTS.length; l++) {
      var Lt = LIGHTS[l], d2 = Lt[2] - camZ;
      if (d2 < 1) continue;
      var lx = cx + Lt[0] / d2 * F, ly = cy - (Lt[1] - EYE) / d2 * F, lr = Lt[3] / d2 * F * 1.6;
      var a = Math.max(0, .16 * (1 - d2 / 80));
      var gg = ctx.createRadialGradient(lx, ly, 0, lx, ly, lr);
      gg.addColorStop(0, "rgba(255,240,215," + a + ")"); gg.addColorStop(1, "rgba(255,240,215,0)");
      ctx.fillStyle = gg; ctx.fillRect(lx - lr, ly - lr, lr * 2, lr * 2);
    }
    ctx.globalCompositeOperation = "source-over";
  }
  function onScroll() {
    var max = Math.max(1, document.documentElement.scrollHeight - window.innerHeight);
    camZ = reduce ? 0 : Math.min(1, window.scrollY / max) * (END - 10);
    if (!ticking) { ticking = true; requestAnimationFrame(draw); }
  }
  document.addEventListener("DOMContentLoaded", function () {
    document.body.insertBefore(cv, document.body.firstChild);
    resize(); onScroll();
    window.addEventListener("resize", function () { resize(); onScroll(); });
    if (!reduce) window.addEventListener("scroll", onScroll, { passive: true });
  });
})();
