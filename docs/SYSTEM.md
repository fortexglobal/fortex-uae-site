# Fortex UAE: карта системы и как её восстановить

Обновлено: 08.11.2026. Ключей и паролей здесь нет, только где они лежат и откуда их взять заново.

## 1. Из чего состоит система

| Часть | Где живёт | За что отвечает | Зависит от Claude? |
|---|---|---|---|
| Репозиторий | GitHub `fortexglobal/fortex-uae-site` | весь код, база знаний, статьи, посты, состояние автоматики | нет |
| Сайт fortex-uae.com | Netlify (собирается из репозитория при каждом пуше) | лендинги, статьи, /virtual-work/, /ipoteka/, /gid/ | нет |
| Сервер (VPS) | `/opt/radar`, `/opt/keeper` | Алексей в Telegram (@Fortex_Dubai) и в директе Instagram, бот @Fortex_Radar_Bot, радар в чатах, публикация в канал @fortex_uae, бот-проверка @FortexCheck_Bot, смотритель | нет (LLM через OpenRouter) |
| GitHub Actions | `.github/workflows/*.yml` | публикация в Threads (оба аккаунта), ответы на комментарии, Instagram, рилсы, обложки, статистика, Метрика | нет |
| Ежедневные задачи | Claude (scheduled tasks) | посты Threads, серия статей, рилс дня, поиск лидов и партнёров, разбор писем, отчёты | ДА: их тексты лежат в бэкапе `tasks/` |
| Память | Claude memory | правила и решения Александра | ДА: выгрузка в бэкапе |

## 2. Сервер

- `/opt/radar`: сервис `radar` (systemd, `/opt/radar/venv/bin/python /opt/radar/radar.py`). Модули: `igdm.py` (Алексей: Telegram и директ Instagram, созвоны, Zoom, календарь), `autoreply.py` (радар в Telegram-чатах), `content.py` (посты в канал @fortex_uae, публикация в 19:07), `starters.py`, `reactions.py`, `newsfeed.py`, `kb.md` (база знаний Алексея).
- `/opt/radar` также сервис `leadbot` (`leadbot.py`, бот @FortexCheck_Bot).
- `/opt/keeper`: сервис `keeper` (`/usr/bin/python3 -u /opt/keeper/keeper.py`). Раз в минуту тянет репозиторий, сам выкладывает изменённые файлы `tools/radar/*` в `/opt/radar` и перезапускает радар, публикует посты Threads минута в минуту, следит за балансами (OpenRouter, Apify), раз в 15 минут пишет `keeper/status.json` в репозиторий, раз в неделю делает бэкап в Google Диск.
- Секреты на сервере (файлы и `*.env`, в репозиторий не попадают): токен бота, OpenRouter, Telegram-сессия аккаунта радара (`*.session`), GitHub-токен (`/opt/radar/github_token`), ключ Instagram, `gcal_hook` (ссылка веб-хука Apps Script), `zoom_creds` (Account ID, Client ID, Client Secret), `/opt/keeper/keeper.env`.
- Установка с нуля: Ubuntu + python3 + venv, скачать файлы `tools/radar/*` и `tools/radar/server/radar.py` (это копия без секретов), вписать секреты, поднять сервисы по `tools/radar/keeper.sh` и `install*.sh`. Telegram-сессию аккаунта @Fortex_Dubai придётся создать заново (вход по коду).

## 3. Секреты GitHub Actions (Settings → Secrets → Actions)

`THREADS_TOKEN` (Threads @ronin.dubai, бывший @fortex__uae), `THREADS_TOKEN_ALEX` (личный Threads @aleks___ruso), `IG_TOKEN` (Instagram Graph API), `OPENROUTER_API_KEY`, `BUNDLE_SOCIAL_API_KEY` (постинг рилсов), `PIXABAY_API_KEY`, `PEXELS_API_KEY` (сток), `FAL_KEY` (картинки и обложки), `ELEVENLABS_API_KEY` (озвучка), `METRIKA_TOKEN` (Яндекс Метрика).

## 4. Внешние сервисы и аккаунты

