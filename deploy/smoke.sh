#!/bin/bash
set -euo pipefail
SEED=/etc/zeiterfassung/seed-once.txt
if [ -z "${BASE:-}" ] && [ -f /etc/zeiterfassung/config.toml ]; then
  BASE=$(python3 -c "import tomllib; print(tomllib.load(open('/etc/zeiterfassung/config.toml','rb')).get('public_url','http://127.0.0.1:8000'))")
fi
BASE="${BASE:-http://127.0.0.1:8000}"
EMP_PW=$(awk '/^mitarbeiter / {print $3}' "$SEED")
HR_PW=$(awk '/^personal / {print $3}' "$SEED")

code=$(curl -sS -o /tmp/index.html -w "%{http_code}" "$BASE/")
echo "GET / $code"
grep -q "Opentakt Zeit" /tmp/index.html

curl -sS -c /tmp/cj -b /tmp/cj -H 'content-type: application/json' \
  -d "{\"username\":\"mitarbeiter\",\"password\":\"$EMP_PW\"}" \
  "$BASE/api/auth/login"
echo
curl -sS -c /tmp/cj -b /tmp/cj "$BASE/api/me/status"
echo
eid=$(python3 -c 'import uuid; print(uuid.uuid4())')
curl -sS -c /tmp/cj -b /tmp/cj -H 'content-type: application/json' \
  -d "{\"kind\":\"in\",\"client_event_id\":\"$eid\"}" \
  "$BASE/api/me/punches"
echo
curl -sS -c /tmp/cj -b /tmp/cj "$BASE/api/me/status"
echo
curl -sS -c /tmp/hr -b /tmp/hr -H 'content-type: application/json' \
  -d "{\"username\":\"personal\",\"password\":\"$HR_PW\"}" \
  "$BASE/api/auth/login"
echo
curl -sS -c /tmp/hr -b /tmp/hr "$BASE/api/hr/users"
echo
echo SMOKE_OK
