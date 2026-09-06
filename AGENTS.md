# Agent notes — Opentakt Zeit

Öffentliche Doku: `README.md`, `DEPLOY.md`, `CONTRIBUTING.md`.

## Stack

Python FastAPI + SQLite (WAL) + React/Vite-PWA. systemd + nginx. Jobs via systemd-timer.

## Lokal

Siehe README (Schnellstart). Health: `GET /api/health`. Kein interaktives pdb.

## Debian-Pfade (nach `deploy/new-host.sh`)

Die Dienstnamen heißen intern weiter `zeiterfassung`:

- App: `/opt/zeiterfassung`
- Config: `/etc/zeiterfassung/config.toml`
- Daten: `/var/lib/zeiterfassung/app.db`
- Backups: `/var/lib/zeiterfassung/backups/`
- Dienstbenutzer: `zeiterfassung`, SSH-User nach Bootstrap: `deploy`
- Sudo nur für systemctl, journalctl, certbot und `deploy/update.sh`

Seed-Logins liegen einmalig in `/etc/zeiterfassung/seed-once.txt` (nicht ins Git).
