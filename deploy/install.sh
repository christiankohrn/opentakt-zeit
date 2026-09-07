#!/bin/bash
set -euo pipefail
# Install or repair the app on a Debian host. Run as root from the repo root
# or with REPO=/path/to/tree.
#
# Env: DOMAIN EMAIL ORG_NAME ENVIRONMENT SKIP_CERTBOT

REPO="${REPO:-$(cd "$(dirname "$0")/.." && pwd)}"
APP_ROOT=/opt/zeiterfassung
DATA=/var/lib/zeiterfassung
CONF=/etc/zeiterfassung
DOMAIN="${DOMAIN:-}"
LE_EMAIL="${EMAIL:-${LE_EMAIL:-}}"
ORG_NAME="${ORG_NAME:-Opentakt Zeit}"
ENVIRONMENT="${ENVIRONMENT:-production}"
SKIP_CERTBOT="${SKIP_CERTBOT:-0}"

if [ "$(id -u)" -ne 0 ]; then
  echo "Bitte als root ausführen" >&2
  exit 1
fi
if [ -z "$DOMAIN" ]; then
  echo "DOMAIN fehlt. Beispiel: DOMAIN=zeit.firma.de EMAIL=it@firma.de $0" >&2
  exit 1
fi

# shellcheck source=deploy/common.sh
source "$(cd "$(dirname "$0")" && pwd)/common.sh"

export DEBIAN_FRONTEND=noninteractive
apt-get install -y nginx python3 python3-venv sqlite3 certbot python3-certbot-nginx rsync curl
ensure_node
ensure_users
ensure_sudoers

mkdir -p "$APP_ROOT" "$DATA" "$DATA/backups" "$CONF"
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
  "$REPO"/ "$APP_ROOT"/

chown -R deploy:zeiterfassung "$APP_ROOT"
chown -R zeiterfassung:zeiterfassung "$DATA"
chown root:zeiterfassung "$CONF"
chmod 750 "$DATA" "$CONF"
chmod a+x "$APP_ROOT/deploy/"*.sh

if [ ! -f "$CONF/config.toml" ]; then
  SECRET=$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')
  DATAFOX=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')
  ADMIN_PW=$(python3 -c 'import secrets; print(secrets.token_urlsafe(12))')
  HR_PW=$(python3 -c 'import secrets; print(secrets.token_urlsafe(12))')
  EMP_PW=$(python3 -c 'import secrets; print(secrets.token_urlsafe(12))')
  SHIFT_PW=$(python3 -c 'import secrets; print(secrets.token_urlsafe(12))')
  cat >"$CONF/config.toml" <<EOF
environment = "$ENVIRONMENT"
secret_key = "$SECRET"
timezone = "Europe/Berlin"
org_name = "$ORG_NAME"
public_url = "https://$DOMAIN"
bundesland = "NW"
database_path = "$DATA/app.db"
listen_host = "127.0.0.1"
listen_port = 8000
datafox_secret = "$DATAFOX"

[seed]
admin_username = "admin"
admin_password = "$ADMIN_PW"
hr_username = "personal"
hr_password = "$HR_PW"
employee_username = "mitarbeiter"
employee_password = "$EMP_PW"
shift_username = "erika"
shift_password = "$SHIFT_PW"

[smtp]
enabled = false

[ldap]
enabled = false
EOF
  chmod 640 "$CONF/config.toml"
  chown root:zeiterfassung "$CONF/config.toml"
  cat >"$CONF/seed-once.txt" <<EOF
admin / $ADMIN_PW
personal / $HR_PW
mitarbeiter / $EMP_PW
erika / $SHIFT_PW
EOF
  chmod 600 "$CONF/seed-once.txt"
fi

install -m 644 "$APP_ROOT/deploy/zeiterfassung.service" /etc/systemd/system/zeiterfassung.service
install -m 644 "$APP_ROOT/deploy/zeiterfassung-jobs.service" /etc/systemd/system/zeiterfassung-jobs.service
install -m 644 "$APP_ROOT/deploy/zeiterfassung-jobs.timer" /etc/systemd/system/zeiterfassung-jobs.timer
install -m 644 "$APP_ROOT/deploy/zeiterfassung-backup.service" /etc/systemd/system/zeiterfassung-backup.service
install -m 644 "$APP_ROOT/deploy/zeiterfassung-backup.timer" /etc/systemd/system/zeiterfassung-backup.timer
render_nginx "$DOMAIN" "$APP_ROOT/deploy/nginx.conf"

sudo -u deploy python3 -m venv "$APP_ROOT/venv"
sudo -u deploy "$APP_ROOT/venv/bin/pip" install --upgrade pip
sudo -u deploy "$APP_ROOT/venv/bin/pip" install -r "$APP_ROOT/backend/requirements.txt"

cd "$APP_ROOT/frontend"
sudo -u deploy npm install
sudo -u deploy npm run build

systemctl daemon-reload
systemctl enable --now zeiterfassung.service zeiterfassung-jobs.timer zeiterfassung-backup.timer
nginx -t
systemctl reload nginx

if [ "$SKIP_CERTBOT" != "1" ]; then
  if [ -z "$LE_EMAIL" ]; then
    echo "EMAIL/LE_EMAIL fehlt — Certbot übersprungen. Später: certbot --nginx -d $DOMAIN" >&2
  else
    certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos -m "$LE_EMAIL" --redirect \
      || echo "Certbot fehlgeschlagen. DNS A/AAAA für $DOMAIN und Port 80 prüfen, dann erneut: certbot --nginx -d $DOMAIN" >&2
    ensure_terminal_http
  fi
fi

systemctl restart zeiterfassung
wait_health "http://127.0.0.1:8000/api/health" || true
echo "Install fertig. Seed-Daten (falls neu): $CONF/seed-once.txt"
