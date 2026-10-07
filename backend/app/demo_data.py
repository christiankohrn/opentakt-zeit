from __future__ import annotations

"""Demo für zwei Konten, etwa sechs Wochen bis heute. Idempotent, Quelle = demo."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select

from app.auth import normalize_username, now_utc
from app.config import get_config
from app.database import SessionLocal, ensure_schema
from app.models import Absence, Department, Punch, User, WorkModel
from app.security import hash_password
from app.seed import seed_if_empty
from app.workmodels import ensure_initial_assignment

TZ = ZoneInfo("Europe/Berlin")
UTC = ZoneInfo("UTC")

# Nur für die Demo auf dem Entwicklungsserver. Das Skript gibt die Logins aus.
DEMO_PASSWORD = "change-me"


def _today() -> date:
    return datetime.now(TZ).date()


def _at(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=TZ).astimezone(UTC)


def _punch(user_id: int, day: date, kind: str, hour: int, minute: int = 0, *, seq: int = 1) -> Punch:
    return Punch(
        user_id=user_id,
        kind=kind,
        server_time=_at(day, hour, minute),
        source="demo",
        client_event_id=f"demo-{user_id}-{day.isoformat()}-{kind}-{seq}",
    )


def _workdays(start: date, end: date) -> list[date]:
    days: list[date] = []
    cursor = start
    while cursor <= end:
        if cursor.weekday() < 5:
            days.append(cursor)
        cursor += timedelta(days=1)
    return days


def _ensure_demo_user(
    db,
    *,
    username: str,
    first_name: str,
    last_name: str,
    email: str,
    work_model_id: int | None,
    department_id: int | None,
    opening_hours: float,
    opening_on: date,
) -> User:
    key = normalize_username(username)
    user = db.scalar(select(User).where(User.username == key))
    if user is None:
        user = User(
            username=key,
            display_name=f"{first_name} {last_name}",
            email=email,
            role="employee",
            auth_source="local",
        )
        db.add(user)
        db.flush()
    user.first_name = first_name
    user.last_name = last_name
    user.display_name = f"{first_name} {last_name}"
    user.email = email
    user.password_hash = hash_password(DEMO_PASSWORD)
    user.must_change_password = False
    user.web_login = True
    user.active = True
    user.auto_break = True
    user.work_model_id = work_model_id
    user.department_id = department_id
    user.hired_on = date(2024, 4, 1)
    user.vacation_days_year = 28
    user.opening_balance_hours = opening_hours
    user.opening_balance_on = opening_on
    db.flush()
    ensure_initial_assignment(db, user, valid_from=date(2024, 4, 1))
    return user


def _add(punches: list[Punch], user_id: int, day: date, events: list[tuple[str, int, int]]) -> None:
    for index, (kind, hour, minute) in enumerate(events, start=1):
        punches.append(_punch(user_id, day, kind, hour, minute, seq=index))


def _office(day: date, *, short_break: bool = False, no_break: bool = False, open_shift: bool = False) -> list[tuple[str, int, int]]:
    start = 48 + (day.day % 6)
    events: list[tuple[str, int, int]] = [("in", 7, start)]
    if open_shift:
        return events
    if no_break:
        return events + [("out", 16, 12)]
    pause = 12 if short_break else 30
    end = 22 + (day.day % 8)
    return events + [("break_start", 12, 0), ("break_end", 12, pause), ("out", 16, end)]


def _early(day: date, *, open_shift: bool = False) -> list[tuple[str, int, int]]:
    events: list[tuple[str, int, int]] = [("in", 6, day.day % 5)]
    if open_shift:
        return events
    return events + [("break_start", 9, 30), ("break_end", 10, 0), ("out", 14, 4 + day.day % 6)]


def _late(day: date) -> list[tuple[str, int, int]]:
    return [
        ("in", 14, day.day % 4),
        ("break_start", 18, 0),
        ("break_end", 18, 30),
        ("out", 22, 6 + day.day % 5),
    ]


def run() -> None:
    get_config()
    ensure_schema()
    db = SessionLocal()
    try:
        seed_if_empty(db)
        admin = db.scalar(select(User).where(User.role == "admin").order_by(User.id))
        if admin is None:
            raise SystemExit("Administrator fehlt")
        admin.password_hash = hash_password(DEMO_PASSWORD)
        admin.must_change_password = False
        admin.web_login = True

        today = _today()
        start = today - timedelta(days=42)
        days = _workdays(start, today)
        history = days[:-1] if days and days[-1] == today else list(days)
        if len(history) < 24:
            raise SystemExit("Zu wenig Werktage für die Demo")

        flextime = db.scalar(select(WorkModel).where(WorkModel.kind == "flextime"))
        shift = db.scalar(select(WorkModel).where(WorkModel.kind == "shift"))
        produktion = db.scalar(select(Department).where(Department.name == "Produktion"))
        lager = db.scalar(select(Department).where(Department.name == "Lager"))

        max_user = _ensure_demo_user(
            db,
            username="mitarbeiter",
            first_name="Max",
            last_name="Mustermann",
            email="max@example.com",
            work_model_id=flextime.id if flextime else None,
            department_id=produktion.id if produktion else None,
            opening_hours=12.5,
            opening_on=start,
        )
        erika = _ensure_demo_user(
            db,
            username="erika",
            first_name="Erika",
            last_name="Schicht",
            email="erika@example.com",
            work_model_id=shift.id if shift else None,
            department_id=lager.id if lager else None,
            opening_hours=-6.25,
            opening_on=start,
        )

        for person in (max_user, erika):
            db.execute(delete(Punch).where(Punch.user_id == person.id))
            db.execute(delete(Absence).where(Absence.user_id == person.id))
        db.flush()

        punches: list[Punch] = []
        absences: list[Absence] = []
        vacation = set(history[4:7])
        sick = {history[9]}
        comp_time = {history[13]}
        school = {history[16]}
        missing = {history[18]}
        short = history[11]
        forgotten = history[20]
        night_friday = next(day for day in history if day.weekday() == 4 and day not in vacation)

        def away(user: User, day: date, kind: str) -> None:
            absences.append(Absence(user_id=user.id, day=day, kind=kind, note=None, created_by_id=admin.id))

        for day in history:
            if day in vacation:
                away(max_user, day, "vacation")
                continue
            if day in sick:
                away(max_user, day, "sick")
                continue
            if day in comp_time:
                away(max_user, day, "comp_time")
                continue
            if day in school:
                away(max_user, day, "school")
                continue
            if day in missing:
                continue
            if day == forgotten:
                _add(punches, max_user.id, day, [("in", 8, 2)])
                continue
            _add(
                punches,
                max_user.id,
                day,
                _office(day, short_break=day == short, no_break=day == history[22]),
            )

        if today.weekday() < 5:
            _add(punches, max_user.id, today, _office(today, open_shift=True))

        erika_vacation = set(history[14:16])
        erika_sick = {history[21]}
        for day in history:
            if day in erika_vacation:
                away(erika, day, "vacation")
                continue
            if day in erika_sick:
                away(erika, day, "sick")
                continue
            if day == night_friday:
                _add(punches, erika.id, day, [("in", 22, 0)])
                _add(punches, erika.id, day + timedelta(days=1), [("out", 6, 10)])
                continue
            if day.isocalendar().week % 2 == 0:
                _add(punches, erika.id, day, _early(day))
            else:
                _add(punches, erika.id, day, _late(day))
        if today.weekday() < 5 and today not in erika_vacation:
            _add(punches, erika.id, today, _early(today, open_shift=True))

        db.add_all(punches)
        db.add_all(absences)
        db.commit()
        print(f"Zeitraum {start.isoformat()} bis {today.isoformat()}")
        print(f"Stempel {len(punches)}, Abwesenheiten {len(absences)}")
        print(f"Zugang {admin.username} / {DEMO_PASSWORD}  (Personal)")
        print(f"Zugang {max_user.username} / {DEMO_PASSWORD}  (Gleitzeit)")
        print(f"Zugang {erika.username} / {DEMO_PASSWORD}  (Schicht)")
    finally:
        db.close()


if __name__ == "__main__":
    run()
