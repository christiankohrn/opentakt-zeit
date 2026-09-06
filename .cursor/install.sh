#!/usr/bin/env bash
# Idempotent Cloud Agent bootstrap for the Opentakt Zeit dev environment.
# Prepares a Python venv for the FastAPI backend, installs the React/Vite
# frontend dependencies, and writes a local dev config.toml (gitignored) with
# known seed logins so the app is usable end to end without secrets.
set -euo pipefail

cd "$(dirname "$0")/.."

# System packages the default image lacks: venv bootstrap + a C toolchain for
# any wheels that need building. Guarded so reruns are cheap.
if ! dpkg -s python3.12-venv >/dev/null 2>&1; then
  sudo apt-get update -qq
  sudo apt-get install -y -qq python3.12-venv python3-dev build-essential
fi

# Backend: virtualenv + pinned Python deps.
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
fi
.venv/bin/pip install --upgrade pip -q
.venv/bin/pip install -r backend/requirements.txt

# Frontend: node deps (uses package-lock when present).
(cd frontend && npm install --no-audit --no-fund)

# Local dev config (gitignored). Only created if absent so it can be edited.
if [ ! -f config.toml ]; then
  cat > config.toml <<'EOF'
environment = "development"
secret_key = "dev-only-change-me"
timezone = "Europe/Berlin"
org_name = "Opentakt Zeit (Dev)"
public_url = "http://127.0.0.1:5173"
bundesland = "NW"
database_path = "data/app.db"
listen_host = "127.0.0.1"
listen_port = 8000
datafox_secret = ""

[seed]
admin_username = "admin"
admin_password = "change-me"
hr_username = "personal"
hr_password = "change-me"
employee_username = "mitarbeiter"
employee_password = "change-me"
shift_username = "erika"
shift_password = "change-me"

[smtp]
enabled = false

[ldap]
enabled = false
EOF
fi

echo "Opentakt Zeit install complete."
