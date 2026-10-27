// откуда пришёл человек: utm-метка или сайт-источник, запоминаем при первом заходе
(function () {
  try {
    if (!sessionStorage.getItem("src")) {
      var q = new URLSearchParams(location.search), ref = document.referrer, src = "";
      if (q.get("utm_source")) src = q.get("utm_source") + (q.get("utm_campaign") ? " / " + q.get("utm_campaign") : "");
      else if (ref && ref.indexOf(location.host) < 0) src = new URL(ref).hostname;
      else src = "прямой заход";
      sessionStorage.setItem("src", src);
      sessionStorage.setItem("land", location.pathname);
    }
  } catch (e) {}
})();

document.addEventListener("DOMContentLoaded", function () {
  // цели Метрики: клики в Telegram и запись на звонок
  document.addEventListener("click", function (e) {
    var a = e.target.closest && e.target.closest("a"); if (!a) return;
    try {
      if (/\/c\/[a-z]+$/i.test(a.getAttribute("href") || "")) { ym(113701535, "reachGoal", "consult_click"); ym(113701535, "reachGoal", "tg_click"); }
      else if (/t\.me\//i.test(a.href)) ym(113701535, "reachGoal", "tg_click");
      else if (/calendly\.com/i.test(a.href)) ym(113701535, "reachGoal", "call_click");
    } catch (err) {}
  });
  // мобильное меню
  var bt = document.querySelector(".burger"), mn = document.getElementById("mnav");
  if (bt && mn) {
    var set = function (open) { bt.setAttribute("aria-expanded", open); mn.hidden = !open; document.documentElement.classList.toggle("menu-open", open); };
    bt.addEventListener("click", function () { set(bt.getAttribute("aria-expanded") !== "true"); });
    mn.addEventListener("click", function (e) { if (e.target.tagName === "A") set(false); });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape") set(false); });
  }
  document.querySelectorAll("form.lead-form").forEach(function (f) {
    f.page.value = location.pathname;
    try { if (f.src) f.src.value = (sessionStorage.getItem("src") || "") + " → " + (sessionStorage.getItem("land") || ""); } catch (e) {}
    f.addEventListener("submit", async function (e) {
      e.preventDefault();
      var msg = f.querySelector(".form-msg"), btn = f.querySelector("button");
      if (f.company_site.value) return;
      btn.disabled = true; btn.textContent = "Отправляем…";
      var data = new URLSearchParams(new FormData(f));
      var ok = false;
      try {
        var r1 = await fetch("/.netlify/functions/lead", { method: "POST", body: data });
        ok = r1.ok;
      } catch (err) {}
      try {
        var r2 = await fetch("/", { method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" }, body: data.toString() });
        ok = ok || r2.ok;
      } catch (err) {}
      if (ok) { try { ym(113701535, "reachGoal", "lead_form"); } catch (e) {} setTimeout(function () { location.href = "/spasibo/"; }, 300); return; }
      btn.disabled = false; btn.textContent = "Отправить заявку";
      msg.textContent = "Не получилось отправить. Напишите нам в Telegram: @Fortex_Dubai";
    });
  });
});

(function () {
  var b = document.querySelector(".float-tg");
  if (!b) return;
  var f = function () { b.classList.toggle("on", window.scrollY > 600); };
  window.addEventListener("scroll", f, { passive: true }); f();
})();
