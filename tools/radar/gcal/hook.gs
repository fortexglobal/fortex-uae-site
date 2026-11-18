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
  if (d.action === 'club') return club_(d);
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

// Клуб: заявки из бота клуба -> лист «Клуб: заявки» в CRM (строка по uid обновляется), сортировка по уровню 1, 2, 3
var CRM_ID = '1qg8dezB2VU6yuKryCYLVzcmLw_OpFqD3VkINSzIY-j4', CLUB_SHEET = 'Клуб: заявки';
function club_(d) {
  var sh = SpreadsheetApp.openById(CRM_ID).getSheetByName(CLUB_SHEET);
  var row = d.row;  // [уровень, дата, имя, telegram, занятие, сфера, команда, ищет, интересы, о себе, источник, uid]
  var last = sh.getLastRow(), at = 0;
  if (last > 1) {
    var ids = sh.getRange(2, 12, last - 1, 1).getValues();
    for (var i = 0; i < ids.length; i++) if (String(ids[i][0]) === String(row[11])) { at = i + 2; break; }
  }
  if (at) sh.getRange(at, 1, 1, row.length).setValues([row]); else sh.appendRow(row);
  last = sh.getLastRow();
  if (last > 2) sh.getRange(2, 1, last - 1, 12).sort([{column: 1, ascending: true}, {column: 2, ascending: false}]);
  return out_({ok: true});
}

function out_(o) {
  return ContentService.createTextOutput(JSON.stringify(o)).setMimeType(ContentService.MimeType.JSON);
}
