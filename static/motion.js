// Движение сайта: блоки въезжают с разных сторон в такт скроллу, лента услуг едет вбок, буква F собирается из двух деталей
(function () {
  var reduce = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (reduce) return;
  document.documentElement.classList.add("js");

  var slides = [], hs = [], mark = null, ticking = false;
  var clamp = function (v, a, b) { return Math.max(a, Math.min(b, v)); };
  var ease = function (t) { return 1 - Math.pow(1 - t, 3); };

  function setup() {
    // больше въездов: вопросы по очереди слева и справа, карточки статей и форма
    Array.prototype.forEach.call(document.querySelectorAll(".faq details"), function (el, i) { if (!el.hasAttribute("data-slide")) el.setAttribute("data-slide", i % 2 ? "right" : "left"); });
    Array.prototype.forEach.call(document.querySelectorAll(".grid3 > .card"), function (el, i) { if (!el.hasAttribute("data-slide")) { el.setAttribute("data-slide", ["left", "up", "right"][i % 3]); el.setAttribute("data-rot", ["-2", "0", "2"][i % 3]); } });
    Array.prototype.forEach.call(document.querySelectorAll(".form-in > div, .prose > h2"), function (el, i) { if (!el.hasAttribute("data-slide") && !el.closest("[data-slide]")) el.setAttribute("data-slide", i % 2 ? "right" : "left"); });
    Array.prototype.forEach.call(document.querySelectorAll(".prose > p, .prose > ul, .prose > ol"), function (el) { if (!el.closest("[data-slide]")) el.setAttribute("data-slide", "up"); });
    var lf = document.querySelector(".lead-form"); if (lf && !lf.hasAttribute("data-slide")) lf.setAttribute("data-slide", "right");
    slides = Array.prototype.map.call(document.querySelectorAll("[data-slide]"), function (el) {
      var d = el.getAttribute("data-slide");
      return { el: el, dir: d === "left" ? -1 : d === "right" ? 1 : 0, rot: parseFloat(el.getAttribute("data-rot") || "0") };
    });
    hs = Array.prototype.map.call(document.querySelectorAll(".hs"), function (sec) {
      return { sec: sec, track: sec.querySelector(".hs-track"), bar: sec.querySelector(".hs-bar i"), sticky: sec.querySelector(".hs-sticky") };
    });
    mark = document.querySelector(".mark");
    size();
  }

  function size() {
    hs.forEach(function (h) {
      var dist = Math.max(0, h.track.scrollWidth - window.innerWidth);
      h.dist = dist;
      // высота секции = путь ленты + один экран: пока листаешь вниз, лента уезжает влево
      h.sec.style.height = (dist + h.sticky.offsetHeight + 64) + "px";
    });
    frame();
  }

  function frame() {
    ticking = false;
    var vh = window.innerHeight, vw = window.innerWidth;
    var shift = Math.min(240, vw * 0.32);

    slides.forEach(function (s) {
      var r = s.el.getBoundingClientRect();
      // 0 когда блок у нижнего края экрана, 1 когда поднялся на 35% экрана
      var p = ease(clamp((vh - r.top) / (vh * 0.35 + Math.min(r.height, vh) * 0.25), 0, 1));
      var x = (1 - p) * shift * s.dir, y = s.dir ? 0 : (1 - p) * 60, rot = (1 - p) * s.rot;
      s.el.style.transform = "translate3d(" + x.toFixed(1) + "px," + y.toFixed(1) + "px,0) rotate(" + rot.toFixed(2) + "deg)";
      s.el.style.opacity = (0.15 + 0.85 * p).toFixed(3);
    });

    hs.forEach(function (h) {
      var r = h.sec.getBoundingClientRect();
      var total = h.sec.offsetHeight - h.sticky.offsetHeight - 64;
      var p = total > 0 ? clamp(-r.top / total, 0, 1) : 0;
      h.track.style.transform = "translate3d(" + (-p * h.dist).toFixed(1) + "px,0,0)";
      if (h.bar) h.bar.style.width = (p * 100).toFixed(1) + "%";
    });

    if (mark) {
      var y = window.scrollY, k = clamp(y / vh, 0, 1.2);
      var a = mark.querySelector(".p1"), b = mark.querySelector(".p2");
      a.style.transform = "translate(" + (k * 70).toFixed(1) + "px," + (-k * 20).toFixed(1) + "px)";
      b.style.transform = "translate(" + (-k * 50).toFixed(1) + "px," + (k * 30).toFixed(1) + "px) rotate(" + (k * -6).toFixed(2) + "deg)";
    }
  }

  function onScroll() { if (!ticking) { ticking = true; requestAnimationFrame(frame); } }

  document.addEventListener("DOMContentLoaded", function () {
    setup();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", size);
    window.addEventListener("load", size);
    // сборка буквы F при загрузке
    if (mark) requestAnimationFrame(function () { mark.classList.add("on"); });
  });
})();
