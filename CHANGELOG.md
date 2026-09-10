# Changelog

Format angelehnt an [Keep a Changelog](https://keepachangelog.com/de/1.1.0/), Versionierung nach [SemVer](https://semver.org/lang/de/).

## [Unreleased]

- Optionales Skript `deploy/install-dfcom.sh`: Datafox-DFCom-SDK von datafox.de laden und `libDFCom.so` lokal bauen. Die Bibliothek wird nicht mitgeliefert; HTTP-Stempeln bleibt der Standardweg.
- Optionales DFCom-Polling: der Server holt Buchungen per TCP vom MasterIV (Tabelle `Stempelung`: Kennzeichen 0 = Kommen, 1 = Gehen). Testbetrieb bestätigt Datensätze nicht. Im Normalbetrieb wird die Liste PERSONAL geschrieben (Name, Zeitkonto, genommene Urlaubstage), nur wenn sich der Inhalt geändert hat.
- Eigenes ESP32-Terminal (SH1106): JSON-API `POST /api/terminals/esp/punch`, Displaytexte in den Einstellungen, Firmware unter `firmware/esp32-terminal/`. V1 bucht nur online.

## [0.1.0] - 2026-09-06

Erste öffentliche Version von **Opentakt Zeit**.

- Stempeln in der PWA (Kommen, Pause, Gehen), inkl. Offline-Warteschlange
- Personal, Arbeitsmodelle, Feiertage, Plausibilität, Korrekturen
- Einladungen und Passwort-Reset per E-Mail, SMTP in den Admin-Einstellungen
- Rollen: Personal verwaltet Stammdaten und Zeiten; nur Administratoren ändern Rollen, Konten, Passwörter und Systemeinstellungen
- Datafox MasterIV über HTTP, optional LDAP
- Debian-Deploy (systemd, nginx, SQLite-Backups)
- AGPL-3.0-or-later
