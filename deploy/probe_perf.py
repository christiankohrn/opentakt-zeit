#!/usr/bin/env python3
"""Leistungsmessung der Übersichts-Endpunkte auf echten Daten (nur lesend).

Verwendung auf dem Zielsystem:

1. Konsistente Kopie der Datenbank anlegen (ändert nichts am Original):
     sqlite3 /var/lib/zeiterfassung/app.db ".backup /tmp/perf-check.db"
   Falls der Zugriff aufs Original fehlt, ersatzweise die neueste Datei aus
   /var/lib/zeiterfassung/backups/ nach /tmp kopieren.

2. Messen (liest nur die Kopie, braucht kein Passwort):
     /opt/zeiterfassung/venv/bin/python probe_perf.py /tmp/perf-check.db 2026-09

Misst Wandzeit, SQL-Zeit und Abfragezahl von Personal, Prüfung und
Monatssalden gegen die exakte Code- und Datenlage des Systems. Die
ausgegebenen Salden dienen nur der Plausibilität, nicht der Abrechnung.
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace


def main() -> None:
    if len(sys.argv) != 3:
        print("Aufruf: probe_perf.py <db-kopie> <monat JJJJ-MM>")
        raise SystemExit(2)
    db_path = Path(sys.argv[1])
    month = sys.argv[2]
    if not db_path.is_file():
        print(f"Nicht gefunden: {db_path}")
        raise SystemExit(2)

    backend = Path(os.environ.get("APP_BACKEND", "/opt/zeiterfassung/backend"))
    sys.path.insert(0, str(backend))
    config = Path(tempfile.mkdtemp(prefix="ze-probe-")) / "config.toml"
    config.write_text(
        f"""
environment = "test"
secret_key = "probe-nur-lesend"
timezone = "Europe/Berlin"
org_name = "Probe"
public_url = "http://probe.local"
database_path = "{db_path.as_posix()}"
listen_host = "127.0.0.1"
listen_port = 8000
esp_terminal_secret = "probe"
""",
        encoding="utf-8",
    )
    os.environ["ZEITERFASSUNG_CONFIG"] = str(config)

    from sqlalchemy import event, func, select

    from app.database import SessionLocal, engine, ensure_schema
    from app.models import (
        Absence,
        AccountEntry,
        DayModel,
        MonthClosing,
        Punch,
        User,
        WorkModel,
        WorkModelAssignment,
    )
    from app.routers import hr, reports

    stats = {"count": 0, "time": 0.0}

    @event.listens_for(engine, "before_cursor_execute")
    def _before(conn, cursor, statement, params, context, executemany):
        context._probe_start = time.perf_counter()

    @event.listens_for(engine, "after_cursor_execute")
    def _after(conn, cursor, statement, params, context, executemany):
        stats["count"] += 1
        stats["time"] += time.perf_counter() - context._probe_start

    ensure_schema()
    db = SessionLocal()
    try:
        users = list(db.scalars(select(User).where(User.active)))
        punches = db.scalar(select(func.count(Punch.id))) or 0
        print(f"personen(aktiv)={len(users)} stempel={punches}")
        kinds = dict(
            db.execute(
                select(WorkModel.kind, func.count(User.id))
                .join(User, User.work_model_id == WorkModel.id)
                .where(User.active)
                .group_by(WorkModel.kind)
            ).all()
        )
        no_model = sum(1 for u in users if u.work_model_id is None)
        print(f"stammmodelle={kinds} ohne={no_model}")
        print(
            "verlaeufe={} tagesmodelle={} abschluesse={} davon_eingefroren={} abwesenheiten={} konten={}".format(
                db.scalar(select(func.count(WorkModelAssignment.id))) or 0,
                db.scalar(select(func.count(DayModel.id))) or 0,
                db.scalar(select(func.count(MonthClosing.id))) or 0,
                db.scalar(
                    select(func.count(MonthClosing.id)).where(MonthClosing.rules_json.is_not(None))
                )
                or 0,
                dict(
                    db.execute(select(Absence.kind, func.count(Absence.id)).group_by(Absence.kind)).all()
                ),
                dict(
                    db.execute(
                        select(AccountEntry.kind, func.count(AccountEntry.id)).group_by(AccountEntry.kind)
                    ).all()
                ),
            )
        )
        admin = next(
            (u for u in users if u.role in {"admin", "hr"} and not u.must_change_password),
            None,
        )
        if admin is None:
            print("Kein aktiver Admin/HR ohne Passwortwechsel gefunden.")
            raise SystemExit(1)
        req = SimpleNamespace(
            session={"uid": admin.id, "rev": int(admin.session_rev or 0)},
            url=SimpleNamespace(path="/api/probe"),
        )
        year, mon = (int(x) for x in month.split("-"))
        last = (date(year + 1, 1, 1) if mon == 12 else date(year, mon + 1, 1)) - timedelta(days=1)
        targets = [
            ("personal /api/hr/balances", lambda: hr.balances(req, db, month)),
            ("pruefung /api/hr/plausibility", lambda: hr.plausibility(req, db, month)),
            (
                "salden /api/hr/reports/month-balances",
                lambda: reports.month_balances(req, db, month, min(last, date.today()), None, None),
            ),
        ]
        for name, call in targets:
            call()
            call()
            stats["count"], stats["time"] = 0, 0.0
            started = time.perf_counter()
            call()
            wall = time.perf_counter() - started
            print(f"{name}: wand={wall:.2f}s sql={stats['time']:.2f}s ({stats['count']} abfragen)")
    finally:
        db.close()


if __name__ == "__main__":
    main()
