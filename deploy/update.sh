#!/bin/bash
set -euo pipefail
APP_ROOT=/opt/zeiterfassung
DATA=/var/lib/zeiterfassung
STAMP=$(date -u +%Y%m%dT%H%M%SZ)

# shellcheck source=deploy/common.sh
source "$(cd "$(dirname "$0")" && pwd)/common.sh"

ensure_datafox_secret
ensure_esp_terminal_secret
ensure_terminal_http

if [ -f "$DATA/app.db" ]; then
  mkdir -p "$DATA/backups/pre-update"
  sqlite3 "$DATA/app.db" ".backup '$DATA/backups/pre-update/app-$STAMP.db'"
  chown zeiterfassung:zeiterfassung "$DATA/backups/pre-update/app-$STAMP.db" || true
fi

if [ -x "$APP_ROOT/venv/bin/pip" ]; then
  sudo -u deploy "$APP_ROOT/venv/bin/pip" install -r "$APP_ROOT/backend/requirements.txt"
fi
if ! command -v npm >/dev/null 2>&1; then
  echo "npm fehlt — Frontend wird nicht gebaut" >&2
elif [ -f "$APP_ROOT/frontend/package.json" ]; then
  cd "$APP_ROOT/frontend"
  sudo -u deploy npm install
  sudo -u deploy npm run build
fi

install -m 644 "$APP_ROOT/deploy/zeiterfassung-backup.service" /etc/systemd/system/zeiterfassung-backup.service
install -m 644 "$APP_ROOT/deploy/zeiterfassung-backup.timer" /etc/systemd/system/zeiterfassung-backup.timer
systemctl daemon-reload
systemctl enable --now zeiterfassung-backup.timer

systemctl restart zeiterfassung
wait_health "http://127.0.0.1:8000/api/health" || true
echo "Update $STAMP fertig"
