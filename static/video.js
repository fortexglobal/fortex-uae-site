// Видео-фон: живой Дубай за текстом. Сначала лёгкий кадр-постер, видео подгружается после загрузки страницы.
// При скролле картинка медленно приближается, будто идёшь вперёд. Экономия трафика и «меньше движения» = только постер.
(function () {
  var v = document.createElement("video");
  if (!v.canPlayType || !v.canPlayType("video/mp4")) return;
  document.documentElement.classList.add("has-video");
  var reduce = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;
  var save = navigator.connection && navigator.connection.saveData;

  v.className = "bank-video";
  v.muted = true; v.loop = true; v.playsInline = true; v.preload = "none";
  v.setAttribute("muted", ""); v.setAttribute("playsinline", ""); v.setAttribute("aria-hidden", "true");
  v.poster = "/video/bg-poster.jpg";

  var ticking = false;
  function zoom() {
    ticking = false;
    var max = Math.max(1, document.documentElement.scrollHeight - innerHeight);
    var p = Math.min(1, scrollY / max);
    v.style.transform = "scale(" + (1.04 + p * .3).toFixed(4) + ")";
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.body.insertBefore(v, document.body.firstChild);
    zoom();
    if (!reduce) addEventListener("scroll", function () { if (!ticking) { ticking = true; requestAnimationFrame(zoom); } }, { passive: true });
  });
  addEventListener("load", function () {
    if (reduce || save) return;
    v.src = "/video/bg-720.mp4";
    v.addEventListener("playing", function () { v.classList.add("on"); }, { once: true });
    var pr = v.play(); if (pr && pr.catch) pr.catch(function () {});
  });
})();

// Видео «Как мы работаем»: грузится, только когда блок виден, играет без звука по кругу, на телефоне вертикальная версия
(function () {
  document.addEventListener("DOMContentLoaded", function () {
    var v = document.querySelector(".how-vid video");
    if (!v) return;
    var mob = window.matchMedia && matchMedia("(max-width:700px)").matches;
    var base = v.getAttribute(mob ? "data-m" : "data-d");
    v.poster = base + ".jpg";
    var reduce = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce || !("IntersectionObserver" in window)) { v.controls = true; v.src = base + ".mp4"; return; }
    new IntersectionObserver(function (es) {
      es.forEach(function (e) {
        if (e.isIntersecting) {
          if (!v.src) v.src = base + ".mp4";
          var pr = v.play(); if (pr && pr.catch) pr.catch(function () {});
        } else if (v.src) v.pause();
      });
    }, { threshold: .35 }).observe(v);
  });
})();
