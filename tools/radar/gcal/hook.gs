// Веб-хук Fortex (Алексей и смотритель): 1) ставит созвоны в Google Календарь, 2) складывает еженедельный бэкап в Google Диск.
// Развернуть (один раз, под аккаунтом Fortex Global):
// script.google.com -> Новый проект -> стереть всё и вставить этот код -> Сохранить ->
// Развернуть -> Новое развёртывание -> шестерёнка: Веб-приложение -> Запуск от имени: Я, Доступ: Все -> Развернуть ->
// разрешить доступ (Календарь и Диск) -> скопировать ссылку веб-приложения.
// Ссылку отправить своему боту командой: /igdm gcal <ссылка>  (бот удалит сообщение с ней).
var BACKUP_FOLDER = 'Fortex Backup';
var KEEP = 12; // сколько последних архивов хранить

function doPost(e) {
  var d = JSON.parse(e.postData.contents);
  if (d.action === 'backup') return backup_(d);
  return calendar_(d);
}

function calendar_(d) {
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
  ev.setColor(CalendarApp.EventColor.ORANGE);  // созвоны с клиентами оранжевым (зелёный у Александра занят)
  return out_({ok: true, id: ev.getId()});
}

function backup_(d) {
  var it = DriveApp.getFoldersByName(BACKUP_FOLDER);
  var folder = it.hasNext() ? it.next() : DriveApp.createFolder(BACKUP_FOLDER);
  var sub = d.folder || 'archives';
  var it2 = folder.getFoldersByName(sub);
  var target = it2.hasNext() ? it2.next() : folder.createFolder(sub);
  var blob = Utilities.newBlob(Utilities.base64Decode(d.b64), d.mime || 'application/gzip', d.name);
  if (d.replace) {  // файл с постоянным именем (например, kb.md): заменяем
    var old = target.getFilesByName(d.name);
    while (old.hasNext()) old.next().setTrashed(true);
  }
  var f = target.createFile(blob);
  if (!d.replace) {  // старые архивы чистим, оставляем KEEP последних
    var files = [], all = target.getFiles();
    while (all.hasNext()) files.push(all.next());
    files.sort(function (a, b) { return b.getDateCreated() - a.getDateCreated(); });
    for (var i = KEEP; i < files.length; i++) files[i].setTrashed(true);
  }
  return out_({ok: true, id: f.getId(), url: f.getUrl()});
}

function out_(o) {
  return ContentService.createTextOutput(JSON.stringify(o)).setMimeType(ContentService.MimeType.JSON);
}
