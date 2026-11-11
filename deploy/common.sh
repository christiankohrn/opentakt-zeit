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

ensure_esp_terminal_secret() {
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
found = re.findall(r'(?m)^esp_terminal_secret\s*=\s*"(.*)"\s*$', text)
secret = next((v.strip() for v in found if v.strip()), "")
top = text.split("\n[", 1)[0]
was_top = bool(re.search(r'(?m)^esp_terminal_secret\s*=\s*".+\s*$', top))
text = re.sub(r'(?m)^esp_terminal_secret\s*=\s*".*"\s*\n?', "", text)
if not secret:
    secret = secrets.token_urlsafe(32)
    action = "ergänzt"
elif was_top:
    action = "vorhanden"
else:
    action = "nach oben verschoben"
insert = f'esp_terminal_secret = "{secret}"\n'
head, sep, tail = text.partition("\n[")
head = head.rstrip() + "\n"
if tail:
    text = head + "\n" + insert + "[" + tail
else:
    text = head + "\n" + insert
if not text.endswith("\n"):
    text += "\n"
p.write_text(text, encoding="utf-8")
print(f"esp_terminal_secret {action}")
PY
}

ensure_terminal_http() {
  local script="${APP_ROOT}/deploy/ensure_terminal_http.py"
  if [ ! -f "$script" ]; then
    echo "ensure_terminal_http.py fehlt" >&2
    return 0
  fi
  python3 "$script" || true
  python3 "$APP_ROOT/deploy/ensure_proxy_timeout.py" || true
  nginx -t && systemctl reload nginx
}

install_update_units() {
  install -m 644 "$APP_ROOT/deploy/zeiterfassung-update.service" /etc/systemd/system/zeiterfassung-update.service
  install -m 644 "$APP_ROOT/deploy/zeiterfassung-update.path" /etc/systemd/system/zeiterfassung-update.path
  systemctl daemon-reload
  systemctl enable --now zeiterfassung-update.path
}

# Git-Stand eines Verzeichnisses als JSON nach stdout (leer bei Fehler).
git_meta_json() {
  python3 - "$1" <<'PY'
import json
import subprocess
import sys

d = sys.argv[1]

def run(*args):
    try:
        return subprocess.run(
            ["git", "-C", d, *args], capture_output=True, text=True, timeout=10, check=True
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""

print(json.dumps({
    "commit": run("rev-parse", "HEAD"),
    "commit_date": run("log", "-1", "--format=%cI"),
    "message": run("log", "-1", "--format=%s")[:160],
}))
PY
}

# Schreibt $DATA/version.json aus dem Git-Stand eines Verzeichnisses (leise ohne .git).
write_version_from_dir() {
  eval "$(git_meta_json "$1" | python3 -c '
import json
import shlex
import sys

try:
    d = json.load(sys.stdin)
except ValueError:
    d = {}
print("META_COMMIT=" + shlex.quote(str(d.get("commit") or "")))
print("META_DATE=" + shlex.quote(str(d.get("commit_date") or "")))
print("META_MSG=" + shlex.quote(str(d.get("message") or "")))
')"
  if [ -n "${META_COMMIT:-}" ]; then
    write_version_json "$META_COMMIT" "$META_DATE" "$META_MSG"
  fi
}

# Schreibt $DATA/version.json. Argumente: commit datum nachricht.
write_version_json() {
  V_COMMIT="$1" V_DATE="$2" V_MSG="$3" python3 <<'PY'
import json
import os
from datetime import datetime, timezone
from pathlib import Path

data = Path(os.environ.get("DATA", "/var/lib/zeiterfassung"))
p = data / "version.json"
doc = {
    "commit": os.environ.get("V_COMMIT") or None,
    "commit_date": os.environ.get("V_DATE") or None,
    "message": (os.environ.get("V_MSG") or "")[:160],
    "installed_at": datetime.now(timezone.utc).isoformat(),
    "source": "github",
    "branch": "main",
}
tmp = p.with_suffix(".tmp")
tmp.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
tmp.replace(p)
PY
  chown zeiterfassung:zeiterfassung "$DATA/version.json" || true
}

# Pflegt den Update-Teil von $DATA/update-status.json. Argumente: zustand [fehler] [commit].
update_state() {
  STATE="$1" STATE_ERROR="${2:-}" STATE_TO="${3:-}" python3 <<'PY'
import json
import os
from datetime import datetime, timezone
from pathlib import Path

data = Path(os.environ.get("DATA", "/var/lib/zeiterfassung"))
p = data / "update-status.json"
try:
    cur = json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}
except ValueError:
    cur = {}
if not isinstance(cur, dict):
    cur = {}
upd = cur.get("update") if isinstance(cur.get("update"), dict) else {}
upd["state"] = os.environ["STATE"]
if os.environ.get("STATE_TO"):
    upd["to_commit"] = os.environ["STATE_TO"][:7]
if os.environ.get("STATE_ERROR"):
    upd["error"] = os.environ["STATE_ERROR"][:500]
if os.environ["STATE"] in {"done", "failed"}:
    upd["finished_at"] = datetime.now(timezone.utc).isoformat()
cur["update"] = upd
tmp = p.with_suffix(".tmp")
tmp.write_text(json.dumps(cur, ensure_ascii=False), encoding="utf-8")
tmp.replace(p)
PY
  chown zeiterfassung:zeiterfassung "$DATA/update-status.json" || true
}
