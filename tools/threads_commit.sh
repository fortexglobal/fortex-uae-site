#!/bin/bash
# Надёжное сохранение результатов Threads: копируем то, что изменил этот прогон, берём свежий main,
# возвращаем наши файлы (status/replied/hot объединяются с тем, что уже в main), пушим. До 4 попыток.
git config user.name "Claude"; git config user.email "noreply@anthropic.com"
T=$(mktemp -d)
FILES=$( (git diff --name-only -- threads; git ls-files --others --exclude-standard -- threads) | sort -u)
[ -z "$FILES" ] && { echo "нечего сохранять"; exit 0; }
for f in $FILES; do [ -f "$f" ] && mkdir -p "$T/$(dirname $f)" && cp "$f" "$T/$f"; done
for i in 1 2 3 4; do
  git fetch -q origin main && git reset -q --hard origin/main
  for f in $FILES; do [ -f "$T/$f" ] && mkdir -p "$(dirname $f)" && cp "$T/$f" "$f"; done
  python3 tools/threads_sync.py || true   # объединяет status/replied/hot с версией из main
  git add threads
  git diff --cached --quiet && { echo "без изменений"; exit 0; }
  git commit -q -m "Threads status" && git push -q origin HEAD:main && { echo "сохранено"; exit 0; }
  sleep $((i * 7))
done
echo "не удалось сохранить"; exit 1
