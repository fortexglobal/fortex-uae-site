"""Скачивает обложки последних 15 публикаций (для превью сетки). Только чтение. Токен: секрет IG_TOKEN."""
import json, os, urllib.request, urllib.parse
T = os.environ["IG_TOKEN"]; API = "https://graph.instagram.com/v21.0"
os.makedirs("ig/grid", exist_ok=True)
q = urllib.parse.urlencode({"fields": "id,media_type,thumbnail_url,media_url,permalink,timestamp,caption", "limit": 15, "access_token": T})
items = json.load(urllib.request.urlopen(f"{API}/me/media?{q}", timeout=60)).get("data", [])
out = []
for i, m in enumerate(items):
    u = m.get("thumbnail_url") or m.get("media_url")
    f = f"ig/grid/{i:02d}.jpg"
    try:
        urllib.request.urlretrieve(u, f)
    except Exception as e:
        f = None
    out.append({"i": i, "type": m.get("media_type"), "ts": m.get("timestamp"), "file": f, "link": m.get("permalink"), "cap": (m.get("caption") or "")[:60]})
json.dump(out, open("ig/grid/list.json", "w"), ensure_ascii=False, indent=1)
print(len(out))
