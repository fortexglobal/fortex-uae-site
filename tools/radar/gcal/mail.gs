// Рассылка Fortex с ящика alexey@fortex-uae.com (решение Александра 26.11, вместо Instantly).
// Сервер DigitalOcean не может слать почту напрямую (порты почты закрыты), поэтому письма отправляет этот скрипт от имени ящика.
// Развернуть (один раз, ВОЙДЯ ПОД alexey@fortex-uae.com):
// script.google.com -> Новый проект -> стереть всё и вставить этот код -> Сохранить ->
// Развернуть -> Новое развёртывание -> шестерёнка: Веб-приложение -> Запуск от имени: Я, Доступ: Все -> Развернуть ->
// разрешить доступ к Gmail -> скопировать ссылку веб-приложения.
// Ссылку отправить боту радара командой: /igdm mailhook <ссылка>  (бот удалит сообщение с ней).

function doPost(e) {
  var d = JSON.parse(e.postData.contents);
  if (d.action === 'send') return send_(d);
  if (d.action === 'inbox') return inbox_(d);
  return out_({ok: false, error: 'unknown action'});
}

function send_(d) {
  var opts = {name: d.from_name || 'Алексей Ронин'};
  if (d.thread_id) {
    var th = GmailApp.getThreadById(d.thread_id);
    if (th) {
      // догоняющее письмо в ту же переписку: тема «Re: …», Gmail склеит его с первым
      var dr = GmailApp.createDraft(d.to, d.subject, d.body, opts);
      dr.send();
      return out_({ok: true, thread_id: d.thread_id});
    }
  }
  var draft = GmailApp.createDraft(d.to, d.subject, d.body, opts);
  var msg = draft.send();
  return out_({ok: true, thread_id: msg.getThread().getId()});
}

function inbox_(d) {
  var q = 'in:inbox newer_than:' + (d.days || 3) + 'd -from:me';
  var res = [];
  GmailApp.search(q, 0, 50).forEach(function (th) {
    th.getMessages().forEach(function (m) {
      if (m.getFrom().indexOf(Session.getActiveUser().getEmail()) >= 0) return;
      var from = m.getFrom(), mm = from.match(/<([^>]+)>/);
      res.push({id: m.getId(), from: (mm ? mm[1] : from).toLowerCase(), subject: m.getSubject(),
                text: m.getPlainBody().slice(0, 4000), date: m.getDate().toISOString()});
    });
  });
  return out_({ok: true, messages: res});
}

function out_(o) {
  return ContentService.createTextOutput(JSON.stringify(o)).setMimeType(ContentService.MimeType.JSON);
}
