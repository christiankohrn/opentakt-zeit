#!/bin/bash
# Rauchtest nach Neuinstallation. Der Seed legt nur den Admin an; das Skript
# wechselt dessen Passwort (Erstlogin-Zwang), legt Mitarbeiter + Personal an
# und prüft Stempeln sowie die HR-Liste.
set -euo pipefail
SEED=/etc/zeiterfassung/seed-once.txt
if [ -z "${BASE:-}" ] && [ -f /etc/zeiterfassung/config.toml ]; then
  BASE=$(python3 -c "import tomllib; print(tomllib.load(open('/etc/zeiterfassung/config.toml','rb')).get('public_url','http://127.0.0.1:8000'))")
fi
BASE="${BASE:-http://127.0.0.1:8000}"
ADMIN_PW=$(awk '/^admin / {print $3}' "$SEED")
NEW_ADMIN_PW=$(python3 -c 'import secrets; print(secrets.token_urlsafe(16))')
EMP_PW=$(python3 -c 'import secrets; print(secrets.token_urlsafe(16))')
HR_PW=$(python3 -c 'import secrets; print(secrets.token_urlsafe(16))')

code=$(curl -sS -o /tmp/index.html -w "%{http_code}" "$BASE/")
echo "GET / $code"
grep -q "Opentakt Zeit" /tmp/index.html

curl -sS -c /tmp/cj-admin -b /tmp/cj-admin -H 'content-type: application/json' \
  -d "{\"username\":\"admin\",\"password\":\"$ADMIN_PW\"}" \
  "$BASE/api/auth/login"
echo
curl -sS -c /tmp/cj-admin -b /tmp/cj-admin -H 'content-type: application/json' \
  -d "{\"current_password\":\"$ADMIN_PW\",\"new_password\":\"$NEW_ADMIN_PW\"}" \
  "$BASE/api/me/password"
echo
MODEL_ID=$(curl -sS -b /tmp/cj-admin "$BASE/api/hr/work-models" | python3 -c 'import json,sys; print(json.load(sys.stdin)[0]["id"])')
curl -sS -b /tmp/cj-admin -H 'content-type: application/json' \
  -d "{\"username\":\"mitarbeiter\",\"display_name\":\"Max Mustermann\",\"role\":\"employee\",\"password\":\"$EMP_PW\",\"work_model_id\":$MODEL_ID,\"web_login\":true}" \
  "$BASE/api/hr/users" > /dev/null
curl -sS -b /tmp/cj-admin -H 'content-type: application/json' \
  -d "{\"username\":\"personal\",\"display_name\":\"Personal\",\"role\":\"hr\",\"password\":\"$HR_PW\",\"work_model_id\":$MODEL_ID,\"web_login\":true}" \
  "$BASE/api/hr/users" > /dev/null

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
