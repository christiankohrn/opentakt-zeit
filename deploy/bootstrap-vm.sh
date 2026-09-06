#!/bin/bash
set -euo pipefail
# OS users, sudo, firewall. Prefer deploy/new-host.sh on a blank machine.
export DEBIAN_FRONTEND=noninteractive
apt-get install -y rsync ufw fail2ban
# shellcheck source=deploy/common.sh
source "$(cd "$(dirname "$0")" && pwd)/common.sh"
ensure_users
ensure_sudoers
ensure_firewall
id deploy
id zeiterfassung
command -v node >/dev/null && node --version || true
nginx -v 2>/dev/null || true
echo BOOTSTRAP_OK
