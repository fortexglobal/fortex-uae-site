"""Перед пушем: объединяем наши threads/status.json, replied.json, hot.json с тем, что уже лежит в main,
чтобы два параллельных прогона не теряли отметки (иначе возможны повторные ответы)."""
import json, subprocess

def remote(path):
    r = subprocess.run(["git", "show", f"origin/main:{path}"], capture_output=True, text=True)
    return json.loads(r.stdout) if r.returncode == 0 and r.stdout.strip() else None

subprocess.run(["git", "fetch", "-q", "origin", "main"], check=True)
for p in ("threads/status.json", "threads/replied.json"):
    mine, theirs = json.load(open(p)), remote(p) or {}
    merged = {**theirs, **{k: v for k, v in mine.items() if not (isinstance(theirs.get(k), dict) and not isinstance(v, dict))}}
    json.dump(merged, open(p, "w"), ensure_ascii=False, indent=1)
mine, theirs = json.load(open("threads/hot.json")), remote("threads/hot.json") or []
seen, out = set(), []
for h in theirs + mine:
    key = (h.get("user"), h.get("text"))
    if key not in seen:
        seen.add(key); out.append(h)
json.dump(out[-200:], open("threads/hot.json", "w"), ensure_ascii=False, indent=1)
