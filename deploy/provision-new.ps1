# Provision a blank Debian host from Windows. Needs root SSH.
# Example:
#   powershell -File deploy/provision-new.ps1 -SshTarget root@192.0.2.10 -Domain zeit.firma.de -Email it@firma.de
#
param(
    [Parameter(Mandatory = $true)]
    [string]$SshTarget,
    [Parameter(Mandatory = $true)]
    [string]$Domain,
    [Parameter(Mandatory = $false)]
    [string]$Email = "",
    [string]$OrgName = "Opentakt Zeit",
    [string]$Environment = "production",
    [switch]$SkipCertbot
)

$ErrorActionPreference = "Stop"
if ($Domain -match "['`"\\s]" -or $OrgName -match "['`"]" -or $Email -match "['`"]") {
    throw "Domain, OrgName und Email dürfen keine Anführungszeichen enthalten."
}
if (-not $SkipCertbot -and -not $Email) {
    throw "Email ist Pflicht (Let's Encrypt) oder -SkipCertbot setzen."
}

$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$tgz = Join-Path $env:TEMP "zeiterfassung-provision.tgz"
$sshOpts = @("-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new")
$skip = if ($SkipCertbot) { "1" } else { "0" }

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
Write-Host "Lade nach $SshTarget"
& scp @sshOpts $tgz "${SshTarget}:/tmp/ze-provision.tgz"

$remote = @"
set -euo pipefail
mkdir -p /tmp/ze-src
tar -xzf /tmp/ze-provision.tgz -C /tmp/ze-src
rm -f /tmp/ze-provision.tgz
export DOMAIN='$Domain'
export EMAIL='$Email'
export ORG_NAME='$OrgName'
export ENVIRONMENT='$Environment'
export SKIP_CERTBOT='$skip'
export REPO=/tmp/ze-src
bash /tmp/ze-src/deploy/new-host.sh
"@
$remote = $remote -replace "`r`n", "`n" -replace "`r", ""

Write-Host "Installiere auf $SshTarget ($Domain)"
& ssh @sshOpts $SshTarget $remote
Write-Host "Provision fertig. Logins: ssh $SshTarget sudo cat /etc/zeiterfassung/seed-once.txt"
