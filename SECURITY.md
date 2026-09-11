# Sicherheit

Opentakt Zeit speichert Anwesenheits- und Personaldaten. Bitte behandelt Funde entsprechend.

## Melden

**Keine öffentlichen Issues** für Sicherheitslücken.

1. GitHub: [privates Security Advisory](https://github.com/christiankohrn/opentakt-zeit/security/advisories/new)
2. Oder direkt an den Maintainer [@christiankohrn](https://github.com/christiankohrn)

Bitte mitliefern, soweit möglich:

- betroffene Version / Commit
- Schritte zur Reproduktion
- Auswirkung (z. B. fremde Stempel lesen, Session übernehmen)

Wir bestätigen den Eingang in der Regel innerhalb weniger Tage und koordinieren eine Behebung, bevor Details öffentlich werden.

## Was wir besonders ernst nehmen

- Authentifizierung und Sitzungen (Cookie, `secret_key`)
- Rechte zwischen Mitarbeiter, Vorgesetzt, Personal, Admin
- Terminal-API (`datafox_secret` in der URL, `esp_terminal_secret` im Header)
- Pfade und Uploads, SQL, XSS in der PWA
- Leak von `config.toml`, Datenbank oder Seed-Passwörtern
- Mitgelieferte Secrets; die optionale Datafox-Bibliothek DFCom nicht ins Git legen

## Betrieb

- `secret_key`, SMTP/LDAP-Passwörter, `datafox_secret` nur in `/etc/zeiterfassung/config.toml` (Rechte 640), nie ins Git
- `esp_terminal_secret` in der Config **oder** in den Admin-Einstellungen (Org-Datenbank); nicht ins Git
- Seed-Datei `/etc/zeiterfassung/seed-once.txt` nach dem ersten Login löschen oder offline aufbewahren
- HTTPS in Produktion; Terminal-HTTP nur so lange, wie die Firmware kein TLS kann — siehe [docs/datafox-masteriv.md](docs/datafox-masteriv.md)
- Backups unter `/var/lib/zeiterfassung/backups/` sind ebenso schützenswert wie `app.db`
