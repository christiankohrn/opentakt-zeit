# Changelog

Format angelehnt an [Keep a Changelog](https://keepachangelog.com/de/1.1.0/), Versionierung nach [SemVer](https://semver.org/lang/de/).

## [Unreleased]

- Deutlich schnellere Personalübersicht, Prüfung und Monatssalden: Stempel werden pro Zeitraum nur einmal sortiert, Urlaub/Krankheit direkt gezählt statt über Jahressummen, und die Personalübersicht lädt alle Personen mit gebündelten Abfragen (Messung bei 40 Personen: Monatssalden von 26 s auf 0,5 s, Personal von 0,8 s auf 0,4 s bei 59 statt 624 Abfragen, Monatsabschluss von 37 s auf 10 s). Die berechneten Werte sind unverändert.
- Die Überstundenkappung bucht nur noch die Korrektur auf die Grenze. Ein automatischer Vortrag in den Folgemonat entfällt; zurückholen geht über eine manuelle Buchung.
- Zeitausgleich und Schule lassen sich wie Urlaub und Krankheit eintragen. Zeitausgleich zieht die Sollzeit vom Zeitkonto ab, auch an einem zukünftigen Tag, und der Tag bleibt ohne Fehlerfarbe.
- Monatsjournale lassen sich aus den Journalen per E-Mail schicken, wenn die Person eine Adresse und den Haken „Monatsjournal per E-Mail“ hat. Der PDF-Knopf fragt, ob alle Journale oder nur die ohne E-Mail-Adresse geladen werden.
- Pausenschwellen lassen sich auf die Minute setzen, zum Beispiel 45 Minuten ab 9:45. Ein Arbeitszeitmodell kann stattdessen feste Pausenzeiten neben der Arbeitszeit verwenden, bei Schichten je Schicht. Ohne Schichtbeginn wählt die Pause, die in die Anwesenheit fällt, die Schicht, ohne Kommen und Gehen zu beschneiden. Die Voreinstellung bleibt die automatische Schwelle.
- Pro Person lässt sich das Zeitkonto vom Monatsabschluss ausnehmen. Der Abschluss speichert dann 0, der Folgemonat beginnt bei 0, und es entsteht keine Korrekturbuchung. Die Stunden des Monats bleiben in der Tagesrechnung.
- Neuer Urlaubsplaner für Personal und Admin: Gesamtansicht aller Abwesenheiten als Personen×Tage-Matrix mit Monats- und Jahresansicht, Filter wie in den Auswertungen, Urlaubskennzahlen pro Person und CSV-/PDF-Export.
- Im Urlaubsplaner lässt sich Urlaub per Klick eintragen und entfernen (Bearbeitungsmodus mit Knopf). Die Kontoprüfung läuft live; geht ein Konto ins Minus, warnt der Planner deutlich und bietet beim Speichern den Ausgleich im Urlaubskonto an.
- Automatische Pause ist bei neuen Personen eingeschaltet (30 Minuten ab 6:30 Stunden, 45 Minuten ab 9:45 Stunden).
- Suchfeld in Personal, Arbeitszeitmodellen, Abteilungen, Prüfung, Feiertagen und im Personenfilter der Auswertungen.
- README beschreibt das Update einer laufenden Installation: frischer Klon, Kopie nach `/opt/zeiterfassung`, dann `update.sh`. Config, Datenbank, nginx und Zertifikat bleiben.
- Während Listen und Auswertungen geladen werden, steht „Laden …“ statt einer leeren Ansicht.
- Administratoren können eine Person endgültig löschen. Stempel, Abwesenheiten und das Konto sind danach weg; die Oberfläche verlangt eine ausdrückliche Bestätigung.
- ESP32-Gehäuse Version 2 (parametrisierter Wandleser, OpenSCAD): Maße nach Prototyp V1 leicht korrigiert, ungetestet. Platz für Stiftleisten und Kabel, nicht für den produktiven Einsatz empfohlen.
- Abteilungen als Stammdaten: Zuordnung am Mitarbeitenden, Filter in Personal und Prüfung. In den Auswertungen lassen sich ganze Abteilungen im Personenfilter anhaken.
- Optionales Skript `deploy/install-dfcom.sh`: Datafox-DFCom-SDK von datafox.de laden und `libDFCom.so` lokal bauen. Die Bibliothek wird nicht mitgeliefert; HTTP-Stempeln bleibt der Standardweg.
- Optionales DFCom-Polling: der Server holt Buchungen per TCP vom MasterIV (Tabelle `Stempelung`: Kennzeichen 0 = Kommen, 1 = Gehen). Testbetrieb bestätigt Datensätze nicht. Im Normalbetrieb wird die Liste PERSONAL geschrieben (Name, Zeitkonto, genommene Urlaubstage), nur wenn sich der Inhalt geändert hat.
- Eigenes ESP32-Terminal (SH1106, Joy-IT RC522 oder Grove NFC PN532): JSON-API `POST /api/terminals/esp/punch`, Displaytexte in den Einstellungen, Firmware unter `firmware/esp32-terminal/`. Bucht nur online. PN532 per Seeed-HSU (Arduino-Branch, Pins im Konstruktor).

## [0.1.0] - 2026-09-06

Erste öffentliche Version von **Opentakt Zeit**.

- Stempeln in der PWA (Kommen, Pause, Gehen), inkl. Offline-Warteschlange
- Personal, Arbeitsmodelle, Feiertage, Plausibilität, Korrekturen
- Einladungen und Passwort-Reset per E-Mail, SMTP in den Admin-Einstellungen
- Rollen: Personal verwaltet Stammdaten und Zeiten; nur Administratoren ändern Rollen, Konten, Passwörter und Systemeinstellungen
- Datafox MasterIV über HTTP, optional LDAP
- Debian-Deploy (systemd, nginx, SQLite-Backups)
- AGPL-3.0-or-later
