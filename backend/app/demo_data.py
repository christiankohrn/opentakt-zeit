from __future__ import annotations

"""Demo-Buchungen für Max Mustermann. Idempotent, Quelle = demo."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select

from app.auth import normalize_username, now_utc
from app.config import get_config
from app.database import SessionLocal
from app.models import Absence, Punch, User, WorkModel
from app.security import hash_password

TZ = ZoneInfo("Europe/Berlin")
UTC = ZoneInfo("UTC")


def _at(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=TZ).astimezone(UTC)


def _punch(user_id: int, day: date, kind: str, hour: int, minute: int = 0, *, seq: int = 1, voided: bool = False, note: str | None = None) -> Punch:
    p = Punch(
        user_id=user_id,
        kind=kind,
        server_time=_at(day, hour, minute),
        source="demo",
        client_event_id=f"demo-{day.isoformat()}-{kind}-{seq}",
        note=note,
    )
    if voided:
        p.voided_at = now_utc()
        p.void_reason = "Demo: falsch gestempelt"
    return p


def run() -> None:
    get_config()
    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.username == normalize_username("mitarbeiter")))
        admin = db.scalar(select(User).where(User.username == normalize_username("admin")))
        if not user or not admin:
            raise SystemExit("Seed-User mitarbeiter/admin fehlen")

        db.execute(delete(Punch).where(Punch.user_id == user.id))
        db.execute(delete(Absence).where(Absence.user_id == user.id))
        db.flush()

        punches: list[Punch] = []
        absences: list[Absence] = []

        def day_off(d: date, kind: str, note: str) -> None:
            absences.append(
                Absence(user_id=user.id, day=d, kind=kind, note=note, created_by_id=admin.id)
            )

        def add(day: date, *events: tuple) -> None:
            for i, ev in enumerate(events, start=1):
                extra: dict = {}
                parts = list(ev)
                if parts and isinstance(parts[-1], dict):
                    extra = parts.pop()
                kind, hour, minute = parts[0], parts[1], parts[2] if len(parts) > 2 else 0
                punches.append(
                    _punch(
                        user.id,
                        day,
                        kind,
                        hour,
                        minute,
                        seq=i,
                        voided=bool(extra.get("voided")),
                        note=extra.get("note"),
                    )
                )

        # August 2026 — voller Katalog praxisnaher Fälle
        add(date(2026, 8, 3), ("in", 8, 0), ("break_start", 12, 0), ("break_end", 12, 30), ("out", 16, 30))
        add(date(2026, 8, 4), ("in", 8, 5))  # Gehen vergessen
        day_off(date(2026, 8, 5), "vacation", "Demo: Urlaub")
        day_off(date(2026, 8, 6), "vacation", "Demo: Urlaub")
        day_off(date(2026, 8, 7), "vacation", "Demo: Urlaub")
        day_off(date(2026, 8, 10), "sick", "Demo: AU Grippe")
        add(date(2026, 8, 11), ("in", 8, 0), ("break_start", 12, 0), ("break_end", 12, 15), ("out", 17, 0))  # Pause 15 Min
        add(date(2026, 8, 12), ("in", 7, 0), ("break_start", 12, 0), ("break_end", 12, 30), ("out", 17, 0))  # >9h, Pause nur 30
        add(date(2026, 8, 13), ("in", 7, 0), ("break_start", 12, 0), ("break_end", 12, 45), ("out", 17, 0))  # 9h+ mit 45 Min
        add(date(2026, 8, 14), ("in", 7, 0), ("break_start", 12, 0), ("break_end", 12, 45), ("out", 18, 30))  # >10 Stunden
        # 17.8. Montag: Fehlzeit, keine Buchung
        add(date(2026, 8, 18), ("in", 8, 0), ("out", 11, 30), ("in", 13, 30), ("out", 17, 30))  # Arzttermin dazwischen
        add(date(2026, 8, 19), ("in", 8, 0), ("out", 16, 30))  # keine Pause
        add(date(2026, 8, 20), ("in", 8, 0), ("break_start", 12, 0), ("break_end", 14, 0), ("out", 17, 0))  # 2h Pause
        day_off(date(2026, 8, 21), "holiday", "Demo: Brückentag")
        add(date(2026, 8, 24), ("in", 10, 0), ("break_start", 13, 0), ("break_end", 13, 30), ("out", 18, 30))  # später Beginn
        add(date(2026, 8, 25), ("in", 8, 0), ("out", 12, 0))  # halber Tag, gegangen
        add(
            date(2026, 8, 26),
            ("in", 7, 58, {"voided": True, "note": "Demo: zu früh, storniert"}),
            ("in", 8, 12),
            ("break_start", 12, 5),
            ("break_end", 12, 35),
            ("out", 16, 40),
        )
        add(date(2026, 8, 27), ("in", 8, 0), ("break_start", 12, 0), ("out", 12, 20))  # aus Pause nach Hause
        add(date(2026, 8, 28), ("in", 8, 0), ("break_start", 12, 0), ("out", 16, 30))  # Pause nicht beendet, dann Gehen
        add(date(2026, 8, 31), ("in", 7, 45), ("break_start", 11, 45), ("break_end", 12, 15), ("out", 16, 15))

        add(date(2026, 9, 1), ("in", 8, 0), ("break_start", 12, 0), ("break_end", 12, 30), ("out", 16, 30))
        # 2.9. Fehlzeit
        add(date(2026, 9, 3), ("in", 8, 10), ("break_start", 12, 2), ("break_end", 12, 32), ("out", 17, 5))

        db.add_all(punches)
        db.add_all(absences)
        db.commit()
        print(f"Demo: {len(punches)} Stempel, {len(absences)} Abwesenheiten für {user.display_name}")
        _seed_erika(db, admin)
    finally:
        db.close()


def _seed_erika(db, admin: User) -> None:
    cfg = get_config()
    shift = db.scalar(select(WorkModel).where(WorkModel.kind == "shift"))
    if not shift:
        shift = WorkModel(
            name="Wechselschicht 3×8",
            kind="shift",
            hours_mon=8,
            hours_tue=8,
            hours_wed=8,
            hours_thu=8,
            hours_fri=8,
            hours_sat=0,
            hours_sun=0,
        )
        db.add(shift)
        db.flush()
    username = normalize_username(cfg.seed.shift_username)
    erika = db.scalar(select(User).where(User.username == username))
    if not erika:
        erika = User(
            username=username,
            display_name="Erika Schicht",
            email="erika@localhost",
            password_hash=hash_password(cfg.seed.shift_password),
            role="employee",
            work_model_id=shift.id,
            auth_source="local",
        )
        db.add(erika)
        db.flush()
        print(f"Benutzer {username} / {cfg.seed.shift_password} angelegt")
    else:
        erika.work_model_id = shift.id
        erika.display_name = "Erika Schicht"

    db.execute(delete(Punch).where(Punch.user_id == erika.id))
    db.execute(delete(Absence).where(Absence.user_id == erika.id))
    db.flush()

    punches: list[Punch] = []
    absences: list[Absence] = []

    def add(uid: int, day: date, *events: tuple) -> None:
        for i, ev in enumerate(events, start=1):
            extra: dict = {}
            parts = list(ev)
            if parts and isinstance(parts[-1], dict):
                extra = parts.pop()
            kind, hour, minute = parts[0], parts[1], parts[2] if len(parts) > 2 else 0
            punches.append(
                _punch(uid, day, kind, hour, minute, seq=i, voided=bool(extra.get("voided")), note=extra.get("note"))
            )

    # Frühschicht
    add(erika.id, date(2026, 8, 3), ("in", 6, 0), ("break_start", 9, 30), ("break_end", 10, 0), ("out", 14, 0))
    add(erika.id, date(2026, 8, 4), ("in", 6, 0), ("break_start", 9, 30), ("break_end", 10, 0), ("out", 14, 0))
    add(erika.id, date(2026, 8, 5), ("in", 6, 5), ("break_start", 9, 40), ("break_end", 9, 55), ("out", 14, 10))  # Pause kurz
    # Spätschicht
    add(erika.id, date(2026, 8, 6), ("in", 14, 0), ("break_start", 18, 0), ("break_end", 18, 30), ("out", 22, 0))
    # Nachtschicht über Mitternacht
    add(erika.id, date(2026, 8, 7), ("in", 22, 0))
    add(erika.id, date(2026, 8, 8), ("out", 6, 0))
    add(erika.id, date(2026, 8, 10), ("in", 14, 0), ("break_start", 18, 0), ("break_end", 18, 30), ("out", 22, 0))
    add(erika.id, date(2026, 8, 11), ("in", 14, 0), ("break_start", 18, 0), ("break_end", 18, 30), ("out", 22, 15))
    add(erika.id, date(2026, 8, 12), ("in", 22, 0))
    add(erika.id, date(2026, 8, 13), ("out", 6, 0), ("in", 22, 0))
    add(erika.id, date(2026, 8, 14), ("out", 6, 5))
    # 17.8. Fehlzeit
    add(erika.id, date(2026, 8, 18), ("in", 6, 0), ("out", 14, 0))  # Früh ohne Pause
    absences.append(Absence(user_id=erika.id, day=date(2026, 8, 19), kind="vacation", note="Demo: Urlaub Schicht", created_by_id=admin.id))
    absences.append(Absence(user_id=erika.id, day=date(2026, 8, 20), kind="vacation", note="Demo: Urlaub Schicht", created_by_id=admin.id))
    absences.append(Absence(user_id=erika.id, day=date(2026, 8, 21), kind="vacation", note="Demo: Urlaub Schicht", created_by_id=admin.id))
    add(erika.id, date(2026, 8, 24), ("in", 14, 0))  # Spät, Gehen vergessen
    add(erika.id, date(2026, 8, 25), ("in", 6, 0), ("break_start", 9, 30), ("break_end", 10, 0), ("out", 14, 0))
    add(erika.id, date(2026, 8, 26), ("in", 6, 0), ("break_start", 9, 30), ("break_end", 11, 30), ("out", 14, 0))  # lange Pause
    add(erika.id, date(2026, 8, 27), ("in", 22, 0))
    add(erika.id, date(2026, 8, 28), ("out", 6, 0))
    add(erika.id, date(2026, 8, 31), ("in", 14, 0), ("break_start", 18, 0), ("break_end", 18, 30), ("out", 22, 0))
    add(erika.id, date(2026, 9, 1), ("in", 6, 0), ("break_start", 9, 30), ("break_end", 10, 0), ("out", 14, 0))

    db.add_all(punches)
    db.add_all(absences)
    db.commit()
    print(f"Demo Schicht: {len(punches)} Stempel, {len(absences)} Abwesenheiten für {erika.display_name}")


if __name__ == "__main__":
    run()
