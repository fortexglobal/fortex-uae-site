"""Последние ответы ассистента в чатах: вопрос из чата → наш ответ (и продолжение ветки).
python3 /opt/radar/replies_dump.py [N]   (по умолчанию 20)
Имена и id людей не выводятся, только тексты и название чата."""
import json, sqlite3, sys, glob

N = int(sys.argv[1]) if len(sys.argv) > 1 else 20
s = json.load(open("/opt/radar/autoreply.json"))
titles = {}
for db in glob.glob("/opt/radar/*.db") + glob.glob("/opt/radar/*.sqlite*"):
    try:
        con = sqlite3.connect(db)
        for t in [r[0] for r in con.execute("select name from sqlite_master where type='table'")]:
            cols = [c[1] for c in con.execute(f"pragma table_info({t})")]
            if "chat_id" in cols and ("title" in cols or "chat_title" in cols):
                tc = "title" if "title" in cols else "chat_title"
                for cid, ti in con.execute(f"select chat_id, {tc} from {t}"):
                    titles[str(cid)] = ti
    except Exception:
        pass
items = list(s.get("threads", {}).items())[-N:]
print(f"Ответов в памяти: {len(s.get('threads', {}))}, показываю последние {len(items)}\n")
for i, (key, t) in enumerate(items, 1):
    cid = key.split(":")[0]
    print(f"{i}. [{titles.get(cid, cid)}]")
    print("   Вопрос: " + (t.get("root") or "").replace("\n", " ")[:400])
    for j, h in enumerate(t.get("history", [])):
        print(("   Мы: " if j == 0 else "   …дальше мы: ") + h.replace("\n", " "))
    print()
