#!/bin/bash
# First install on a blank Debian 12/13 machine. Run as root.
#
# Pflicht:
#   DOMAIN=zeit.firma.de EMAIL=it@firma.de ./deploy/new-host.sh
#
# Optional:
#   ORG_NAME="Muster GmbH"
#   ENVIRONMENT=production          (default)
#   SKIP_CERTBOT=1                  ohne Let's Encrypt
#   GIT_URL=https://github.com/christiankohrn/opentakt-zeit.git
#   ENABLE_UNATTENDED=1             (default) automatische Sicherheitsupdates
#
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Bitte als root ausführen" >&2
  exit 1
fi

DOMAIN="${DOMAIN:-}"
EMAIL="${EMAIL:-}"
ORG_NAME="${ORG_NAME:-Opentakt Zeit}"
ENVIRONMENT="${ENVIRONMENT:-production}"
SKIP_CERTBOT="${SKIP_CERTBOT:-0}"
GIT_URL="${GIT_URL:-}"
ENABLE_UNATTENDED="${ENABLE_UNATTENDED:-1}"

if [ -z "$DOMAIN" ]; then
  echo "DOMAIN fehlt. Beispiel: DOMAIN=zeit.firma.de EMAIL=it@firma.de $0" >&2
  exit 1
fi
if [ "$SKIP_CERTBOT" != "1" ] && [ -z "$EMAIL" ]; then
  echo "EMAIL fehlt (Let's Encrypt). Oder SKIP_CERTBOT=1 setzen." >&2
  exit 1
fi

HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=deploy/common.sh
source "$HERE/common.sh"
export DEBIAN_FRONTEND=noninteractive

if [ -r /etc/os-release ]; then
  # shellcheck disable=SC1091
  . /etc/os-release
  case "${ID:-}:${VERSION_ID:-}" in
    debian:12*|debian:13*|debian:14*) ;;
    *) echo "Warnung: getestet auf Debian 12/13, erkannt: ${PRETTY_NAME:-unbekannt}" ;;
  esac
fi

echo "==> Pakete"
apt-get update
apt-get install -y \
  nginx python3 python3-venv python3-pip sqlite3 \
  certbot python3-certbot-nginx rsync curl git ca-certificates \
  ufw fail2ban gnupg
if [ "$ENABLE_UNATTENDED" = "1" ]; then
  apt-get install -y unattended-upgrades
  echo 'unattended-upgrades unattended-upgrades/enable_auto_updates boolean true' | debconf-set-selections
  dpkg-reconfigure -f noninteractive unattended-upgrades || true
fi

echo "==> Node.js"
ensure_node

echo "==> Benutzer, Sudo, Firewall"
ensure_users
ensure_sudoers
ensure_firewall

if [ -n "$GIT_URL" ]; then
  echo "==> Quellcode von $GIT_URL"
  REPO="${REPO:-/tmp/opentakt-zeit-src}"
  rm -rf "$REPO"
  git clone --depth 1 "$GIT_URL" "$REPO"
else
  REPO="${REPO:-$(cd "$HERE/.." && pwd)}"
fi
if [ ! -f "$REPO/deploy/install.sh" ]; then
  echo "Kein App-Tree unter $REPO (GIT_URL setzen oder Script aus dem Repo starten)" >&2
  exit 1
fi

echo "==> App nach $APP_ROOT"
export REPO DOMAIN EMAIL ORG_NAME ENVIRONMENT SKIP_CERTBOT
bash "$REPO/deploy/install.sh"

echo
echo "========================================"
echo "Installation fertig."
echo "  URL:     https://$DOMAIN"
echo "  Code:    $APP_ROOT"
echo "  Config:  $CONF/config.toml"
echo "  Daten:   $DATA/app.db"
echo "  Logins:  $CONF/seed-once.txt  (nur einmal, nicht ins Git)"
echo "  SSH:     ssh deploy@<host>    (gleicher Key wie root, falls vorhanden)"
echo "Update:    sudo $APP_ROOT/deploy/update.sh"
echo "========================================"
