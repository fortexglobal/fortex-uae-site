// Веб-хук для Алексея: ставит созвон в Google Календарь аккаунта, под которым развёрнут.
// Развернуть: script.google.com -> Новый проект -> вставить этот код -> Развернуть -> Новое развёртывание ->
// Тип: Веб-приложение, Запуск от имени: Я, Доступ: Все -> Развернуть -> разрешить доступ к календарю -> скопировать ссылку.
// Ссылку отправить своему боту командой: /igdm gcal <ссылка>  (бот удалит сообщение с ней).
function doPost(e) {
  var d = JSON.parse(e.postData.contents);
  var cal = CalendarApp.getDefaultCalendar();
  var start = new Date(d.start), end = new Date(d.end);
  var ev = d.id ? cal.getEventById(d.id) : null;
  if (ev) {
    ev.setTime(start, end);
    ev.setTitle(d.title);
    ev.setDescription(d.description || '');
  } else {
    ev = cal.createEvent(d.title, start, end, {description: d.description || ''});
    ev.addPopupReminder(10);
  }
  return ContentService.createTextOutput(JSON.stringify({ok: true, id: ev.getId()})).setMimeType(ContentService.MimeType.JSON);
}
