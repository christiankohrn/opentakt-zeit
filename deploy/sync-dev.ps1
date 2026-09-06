# Sync working tree to a Debian VM without a git commit.
# Usage:
#   powershell -File deploy/sync-dev.ps1 -HostName zeit-dev -Domain zeit.firma.de
# oder Umgebungsvariablen OPENTAKT_DEV_HOST / OPENTAKT_DEV_DOMAIN.

param(
    [string]$HostName = $env:OPENTAKT_DEV_HOST,
    [string]$Domain = $env:OPENTAKT_DEV_DOMAIN,
    [string]$OrgName = $(if ($env:OPENTAKT_DEV_ORG) { $env:OPENTAKT_DEV_ORG } else { "Opentakt Zeit" })
)

$ErrorActionPreference = "Stop"
if (-not $HostName) {
    throw "HostName fehlt. Beispiel: -HostName zeit-dev  oder  OPENTAKT_DEV_HOST setzen."
}

$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$tgz = Join-Path $env:TEMP "opentakt-zeit-sync.tgz"

Write-Host "Packe $root"
$excludes = @(
    "--exclude=.git",
    "--exclude=node_modules",
    "--exclude=frontend/node_modules",
    "--exclude=frontend/dist",
    "--exclude=.venv",
    "--exclude=backend/.venv",
    "--exclude=data",
    "--exclude=__pycache__",
    "--exclude=*.pyc"
)
if (Test-Path $tgz) { Remove-Item $tgz }
& tar -C $root -czf $tgz @excludes .
Write-Host "Lade nach $HostName"
scp -o BatchMode=yes $tgz "${HostName}:/tmp/ze-sync.tgz"

$org = ($OrgName -replace '"', '')
$exportDomain = ""
if ($Domain) {
    $exportDomain = "export DOMAIN=$Domain ORG_NAME=`"$org`""
}

$remote = @"
set -euo pipefail
$exportDomain
mkdir -p /tmp/ze-src
tar -xzf /tmp/ze-sync.tgz -C /tmp/ze-src
rm -f /tmp/ze-sync.tgz
export REPO=/tmp/ze-src
chmod a+x /tmp/ze-src/deploy/*.sh
if [ -d /opt/zeiterfassung/backend ]; then
  rsync -a --delete --exclude venv --exclude frontend/node_modules --exclude frontend/dist \
    /tmp/ze-src/ /opt/zeiterfassung/
  chmod a+x /opt/zeiterfassung/deploy/*.sh
  sudo /opt/zeiterfassung/deploy/update.sh
else
  if [ -z "`${DOMAIN:-}" ]; then
    echo "Erstinstallation braucht -Domain bzw. OPENTAKT_DEV_DOMAIN" >&2
    exit 1
  fi
  bash /tmp/ze-src/deploy/install.sh
fi
for i in `$(seq 1 40); do
  curl -fsS http://127.0.0.1:8000/api/health && break
  sleep 1
done
if [ -n "`${DOMAIN:-}" ]; then
  curl -fsS "https://`${DOMAIN}/api/health" || true
fi
"@
$remote = $remote -replace "`r`n", "`n" -replace "`r", ""

ssh -o BatchMode=yes $HostName $remote
Write-Host "Sync fertig"
