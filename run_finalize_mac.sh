#!/bin/bash
# Finalize vanaf de Mac, elke 5 minuten (LaunchAgent com.betexperts.opstellingen-finalize).
# GitHub Actions (finalize.yml) blijft draaien als vangnet wanneer de Mac uit staat.
# Beide flippen alleen artikelen die nog niet definitief zijn; state wordt vóór het pushen samengevoegd.
cd "$(dirname "$0")" || exit 1
H=$(date +%H)
if [ "$H" -ge 1 ] && [ "$H" -lt 8 ]; then exit 0; fi           # 's nachts niets te doen (01:00-08:00)
LOCK=/tmp/opstellingen-finalize.lock
mkdir "$LOCK" 2>/dev/null || exit 0                             # vorige run nog bezig
trap 'rmdir "$LOCK"' EXIT
set -a; . ../superodd-agent/.env; set +a
PY=../superodd-agent/.venv/bin/python
echo "== $(date '+%Y-%m-%d %H:%M')"

sync_push() {   # $1 = commitbericht
  git add state/opstellingen.json og/*.webp 2>/dev/null
  git diff --cached --quiet && return 0
  git commit -q -m "$1 [skip ci]"
  for i in 1 2 3; do
    git push -q origin HEAD:main 2>/dev/null && return 0
    git pull -q --rebase -X theirs origin main || { git rebase --abort 2>/dev/null; }
  done
  echo "! push mislukt"; return 1
}

git pull -q --rebase -X theirs origin main || { git rebase --abort 2>/dev/null; echo "! pull mislukt"; exit 1; }
$PY finalize.py
sync_push "state: definitief geflipt (Mac)" || exit 1
# nog niet gekoppelde deelafbeeldingen? (bestand staat nu op GitHub) -> koppelen
if $PY -c "import json,sys;s=json.load(open('state/opstellingen.json'));sys.exit(0 if any(e.get('og') and e.get('og_done')!=e['og'] for e in s.values()) else 1)"; then
  sleep 5
  $PY attach_og.py
  sync_push "state: deelafbeeldingen gekoppeld (Mac)"
fi
