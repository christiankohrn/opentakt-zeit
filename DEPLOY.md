# Deployment — Opentakt Zeit

On-Prem: Python FastAPI + SQLite + React-PWA hinter nginx, systemd und Let’s Encrypt.
Zielsystem: **Debian 12 oder 13**, eine öffentliche IPv4 (besser auch IPv6), SSH-Zugang als **root** für die Erstinstallation.

## Voraussetzungen

1. DNS **A** (und optional **AAAA**) für die Wunschdomain zeigt auf die Maschine.
2. Ports **22 / 80 / 443** erreichbar.
3. Eine E-Mail-Adresse für Let’s Encrypt.
4. Der App-Tree (Git-Clone oder Kopie).

Ohne gültiges DNS schlägt das Zertifikat fehl; die App läuft dann erstmal nur auf Port 80.

## Neue Maschine (empfohlen)

Auf der Debian-Box als root, Tree liegt z. B. unter `/tmp/opentakt-zeit`:

```bash
export DOMAIN=zeit.firma.de
export EMAIL=it@firma.de
export ORG_NAME="Muster GmbH"          # optional
# export SKIP_CERTBOT=1                # optional, ohne HTTPS
# export GIT_URL=https://github.com/christiankohrn/opentakt-zeit.git   # nur wenn der Tree fehlt
bash /tmp/opentakt-zeit/deploy/new-host.sh
```

Aus Git auf der Maschine:

```bash
apt-get update && apt-get install -y git
git clone --depth 1 https://github.com/christiankohrn/opentakt-zeit.git /tmp/opentakt-zeit
export DOMAIN=zeit.firma.de EMAIL=it@firma.de
bash /tmp/opentakt-zeit/deploy/new-host.sh
```

`new-host.sh` macht in einem Rutsch:

- Pakete (nginx, Python, SQLite, certbot, ufw, fail2ban, Node 20+)
- Benutzer `deploy` (SSH) und `zeiterfassung` (Dienst)
- Firewall und Sudo nur für systemctl / journalctl / certbot / update
- App nach `/opt/zeiterfassung`, Config, systemd, Frontend-Build
- nginx + Let’s Encrypt, Health-Check

Die Linux-Benutzer, systemd-Units und Verzeichnisse heißen intern weiter `zeiterfassung`. Nur der sichtbare Produktname ist Opentakt Zeit.

### Vom Windows-PC

Root-SSH muss funktionieren (`ssh root@…`).

```powershell
powershell -File deploy/provision-new.ps1 `
  -SshTarget root@192.0.2.10 `
  -Domain zeit.firma.de `
  -Email it@firma.de `
  -OrgName "Muster GmbH"
```

Ohne Zertifikat (Labor, noch kein DNS): `-SkipCertbot`.

## Nach der Installation

| Was | Pfad |
| --- | --- |
| App | `/opt/zeiterfassung` |
| Config | `/etc/zeiterfassung/config.toml` |
| Erst-Logins | `/etc/zeiterfassung/seed-once.txt` (nicht ins Git) |
| Datenbank | `/var/lib/zeiterfassung/app.db` |
| Backups | `/var/lib/zeiterfassung/backups/` (täglich 02:15, 30/12/2) |
| Health | `GET https://<domain>/api/health` |

SSH danach als **`deploy`**, nicht dauerhaft als root. Sudo ist auf Dienst-Kommandos begrenzt.

Seed-Passwörter umgehend notieren und die Datei nur lokal belassen. Benutzer in der UI anpassen; SMTP/LDAP in `config.toml` bei Bedarf.

```bash
sudo journalctl -u zeiterfassung -n 200 --no-pager
curl -fsS https://zeit.firma.de/api/health
```

## Bestehende Instanz aktualisieren

Code liegt schon unter `/opt/zeiterfassung`. Als `deploy`:

```bash
# Variante A: Tree ist ein Git-Clone
cd /opt/zeiterfassung && git pull
sudo /opt/zeiterfassung/deploy/update.sh

# Variante B: vom Entwicklungs-PC ohne Commit
powershell -File deploy/sync-dev.ps1 -HostName zeit-dev -Domain zeit.firma.de
```

`update.sh` sichert die SQLite-Datei nach `backups/pre-update/`, spielt pip/npm neu ein und startet den Dienst.

`config.toml` und die Datenbank werden **nicht** überschrieben.

## Was wo läuft

- **zeiterfassung.service** — uvicorn auf `127.0.0.1:8000`
- **nginx** — TLS und Reverse-Proxy
- **zeiterfassung-jobs.timer** — Feierabend-Erinnerung (Mo–Fr 18:15)
- **zeiterfassung-backup.timer** — tägliches SQLite-Backup 02:15

nginx-Vorlage: `deploy/nginx.conf` (`__DOMAIN__` wird beim Install ersetzt). Certbot hängt SSL an dieselbe Site.

## Restore

```bash
sudo systemctl stop zeiterfassung
sudo -u zeiterfassung cp /var/lib/zeiterfassung/backups/daily/YYYY-MM-DD.db /var/lib/zeiterfassung/app.db
sudo systemctl start zeiterfassung
```

## Typische Fehler

| Symptom | Prüfung |
| --- | --- |
| Certbot / HTTPS fehlt | `dig +short A $DOMAIN`, Port 80 von außen, dann `sudo certbot --nginx -d $DOMAIN` |
| 502 Bad Gateway | `sudo systemctl status zeiterfassung`; kurz warten, uvicorn startet nach dem Deploy ein paar Sekunden später |
| Frontend alt | Hard-Reload / PWA-Cache; `sudo /opt/zeiterfassung/deploy/update.sh` baut `frontend/dist` neu |
| Node zu alt | `new-host.sh` holt Node 22 von NodeSource, wenn Debian < 20 liefert |
| Kein Login nach Neuinstall | Nur bei **leerer** Datenbank werden Seed-User angelegt. Logins stehen in `seed-once.txt` |

## Skripte

| Script | Rolle |
| --- | --- |
| `deploy/new-host.sh` | Erstinstallation auf leerem Debian |
| `deploy/provision-new.ps1` | dasselbe, ferngesteuert von Windows |
| `deploy/install.sh` | App installieren/reparieren (wird von new-host und sync-dev genutzt) |
| `deploy/update.sh` | laufende Instanz aktualisieren |
| `deploy/sync-dev.ps1` | Arbeitsbaum auf die bestehende Dev-VM schieben |
| `deploy/smoke.sh` | grober HTTP/Login-Check (`BASE=https://…`) |