| Сервис | Для чего | Аккаунт |
|---|---|---|
| Netlify | хостинг сайта (тариф Pro с 08.11, через месяц вернуть на Personal) | Александр |
| GitHub | репозиторий и Actions | fortexglobal |
| OpenRouter | мозг Алексея, автоответов, постов (пополнять, при остатке меньше $5 бот присылает предупреждение) | Александр |
| Meta: Instagram и Threads | @ronin.dubai (от лица Алексея Ронина), @aleks___ruso | Александр |
| Telegram | канал @fortex_uae, аккаунт радара @Fortex_Dubai, боты @Fortex_Radar_Bot, @FortexCheck_Bot | Александр |
| Google (fortexglobal.otc@gmail.com) | Gmail, Календарь (созвоны оранжевым), Диск (бэкап), Таблица CRM `1qg8dezB2VU6yuKryCYLVzcmLw_OpFqD3VkINSzIY-j4`, Apps Script веб-хук | Fortex Global |
| Zoom | встречи с клиентами, Server-to-Server OAuth приложение «Alexey» (marketplace.zoom.us/user/build) | Александр |
| Instantly | холодные письма с alexey@fortex-uae.com, кампании клиенты и партнёры | Александр |
| Apollo, Apify | поиск лидов, тренды Threads и Instagram, звуки | Александр |
| bundle.social | публикация рилсов с трендовыми звуками (бесплатно 20 постов в месяц) | Александр |
| Яндекс Метрика, Вебмастер, Google Search Console | статистика и индексация сайта | Александр |

## 5. Где что лежит в репозитории

- Сайт: `build.py`, `content/` (страницы `pages.py`, `site.py`, статьи `articles/*.md`, лендинги `virtual-work.md`, `ipoteka.md`, `gid.md`, план серии `series/plan.md`), `static/`, `netlify.toml` (редиректы /c/... с готовым текстом в Telegram).
- База знаний Алексея: `tools/radar/kb.md` (главный накопленный актив, правила ведения в шапке файла), архив исходной переписки: `tools/radar/kb_archive/`.
- Threads: `threads/` (@ronin.dubai: очередь `src/`, статусы, ответы, статистика, тренды, выводы `insights.md`), `threads-alex/` (личный @aleks___ruso), код `tools/threads.py`.
- Instagram: `ig/`, `reels/`, `tools/ig.py`, `tools/ig_render.py`, шуточные рилсы `reels/joke/`, `tools/joke/build.py`.
- Канал Telegram: `posts/*.json` (статус approved публикуется сервером в 19:07).
- Статистика: `stats/`, `threads/stats/`, `keeper/status.json` (состояние сервера).

## 6. Как восстановить, если Claude недоступен

1. Сервер, сайт и GitHub Actions продолжают работать сами: Алексей отвечает, посты по уже созданным файлам выходят.
2. Новый ИИ-агент (новый аккаунт Claude, Claude Code или другой) получает доступ к репозиторию GitHub и этой папке бэкапа.
3. Ему дать: этот файл, `kb.md` и тексты задач из `tasks/`. Каждую задачу пересоздать по её тексту и расписанию (в текстах указаны все шаги, файлы и форматы).
4. Подключить заново: Gmail, Google Диск и Таблицы, Календарь, Apify, Apollo (через коннекторы агента).
5. Правила и предпочтения Александра: файл `memory/` в бэкапе.

## 7. Если сломался сервер

1. Новый VPS (Ubuntu), установить по `tools/radar/keeper.sh` и `install*.sh`.
2. Вписать секреты (раздел 2), заново войти в Telegram-аккаунт радара.
3. Вернуть состояние диалогов из последнего архива `archives/fortex-backup-*.tar.gz`, папка `server/radar/` (файлы `*.json`).
4. Отправить боту `/igdm gcal <ссылка>` и `/igdm zoom <ключи>`.

## 8. Если пропал репозиторий

Распаковать последний архив из `archives/` (папка `repo/` внутри: весь код и тексты без медиа), создать новый репозиторий, запушить, подключить к Netlify, вписать секреты GitHub (раздел 3). Медиа (рилсы, картинки) пересоздаются автоматикой.
