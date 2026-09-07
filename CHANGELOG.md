# Changelog

Format angelehnt an [Keep a Changelog](https://keepachangelog.com/de/1.1.0/), Versionierung nach [SemVer](https://semver.org/lang/de/).

## [Unreleased]

- Optionales Skript `deploy/install-dfcom.sh`: Datafox-DFCom-SDK von datafox.de laden und `libDFCom.so` lokal bauen. Die Bibliothek wird nicht mitgeliefert; HTTP-Stempeln bleibt der Standardweg.

## [0.1.0] - 2026-09-06

Erste öffentliche Version von **Opentakt Zeit**.

- Stempeln in der PWA (Kommen, Pause, Gehen), inkl. Offline-Warteschlange
- Personal, Arbeitsmodelle, Feiertage, Plausibilität, Korrekturen
- Einladungen und Passwort-Reset per E-Mail, SMTP in den Admin-Einstellungen
- Rollen: Personal verwaltet Stammdaten und Zeiten; nur Administratoren ändern Rollen, Konten, Passwörter und Systemeinstellungen
- Datafox MasterIV über HTTP, optional LDAP
- Debian-Deploy (systemd, nginx, SQLite-Backups)
- AGPL-3.0-or-later
