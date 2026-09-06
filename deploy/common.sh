#!/bin/bash
# Shared helpers for new-host.sh / install.sh / update.sh. Source only.

APP_ROOT="${APP_ROOT:-/opt/zeiterfassung}"
DATA="${DATA:-/var/lib/zeiterfassung}"
CONF="${CONF:-/etc/zeiterfassung}"

wait_health() {
  local url="${1:-http://127.0.0.1:8000/api/health}"
  local i
  for i in $(seq 1 40); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      echo "Health OK ($url)"
      return 0
    fi
    sleep 1
  done
  echo "Warnung: $url antwortet noch nicht" >&2
  return 1
}

node_major() {
  node -v 2>/dev/null | sed 's/^v//;s/\..*//'
}

ensure_node() {
  local major
  if command -v node >/dev/null 2>&1 && command -v npm >/dev/null 2>&1; then
    major="$(node_major)"
    if [ -n "$major" ] && [ "$major" -ge 20 ]; then
      echo "Node $(node -v) vorhanden"
      return 0
    fi
    echo "Node $(node -v) ist zu alt (mindestens 20 nötig), installiere Node 22"
  fi
  apt-get install -y ca-certificates curl gnupg
  mkdir -p /etc/apt/keyrings
  curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key \
    | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg
  echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_22.x nodistro main" \
    >/etc/apt/sources.list.d/nodesource.list
  apt-get update
  apt-get install -y nodejs
  major="$(node_major)"
  if ! command -v npm >/dev/null 2>&1 || [ -z "$major" ] || [ "$major" -lt 20 ]; then
    echo "Node.js 20+ konnte nicht installiert werden" >&2
    return 1
  fi
  echo "Node $(node -v) / npm $(npm -v)"
}

ensure_users() {
  if ! id deploy >/dev/null 2>&1; then
    adduser --disabled-password --comment deploy deploy
  fi
  getent group zeiterfassung >/dev/null || addgroup --system zeiterfassung
  if ! id zeiterfassung >/dev/null 2>&1; then
    adduser --system --ingroup zeiterfassung --home "$DATA" --shell /usr/sbin/nologin zeiterfassung
  fi
  usermod -aG zeiterfassung deploy
  mkdir -p /home/deploy/.ssh "$APP_ROOT" "$DATA" "$DATA/backups" "$CONF"
  chmod 700 /home/deploy/.ssh
  if [ -f /root/.ssh/authorized_keys ]; then
    cp /root/.ssh/authorized_keys /home/deploy/.ssh/authorized_keys
    chown -R deploy:deploy /home/deploy/.ssh
    chmod 600 /home/deploy/.ssh/authorized_keys
  fi
  chown -R deploy:zeiterfassung "$APP_ROOT"
  chown -R zeiterfassung:zeiterfassung "$DATA"
  chown root:zeiterfassung "$CONF"
  chmod 750 "$DATA" "$CONF"
}

ensure_sudoers() {
  cat >/etc/sudoers.d/zeiterfassung-deploy <<'SUD'
deploy ALL=(root) NOPASSWD: /bin/systemctl start zeiterfassung, /bin/systemctl stop zeiterfassung, /bin/systemctl restart zeiterfassung, /bin/systemctl reload zeiterfassung, /bin/systemctl status zeiterfassung, /bin/systemctl start nginx, /bin/systemctl stop nginx, /bin/systemctl restart nginx, /bin/systemctl reload nginx, /bin/systemctl status nginx, /usr/bin/journalctl, /usr/bin/certbot, /opt/zeiterfassung/deploy/update.sh, /opt/zeiterfassung/deploy/install.sh
SUD
  chmod 440 /etc/sudoers.d/zeiterfassung-deploy
}

ensure_firewall() {
  ufw default deny incoming
  ufw default allow outgoing
  ufw allow OpenSSH
  ufw allow 80/tcp
  ufw allow 443/tcp
  ufw --force enable
  systemctl enable --now fail2ban || true
}

render_nginx() {
  local domain="$1"
  local src="${2:-$APP_ROOT/deploy/nginx.conf}"
  local dest=/etc/nginx/sites-available/zeiterfassung
  if [ ! -f "$src" ]; then
    echo "nginx-Vorlage fehlt: $src" >&2
    return 1
  fi
  sed "s/__DOMAIN__/${domain}/g" "$src" >"$dest"
  ln -sfn "$dest" /etc/nginx/sites-enabled/zeiterfassung
  rm -f /etc/nginx/sites-enabled/default
}

ensure_datafox_secret() {
  local conf="${1:-$CONF/config.toml}"
  python3 - "$conf" <<'PY'
from pathlib import Path
import re
import secrets
import sys

p = Path(sys.argv[1])
if not p.is_file():
    raise SystemExit(0)
text = p.read_text(encoding="utf-8")
found = re.findall(r'(?m)^datafox_secret\s*=\s*"(.*)"\s*$', text)
secret = next((v.strip() for v in found if v.strip()), "")
top = text.split("\n[", 1)[0]
was_top = bool(re.search(r'(?m)^datafox_secret\s*=\s*".+\s*$', top))
text = re.sub(r'(?m)^datafox_secret\s*=\s*".*"\s*\n?', "", text)
if not secret:
    secret = secrets.token_urlsafe(32)
    action = "ergänzt"
elif was_top:
    action = "vorhanden"
else:
    action = "nach oben verschoben"
insert = f'datafox_secret = "{secret}"\n'
head, sep, tail = text.partition("\n[")
head = head.rstrip() + "\n"
if tail:
    text = head + "\n" + insert + "[" + tail
else:
    text = head + "\n" + insert
if not text.endswith("\n"):
    text += "\n"
p.write_text(text, encoding="utf-8")
print(f"datafox_secret {action}")
PY
}

ensure_terminal_http() {
  local script="${APP_ROOT}/deploy/ensure_terminal_http.py"
  if [ ! -f "$script" ]; then
    echo "ensure_terminal_http.py fehlt" >&2
    return 0
  fi
  python3 "$script" || return 0
  nginx -t && systemctl reload nginx
}
