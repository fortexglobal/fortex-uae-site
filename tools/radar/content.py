"""Контент Fortex UAE в боте: утверждение постов кнопками, правки голосом, публикация в 19:07.

Данные лежат в репозитории fortexglobal/fortex-uae-site:
  posts/<slug>.json              {"slug","title","post"(Telegram HTML),"status": wait|approved|published, ...}
  content/articles/<slug>.md     статья (status: draft до публикации)
  covers/requests/<slug>.json    заявка на обложку {"prompt","title","topic"}; GitHub Actions рисует
  static/covers/tg/<slug>.jpg    обложка для Telegram
Токен GitHub: файл /opt/radar/github_token (fine-grained, Contents: read and write, только этот репозиторий).
"""
import asyncio, base64, json, logging, os, re, time
from datetime import datetime, timedelta, timezone

import httpx

log = logging.getLogger("content")
BASE = os.path.dirname(os.path.abspath(__file__))
REPO = "fortexglobal/fortex-uae-site"
SITE = "https://fortex-uae.com"
CHANNEL = "@fortex_uae"
DUBAI = timezone(timedelta(hours=4))
PUBLISH_AT = (19, 7)
INDEXNOW_KEY = "c604156419421e0a88c61ad9542e1c13"
EDIT_MODELS = ["anthropic/claude-sonnet-4.5", "openai/gpt-4.1", "google/gemini-2.5-pro"]

CTX = {}          # bot_token, openrouter_key, owner_id(), kv_get, kv_set, transcribe
PENDING = {}      # owner_id -> slug, ждём правку


def setup(**kw):
    CTX.update(kw)


def gh_token():
    try:
        return open(os.path.join(BASE, "github_token")).read().strip()
    except Exception:
        return ""


