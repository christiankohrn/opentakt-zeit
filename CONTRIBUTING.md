# Mitwirken

Danke, dass du Opentakt Zeit verbessern willst. Kleine, nachvollziehbare Änderungen sind leichter zu prüfen als große Sammel-PRs.

## Ablauf

1. Issue öffnen oder an einem bestehenden Issue arbeiten.
2. Fork bzw. Branch vom aktuellen Hauptbranch.
3. Lokal entwickeln und die Tests laufen lassen.
4. Pull Request mit kurzer Beschreibung: **Warum**, nicht nur **Was**.

Bitte keine Secrets, Produktions-Configs, Datenbanken oder `seed-once.txt` committen.

## Lokale Umgebung

Siehe [README.md](README.md#schnellstart-entwicklung). Kurz:

- Backend: Python 3.12+, `pip install -r backend/requirements.txt`
- Frontend: Node 20+, `npm install` in `frontend/`
- Config: `cp config.toml.example config.toml` und Seed-Passwörter setzen
- API: `uvicorn` auf Port 8000, UI: Vite auf 5173 (`/api` wird proxied)

## Tests

```bash
cd backend && PYTHONPATH=. python -m pytest
cd frontend && npx tsc --noEmit
```

Neue Logik (Zeitrechnung, Feiertage, Terminal-Parsing, Backups) bitte mit einem Pytest abdecken, im Stil der Dateien unter `backend/tests/`.

## Stil

- Backend: Python 3.12, Typen wo sie helfen, deutsche Nutzertexte in API-Fehlern.
- Frontend: TypeScript `strict`, bestehende Komponenten und Tailwind-Klassen wiederverwenden.
- UI auf Handy und Desktop denken (PWA, Safe-Area, große Touch-Ziele).
- Keine Formatter-only-Diffs in fachlichen PRs.

## Pull Requests

- Ein Thema pro PR.
- Breaking Changes (Config, Datenbankschema, Terminal-Protokoll) deutlich benennen.
- Screenshots oder kurzes Terminal-Log helfen bei UI- und Deploy-Änderungen.

Mit dem Beitrag akzeptierst du, dass er unter der [AGPL-3.0-or-later](LICENSE) des Projekts steht.
