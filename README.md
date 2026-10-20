# fortex-uae.com

Сайт Fortex UAE. Сборка без зависимостей: `python3 build.py` → папка `public/`.

- Главная: `content/site.py`
- Статьи: `content/articles/*.md` (front matter: title, description, date, topic). Статья с датой в будущем не публикуется до этой даты.
- Стили и картинки: `static/`
- Netlify собирает сайт сам при каждом коммите (`netlify.toml`).

## Черновики статей
Статья с `status: draft` в шапке собирается только по скрытой ссылке `/draft/<slug>/` (noindex, нет в sitemap и списках).
Чтобы опубликовать: убрать строку `status: draft`, поставить актуальную `date:`.
Очередь одобрения: Google Sheets CRM, лист «Контент».
