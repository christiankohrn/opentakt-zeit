#!/bin/bash
set -euo pipefail
if [ -z "${BASE:-}" ] && [ -f /etc/zeiterfassung/config.toml ]; then
  BASE=$(python3 -c "import tomllib; print(tomllib.load(open('/etc/zeiterfassung/config.toml','rb')).get('public_url','http://127.0.0.1:8000'))")
fi
BASE="${BASE:-http://127.0.0.1:8000}"
SEED=/etc/zeiterfassung/seed-once.txt
EMP_PW=$(awk '/^mitarbeiter / {print $3}' "$SEED")
curl -sS -c /tmp/cj -b /tmp/cj -H 'content-type: application/json' \
  -d "{\"username\":\"MITARBEITER\",\"password\":\"$EMP_PW\"}" \
  "$BASE/api/auth/login"
echo
curl -sS -c /tmp/cj -b /tmp/cj "$BASE/api/me/days?month=2026-08" | python3 -c 'import json,sys; d=json.load(sys.stdin); days=d["days"];
print("days",len(days));
for x in days:
    if x["work_hours"] or x["first_in"] or x["absence"] or (x["soll_hours"] and x["date"]>="2026-08-03"):
        print(x["date"], x.get("absence"), x["first_in"], x["last_out"], x["work_hours"], x["warnings"])'
