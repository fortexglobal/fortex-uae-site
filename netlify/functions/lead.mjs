// Отправляет заявку с сайта в Telegram. Переменные окружения Netlify: BOT_TOKEN, CHAT_ID
export default async (req) => {
  if (req.method !== "POST") return new Response("Method not allowed", { status: 405 });
  const form = new URLSearchParams(await req.text());
  if (form.get("company_site")) return new Response("ok");
  const clip = (v, n) => (v || "").toString().trim().slice(0, n);
  const name = clip(form.get("name"), 100), tg = clip(form.get("telegram"), 100);
  const task = clip(form.get("task"), 1500), page = clip(form.get("page"), 200), src = clip(form.get("src"), 200);
  if (!name || !tg) return new Response("Заполните имя и Telegram", { status: 400 });
  const handle = tg.startsWith("@") ? tg.slice(1) : (/^[A-Za-z0-9_]{5,}$/.test(tg) ? tg : "");
  const text = `🔥 Заявка с сайта fortex-uae.com\n\nИмя: ${name}\nTelegram: ${tg}${handle ? `\nhttps://t.me/${handle}` : ""}\nЗадача: ${task || "не указана"}\nСтраница: ${page || "/"}\nИсточник: ${src || "не определён"}`;
  const r = await fetch(`https://api.telegram.org/bot${process.env.BOT_TOKEN}/sendMessage`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: process.env.CHAT_ID, text, disable_web_page_preview: true }),
  });
  return new Response(r.ok ? "ok" : "telegram error", { status: r.ok ? 200 : 502 });
};