def gh_headers():
    return {"Authorization": f"Bearer {gh_token()}", "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "fortex-radar"}


async def gh_get(path):
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.get(f"https://api.github.com/repos/{REPO}/contents/{path}", headers=gh_headers(), params={"ref": "main"})
        if r.status_code != 200:
            return None, None
        j = r.json()
        if isinstance(j, list):
            return j, None
        if j.get("content"):
            return base64.b64decode(j["content"]), j["sha"]
        # большие файлы (>1 МБ) отдаются без content
        r2 = await c.get(j["download_url"])
        return r2.content, j["sha"]


async def gh_put(path, data, sha, msg):
    if isinstance(data, str):
        data = data.encode()
    body = {"message": msg, "content": base64.b64encode(data).decode(), "branch": "main",
            "committer": {"name": "Claude", "email": "noreply@anthropic.com"}}
    if sha:
        body["sha"] = sha
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.put(f"https://api.github.com/repos/{REPO}/contents/{path}", headers=gh_headers(), json=body)
        if r.status_code not in (200, 201):
            raise RuntimeError(f"GitHub {r.status_code}: {r.text[:200]}")
        return r.json()["content"]["sha"]


async def load_post(slug):
    raw, sha = await gh_get(f"posts/{slug}.json")
    return (json.loads(raw), sha) if raw else (None, None)


async def tg(method, data=None, files=None):
    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.post(f"https://api.telegram.org/bot{CTX['bot_token']}/{method}", data=data, files=files)
        return r.json()


def kb(slug):
    return json.dumps({"inline_keyboard": [[{"text": "✅ Утверждаю", "callback_data": f"cok:{slug}"[:64]},
                                            {"text": "✏️ Доработать", "callback_data": f"cfix:{slug}"[:64]}]]})


async def send_preview(slug, note=None):
    p, _ = await load_post(slug)
    img, _ = await gh_get(f"static/covers/tg/{slug}.jpg")
    oid = CTX["owner_id"]()
    if note:
        await tg("sendMessage", {"chat_id": oid, "text": note})
    data = {"chat_id": oid, "caption": p["post"], "parse_mode": "HTML", "reply_markup": kb(slug)}
    r = await tg("sendPhoto", data, {"photo": ("cover.jpg", img or b"", "image/jpeg")}) if img else \
        await tg("sendMessage", {"chat_id": oid, "text": p["post"], "parse_mode": "HTML", "reply_markup": kb(slug)})
    if not r.get("ok"):
        log.warning("preview: %s", r)
        await tg("sendMessage", {"chat_id": oid, "text": "Не получилось показать превью: " + str(r.get("description"))})


def next_publish_text():
    now = datetime.now(DUBAI)
    t = now.replace(hour=PUBLISH_AT[0], minute=PUBLISH_AT[1], second=0, microsecond=0)
    return "сегодня в 19:07" if now < t else "завтра в 19:07"


async def on_button(ev):
    action, slug = ev.data.decode().split(":", 1)
    if action in ("cigok", "cigfix"):
        return await ig_button(ev, action, slug)
    if action == "cok":
        p, sha = await load_post(slug)
        if not p:
            return await ev.answer("Пост не найден", alert=True)
        if p.get("status") == "published":
            return await ev.answer("Уже опубликован")
        p["status"] = "approved"; p["approved_at"] = datetime.now(DUBAI).isoformat(timespec="minutes")
        await gh_put(f"posts/{slug}.json", json.dumps(p, ensure_ascii=False, indent=1), sha, f"Approved: {slug}")
        await tg("editMessageReplyMarkup", {"chat_id": ev.chat_id, "message_id": ev.message_id,
                                            "reply_markup": json.dumps({"inline_keyboard": []})})
        await ev.answer("Утверждено ✅")
        await ev.respond(f"✅ Утверждено. Выйдет в канале и на сайте {next_publish_text()}")
    elif action == "cfix":
        PENDING[ev.sender_id] = slug
        await ev.answer()
        await ev.respond("Надиктуй голосовым или напиши, что поправить. Можно про текст поста, статью или картинку")


SYSTEM_EDIT = """Ты редактор контента Fortex UAE (Дубай: счета в банках ОАЭ для владельцев российского паспорта, сложные случаи, рабочие визы, ВНЖ, компании).
Тебе дают пост для Telegram-канала (Telegram HTML), заголовок обложки, статью для сайта (markdown с шапкой ---) и правки от владельца (часто расшифровка голосового, разговорная речь).
Внеси ровно те правки, о которых он просит, остальное не трогай. Не выдумывай факты, цены и кейсы.
Правила поста: заголовок первой строкой в <b>…</b>; короткие абзацы, между мыслями пустая строка; ключевой факт в <blockquote>; 1–2 выделения <b> внутри, иногда <i>; эмодзи не больше 2–3; без хэштегов; без длинных тире (— и –), без точки в самом конце, без слова «профиль»; последняя строка со ссылками оставь как есть; до 950 знаков с тегами. Допустимые теги: b, i, u, s, a, blockquote, code.
Правила статьи: шапку (между ---) не меняй, кроме title и description, если об этом просят; без длинных тире.
Обложка: на ней фон-картинка по теме и короткая основная мысль (до 50 символов).
Ответь строго JSON без пояснений:
{"post": "<новый пост>", "cover_title": "<текст на обложке>", "new_picture": false, "picture_prompt": "<если нужна новая картинка: английское описание фотосцены без текста, логотипов и лиц, иначе пусто>", "article_md": "<полный новый текст статьи, ТОЛЬКО если правки касаются статьи, иначе пусто>", "summary": "<что поменял, 1–2 коротких предложения>"}"""


async def llm_edit(post, cover_title, article, instruction):
    msgs = [{"role": "system", "content": SYSTEM_EDIT},
            {"role": "user", "content": f"ПОСТ:\n{post}\n\nОБЛОЖКА: {cover_title}\n\nСТАТЬЯ:\n{article}\n\nПРАВКИ:\n{instruction}"}]
    async with httpx.AsyncClient(timeout=240) as c:
        for m in EDIT_MODELS:
            try:
                r = await c.post("https://openrouter.ai/api/v1/chat/completions",
                                 headers={"Authorization": f"Bearer {CTX['openrouter_key']}", "Content-Type": "application/json",
                                          "HTTP-Referer": SITE, "X-Title": "Fortex Content"},
                                 json={"model": m, "messages": msgs, "temperature": 0.2, "max_tokens": 8000,
                                       "response_format": {"type": "json_object"}})
                if r.status_code != 200:
                    log.warning("edit %s -> %s %s", m, r.status_code, r.text[:200]); continue
                out = r.json()["choices"][0]["message"]["content"]
                mm = re.search(r"\{.*\}", out, re.S)
                if mm:
                    return json.loads(mm.group(0))
            except Exception as e:
                log.warning("edit error %s: %s", m, e)
    return None


async def wait_cover(slug, old_mark_sha, minutes=7):
    for _ in range(minutes * 4):
        await asyncio.sleep(15)
        _, sha = await gh_get(f"covers/rendered/{slug}.txt")
        if sha and sha != old_mark_sha:
            return True
    return False


async def revise(ev, slug, instruction):
    await ev.respond("Принял, правлю…")
    p, psha = await load_post(slug)
    req_raw, rsha = await gh_get(f"covers/requests/{slug}.json")
    req = json.loads(req_raw) if req_raw else {}
    art_raw, asha = await gh_get(f"content/articles/{slug}.md")
    article = art_raw.decode() if art_raw else ""
    res = await llm_edit(p["post"], req.get("title", ""), article, instruction)
    if not res or not res.get("post"):
        return await ev.respond("Не получилось внести правки, попробуй сформулировать ещё раз")
    p["post"] = res["post"].strip(); p["status"] = "wait"
    p.setdefault("edits", []).append({"at": datetime.now(DUBAI).isoformat(timespec="minutes"), "what": instruction[:500]})
    await gh_put(f"posts/{slug}.json", json.dumps(p, ensure_ascii=False, indent=1), psha, f"Post edit: {slug}")
    if res.get("article_md") and res["article_md"].strip().startswith("---") and asha:
        await gh_put(f"content/articles/{slug}.md", res["article_md"].strip() + "\n", asha, f"Article edit: {slug}")
    cover_changed = False
    new_title = (res.get("cover_title") or "").strip()
    if req and ((new_title and new_title != req.get("title")) or res.get("new_picture")):
        _, mark_sha = await gh_get(f"covers/rendered/{slug}.txt")
        if new_title:
            req["title"] = new_title
        if res.get("new_picture"):
            req["new_bg"] = True
            if res.get("picture_prompt"):
                req["prompt"] = res["picture_prompt"]
        await gh_put(f"covers/requests/{slug}.json", json.dumps(req, ensure_ascii=False, indent=1), rsha, f"Cover edit: {slug}")
        await ev.respond("Перерисовываю обложку, это пара минут…")
        cover_changed = await wait_cover(slug, mark_sha)
    note = "Поправил: " + (res.get("summary") or "готово")
    if req and not cover_changed and (new_title != req.get("title") or res.get("new_picture")):
        note += "\nОбложка ещё рисуется, пришлю её с постом при публикации"
    await send_preview(slug, note)


async def maybe_handle(ev, text):
    """Вызывается из on_owner_text до остальной логики. True = сообщение обработано здесь."""
    slug = PENDING.pop(ev.sender_id, None)
    if not slug:
        return False
    if ev.voice or ev.audio:
        await ev.respond("Расшифровываю…")
        text = await CTX["transcribe"](ev)
        if not text:
            PENDING[ev.sender_id] = slug
            await ev.respond("Не расшифровалось, попробуй ещё раз или напиши текстом")
            return True
        await ev.respond("Понял так:\n" + text[:1500])
    if not text.strip():
        PENDING[ev.sender_id] = slug
        return True
    try:
        if slug.startswith("ig:"):
            return await ig_revise(ev, slug[3:], text) or True
        await revise(ev, slug, text)
    except Exception as e:
        log.exception("revise")
        await ev.respond(f"Ошибка при правке: {e}")
    return True


async def page_live(url):
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as c:
            r = await c.get(url, params={"t": int(time.time())})
            return r.status_code == 200 and 'http-equiv="refresh"' not in r.text
    except Exception:
        return False


async def publish(slug):
    p, psha = await load_post(slug)
    oid = CTX["owner_id"]()
    url = f"{SITE}/articles/{slug}/"
    raw, asha = await gh_get(f"content/articles/{slug}.md")
    if raw:
        md = raw.decode()
        today = datetime.now(DUBAI).date().isoformat()
        md2 = re.sub(r"^status:\s*draft\s*\n", "", md, flags=re.M)
        md2 = re.sub(r"^date:.*$", f"date: {today}", md2, count=1, flags=re.M)
        if md2 != md:
            await gh_put(f"content/articles/{slug}.md", md2, asha, f"Publish: {slug}")
        for _ in range(30):  # ждём выкладку Netlify до 15 минут
            if await page_live(url):
                break
            await asyncio.sleep(30)
    img, _ = await gh_get(f"static/covers/tg/{slug}.jpg")
    data = {"chat_id": CHANNEL, "caption": p["post"], "parse_mode": "HTML"}
    r = await tg("sendPhoto", data, {"photo": ("cover.jpg", img, "image/jpeg")}) if img else \
        await tg("sendMessage", {"chat_id": CHANNEL, "text": p["post"], "parse_mode": "HTML"})
    if not r.get("ok"):
        await tg("sendMessage", {"chat_id": oid, "text": f"Не получилось опубликовать «{p['title']}» в канал: {r.get('description')}"})
        return
    mid = r["result"]["message_id"]
    p.update(status="published", published_at=datetime.now(DUBAI).isoformat(timespec="minutes"), url=url,
             channel_post=f"https://t.me/{CHANNEL.lstrip('@')}/{mid}")
    _, psha = await load_post(slug)
    await gh_put(f"posts/{slug}.json", json.dumps(p, ensure_ascii=False, indent=1), psha, f"Published: {slug}")
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            await c.get("https://yandex.com/indexnow", params={"url": url, "key": INDEXNOW_KEY})
    except Exception:
        pass
    await tg("sendMessage", {"chat_id": oid, "disable_web_page_preview": "true",
                             "text": f"Опубликовано: {p['title']}\nКанал: {p['channel_post']}\nСайт: {url}"})


async def scheduler():
    while True:
        try:
            now = datetime.now(DUBAI)
            day = now.date().isoformat()
            if (now.hour, now.minute) >= PUBLISH_AT and CTX["kv_get"]("content_pub_day") != day and gh_token():
                CTX["kv_set"]("content_pub_day", day)
                lst, _ = await gh_get("posts")
                for f in lst or []:
                    if not f["name"].endswith(".json"):
                        continue
                    p, _ = await load_post(f["name"][:-5])
                    if p and p.get("status") == "approved":
                        try:
                            await publish(p["slug"])
                        except Exception as e:
                            log.exception("publish")
                            await tg("sendMessage", {"chat_id": CTX["owner_id"](), "text": f"Ошибка публикации {p['slug']}: {e}"})
        except Exception:
            log.exception("scheduler")
        await asyncio.sleep(60)



# ===== Instagram: карусели на утверждение =====
# ig/src/<slug>.json {"caption","slides":[...],"status": wait|approved|published, "bg_prompt"}
# ig/<slug>/render.json {"hash","files"}; рисует и публикует GitHub Actions (workflow instagram.yml)

def ig_kb(slug):
    return json.dumps({"inline_keyboard": [[{"text": "✅ Утверждаю", "callback_data": f"cigok:{slug}"[:64]},
                                            {"text": "✏️ Доработать", "callback_data": f"cigfix:{slug}"[:64]}]]})


async def send_ig_preview(slug, note=None):
    oid = CTX["owner_id"]()
    raw, _ = await gh_get(f"ig/src/{slug}.json")
    meta, _ = await gh_get(f"ig/{slug}/render.json")
    if not raw or not meta:
        return await tg("sendMessage", {"chat_id": oid, "text": f"Карусель {slug} ещё не готова"})
    src, files = json.loads(raw), json.loads(meta)["files"]
    if note:
        await tg("sendMessage", {"chat_id": oid, "text": note})
    for k in range(0, len(files), 10):
        media, up = [], {}
        for i, f in enumerate(files[k:k + 10]):
            img, _ = await gh_get(f"ig/{slug}/{f}")
            up[f"p{i}"] = (f, img, "image/jpeg")
            media.append({"type": "photo", "media": f"attach://p{i}"})
        await tg("sendMediaGroup", {"chat_id": oid, "media": json.dumps(media)}, up)
    await tg("sendMessage", {"chat_id": oid, "text": "Подпись в Instagram:\n\n" + src.get("caption", ""), "reply_markup": ig_kb(slug)})


async def ig_wait_published(slug, minutes=15):
    for _ in range(minutes * 2):
        await asyncio.sleep(30)
        raw, _ = await gh_get(f"ig/src/{slug}.json")
        src = json.loads(raw) if raw else {}
        if src.get("status") == "published":
            link = (src.get("result") or {}).get("permalink", "")
            return await tg("sendMessage", {"chat_id": CTX["owner_id"](), "text": f"Вышло в Instagram ✅\n{link}"})
        if src.get("status") == "error":
            return await tg("sendMessage", {"chat_id": CTX["owner_id"](), "text": f"Instagram не принял карусель {slug}: {str(src.get('result'))[:300]}"})
    await tg("sendMessage", {"chat_id": CTX["owner_id"](), "text": f"Карусель {slug} пока не вышла, проверю позже"})


async def ig_button(ev, action, slug):
    if action == "cigok":
        raw, sha = await gh_get(f"ig/src/{slug}.json")
        if not raw:
            return await ev.answer("Карусель не найдена", alert=True)
        src = json.loads(raw)
        if src.get("status") == "published":
            return await ev.answer("Уже опубликована")
        src["status"] = "approved"; src["approved_at"] = datetime.now(DUBAI).isoformat(timespec="minutes")
        await gh_put(f"ig/src/{slug}.json", json.dumps(src, ensure_ascii=False, indent=1), sha, f"IG approved: {slug}")
        await tg("editMessageReplyMarkup", {"chat_id": ev.chat_id, "message_id": ev.message_id,
                                            "reply_markup": json.dumps({"inline_keyboard": []})})
        await ev.answer("Утверждено ✅")
        await ev.respond("✅ Утверждено. Публикую в Instagram, это пара минут")
        asyncio.get_event_loop().create_task(ig_wait_published(slug))
    else:
        PENDING[ev.sender_id] = "ig:" + slug
        await ev.answer()
        await ev.respond("Надиктуй голосовым или напиши, что поправить в карусели. Можно про слайды, подпись или фото на обложке")


SYSTEM_IG = """Ты редактор Instagram Fortex UAE (Дубай: счета в банках ОАЭ для владельцев российского паспорта, сложные случаи, рабочие визы, ВНЖ, компании).
Тебе дают карусель в JSON (caption и slides) и правки владельца (часто расшифровка голосового). Внеси ровно эти правки, остальное не трогай.
Не выдумывай факты, цены и кейсы. Без длинных тире (— и –), без слова «профиль». Текст на слайде короткий: заголовок до 35 знаков, body до 160 знаков. **жирное** выделяет золотом.
Типы слайдов: cover {tag,title,accent}, text {title,body}, list {title,items}, case {title,stat,body}, compare {title,cols:[{h,items}]}, cta {title,body}. Первый слайд cover, последний cta, всего до 10.
Ответь строго JSON: {"caption": "...", "slides": [...], "new_picture": false, "picture_prompt": "<если нужна новая фотография на обложку: английское описание сцены без текста, логотипов и лиц, иначе пусто>", "summary": "<что поменял, коротко>"}"""


async def llm_json(system, user):
    async with httpx.AsyncClient(timeout=240) as c:
        for m in EDIT_MODELS:
            try:
                r = await c.post("https://openrouter.ai/api/v1/chat/completions",
                                 headers={"Authorization": f"Bearer {CTX['openrouter_key']}", "Content-Type": "application/json",
                                          "HTTP-Referer": SITE, "X-Title": "Fortex Content"},
                                 json={"model": m, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                                       "temperature": 0.2, "max_tokens": 8000, "response_format": {"type": "json_object"}})
                if r.status_code != 200:
                    continue
                mm = re.search(r"\{.*\}", r.json()["choices"][0]["message"]["content"], re.S)
                if mm:
                    return json.loads(mm.group(0))
            except Exception as e:
                log.warning("llm_json %s: %s", m, e)
    return None


async def ig_revise(ev, slug, instruction):
    await ev.respond("Принял, правлю…")
    raw, sha = await gh_get(f"ig/src/{slug}.json")
    src = json.loads(raw)
    res = await llm_json(SYSTEM_IG, "КАРУСЕЛЬ:\n" + json.dumps({"caption": src["caption"], "slides": src["slides"]}, ensure_ascii=False, indent=1)
                         + "\n\nПРАВКИ:\n" + instruction)
    if not res or not res.get("slides"):
        PENDING[ev.sender_id] = "ig:" + slug
        return await ev.respond("Не получилось внести правки, сформулируй ещё раз")
    _, meta_sha = await gh_get(f"ig/{slug}/render.json")
    src.update(caption=res.get("caption") or src["caption"], slides=res["slides"], status="wait")
    if res.get("new_picture"):
        src["new_bg"] = True
        if res.get("picture_prompt"):
            src["bg_prompt"] = res["picture_prompt"]
    src.setdefault("edits", []).append({"at": datetime.now(DUBAI).isoformat(timespec="minutes"), "what": instruction[:500]})
    await gh_put(f"ig/src/{slug}.json", json.dumps(src, ensure_ascii=False, indent=1), sha, f"IG edit: {slug}")
    await ev.respond("Перерисовываю слайды, пара минут…")
    for _ in range(40):
        await asyncio.sleep(15)
        _, s2 = await gh_get(f"ig/{slug}/render.json")
        if s2 and s2 != meta_sha:
            break
    await send_ig_preview(slug, "Поправил: " + (res.get("summary") or "готово"))
