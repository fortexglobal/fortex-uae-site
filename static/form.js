document.addEventListener("DOMContentLoaded", function () {
  document.querySelectorAll("form.lead-form").forEach(function (f) {
    f.page.value = location.pathname;
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
      if (ok) { location.href = "/spasibo/"; return; }
      btn.disabled = false; btn.textContent = "Отправить заявку";
      msg.textContent = "Не получилось отправить. Напишите нам в Telegram: @FortexGlobal";
    });
  });
});
