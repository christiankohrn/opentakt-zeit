#!/bin/bash
set -euo pipefail
# Aktualisiert eine laufende Installation. Als root bzw. per sudo laufen lassen.
#
# Manuell (Code wurde vorher per rsync nach /opt/zeiterfassung kopiert):
#   sudo /opt/zeiterfassung/deploy/update.sh
# Aus der Weboberfläche (GitHub ist die Quelle, systemd-Path-Unit ruft auf):
#   update.sh --from-web   (klont, kopiert, startet sich als --continue-from-web neu)
APP_ROOT=/opt/zeiterfassung
DATA=/var/lib/zeiterfassung
export DATA
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
MODE="${1:-}"

# shellcheck source=deploy/common.sh
source "$(cd "$(dirname "$0")" && pwd)/common.sh"

LOG="$DATA/update.log"
META="$DATA/.update-meta.json"
LOCK="$DATA/update.lock"

if [ ! -w "$DATA" ]; then
  echo "Keine Schreibrechte auf $DATA — als root bzw. mit sudo starten." >&2
  exit 1
fi
# --from-web übergibt per exec an --continue-from-web. Die Sperre bleibt liegen,
# der zweite Prozess übernimmt sie (kein zweites mkdir, sonst bricht er ab).
if [ "$MODE" = "--continue-from-web" ]; then
  if [ ! -d "$LOCK" ]; then
    echo "Update-Sperre fehlt. Abbruch." >&2
    update_state failed "Update-Sperre fehlt."
    exit 1
  fi
elif ! mkdir "$LOCK" 2>/dev/null; then
  echo "Ein Update läuft bereits. Abbruch."
  exit 0
fi
trap 'rmdir "$LOCK" 2>/dev/null || true' EXIT

# Die zweite Phase (--continue-from-web) hakt sich per exec ein und hängt an.
if [ "$MODE" != "--continue-from-web" ]; then
  : >"$LOG"
fi
exec > >(tee -a "$LOG") 2>&1

fail() {
  echo "FEHLER: $1" >&2
  update_state failed "$1"
  exit 1
}

if [ "$MODE" = "--from-web" ]; then
  rm -f "$DATA/update.request"
  update_state running
  echo "==> Klone von GitHub ($STAMP)"
  WORK="$DATA/tmp-update"
  rm -rf "$WORK"
  GIT_URL="${GIT_URL:-https://github.com/christiankohrn/opentakt-zeit.git}"
  git clone --depth 1 "$GIT_URL" "$WORK" || fail "GitHub-Klon ist fehlgeschlagen."
  git_meta_json "$WORK" >"$META" || fail "Commit konnte nicht gelesen werden."
  rsync -a --delete \
    --exclude '.git' \
    --exclude 'node_modules' \
    --exclude '.venv' \
    --exclude 'backend/.venv' \
    --exclude 'frontend/node_modules' \
    --exclude 'frontend/dist' \
    --exclude 'data' \
    --exclude 'venv' \
    --exclude 'lib' \
    "$WORK"/ "$APP_ROOT"/
  rm -rf "$WORK"
  chmod a+x "$APP_ROOT/deploy/"*.sh
  echo "==> Code synchron, starte neue Version"
  exec bash "$APP_ROOT/deploy/update.sh" --continue-from-web
fi

FROM_WEB=0
if [ "$MODE" = "--continue-from-web" ]; then
  FROM_WEB=1
fi

if [ "$MODE" != "" ] && [ "$MODE" != "--continue-from-web" ]; then
  echo "Unbekannte Option: $MODE" >&2
  exit 1
fi

# rsync as root leaves the tree root-owned; pip and npm run as deploy.
chown -R deploy:zeiterfassung "$APP_ROOT"
chmod a+x "$APP_ROOT/deploy/"*.sh

ensure_datafox_secret
ensure_esp_terminal_secret
ensure_terminal_http

if [ -f "$DATA/app.db" ]; then
  mkdir -p "$DATA/backups/pre-update"
  sqlite3 "$DATA/app.db" ".backup '$DATA/backups/pre-update/app-$STAMP.db'" \
    || fail "Datenbank-Backup ist fehlgeschlagen."
  chown zeiterfassung:zeiterfassung "$DATA/backups/pre-update/app-$STAMP.db" || true
  chmod 600 "$DATA/backups/pre-update/app-$STAMP.db"
fi

if [ -x "$APP_ROOT/venv/bin/pip" ]; then
  sudo -u deploy "$APP_ROOT/venv/bin/pip" install -r "$APP_ROOT/backend/requirements.txt" \
    || fail "pip install ist fehlgeschlagen."
fi
if ! command -v npm >/dev/null 2>&1; then
  echo "npm fehlt — Frontend wird nicht gebaut" >&2
elif [ -f "$APP_ROOT/frontend/package.json" ]; then
  cd "$APP_ROOT/frontend"
  sudo -u deploy npm install || fail "npm install ist fehlgeschlagen."
  sudo -u deploy npm run build || fail "Frontend-Build ist fehlgeschlagen."
fi

install -m 644 "$APP_ROOT/deploy/zeiterfassung-backup.service" /etc/systemd/system/zeiterfassung-backup.service
install -m 644 "$APP_ROOT/deploy/zeiterfassung-backup.timer" /etc/systemd/system/zeiterfassung-backup.timer
install_update_units
systemctl daemon-reload
systemctl enable --now zeiterfassung-backup.timer

# Installierten Stand festhalten: aus dem Web-Klon oder, manuell, aus /tmp.
META_COMMIT=""
META_DATE=""
META_MSG=""
if [ "$FROM_WEB" = "1" ] && [ -f "$META" ]; then
  eval "$(python3 - "$META" <<'PY'
import json
import shlex
import sys

try:
    d = json.load(open(sys.argv[1], encoding="utf-8"))
except (OSError, ValueError):
    d = {}
print("META_COMMIT=" + shlex.quote(str(d.get("commit") or "")))
print("META_DATE=" + shlex.quote(str(d.get("commit_date") or "")))
print("META_MSG=" + shlex.quote(str(d.get("message") or "")))
PY
)"
  rm -f "$META"
  if [ -n "$META_COMMIT" ]; then
    write_version_json "$META_COMMIT" "$META_DATE" "$META_MSG"
  fi
elif [ -d "/tmp/opentakt-zeit/.git" ]; then
  write_version_from_dir /tmp/opentakt-zeit
fi

systemctl restart zeiterfassung
if wait_health "http://127.0.0.1:8000/api/health"; then
  update_state done "" "$META_COMMIT"
  echo "Update $STAMP fertig"
else
  fail "Der Dienst startet nach dem Update nicht."
fi
