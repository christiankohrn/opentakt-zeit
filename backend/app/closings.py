"""Monatsabschluss: gespeicherter Saldo, damit nicht jeder Aufruf bei Eintritt neu rechnet."""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import HTTPException
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.auth import now_utc
from app.balance import days_in_range, employment_end, hired_on
from app.models import MonthClosing, User

MONTH_NAMES = (
    "Januar",
    "Februar",
    "März",
    "April",
    "Mai",
    "Juni",
    "Juli",
    "August",
    "September",
    "Oktober",
    "November",
    "Dezember",
)


def month_end(year: int, month: int) -> date:
    if month == 12:
        return date(year, 12, 31)
    return date(year, month + 1, 1) - timedelta(days=1)


def next_month(year: int, month: int) -> tuple[int, int]:
    if month == 12:
        return year + 1, 1
    return year, month + 1


def month_label(year: int, month: int) -> str:
    return f"{MONTH_NAMES[month - 1]} {year}"


def opening_hours(user: User) -> float:
    return round(float(user.opening_balance_hours or 0), 1)


def calc_start(user: User) -> date:
    if user.opening_balance_on:
        return user.opening_balance_on
    return hired_on(user)


def first_closable(user: User) -> tuple[int, int]:
    if user.opening_balance_on:
        day = user.opening_balance_on - timedelta(days=1)
    else:
        day = hired_on(user)
    return day.year, day.month


def _delta(day: dict) -> float:
    return float(day.get("delta_hours") or 0)


def _walk(db: Session, user: User, last: date) -> tuple[float, dict[tuple[int, int], float]]:
    """Saldo am `last` und den Stand am Ende jedes Monats ab dem ersten abschließbaren Monat."""
    start = calc_start(user)
    running = opening_hours(user)
    if last < start:
        floor = start - timedelta(days=1)
        if last >= floor:
            return running, {}
        return 0.0, {}
    end = min(last, employment_end(user, last))
    by_day: dict[str, float] = {}
    if end >= start:
        for day in days_in_range(db, user, start, end):
            by_day[str(day["date"])] = _delta(day)
    snapshots: dict[tuple[int, int], float] = {}
    first = first_closable(user)
    year, month = first
    target = (last.year, last.month)
    while (year, month) <= target:
        end_day = month_end(year, month)
        cursor = date(year, month, 1)
        while cursor <= end_day:
            if cursor >= start:
                running += by_day.get(cursor.isoformat(), 0.0)
            cursor += timedelta(days=1)
        snapshots[(year, month)] = round(running, 1)
        if end_day >= last:
            break
        year, month = next_month(year, month)
    return round(running, 1), snapshots


def flex_as_of(db: Session, user: User, last: date) -> float:
    start = calc_start(user)
    chosen = _latest_usable(db, user.id, last, start)
    if chosen is not None:
        base = round(float(chosen.flex_hours), 1)
        calc_from = month_end(chosen.year, chosen.month) + timedelta(days=1)
    else:
        if last < start:
            floor = start - timedelta(days=1)
            return opening_hours(user) if last >= floor else 0.0
        base = opening_hours(user)
        calc_from = start
    if calc_from > last:
        return base
    end = min(last, employment_end(user, last))
    if end < calc_from:
        return base
    total = base + sum(_delta(day) for day in days_in_range(db, user, calc_from, end))
    return round(total, 1)


def month_delta(db: Session, user: User, year: int, month: int, today: date) -> float:
    start = max(date(year, month, 1), calc_start(user))
    end = min(month_end(year, month), employment_end(user, today))
    if end < start:
        return 0.0
    return round(sum(_delta(day) for day in days_in_range(db, user, start, end)), 1)


def _latest_usable(db: Session, user_id: int, last: date, start: date) -> MonthClosing | None:
    floor = start - timedelta(days=1)
    rows = list(
        db.scalars(
            select(MonthClosing)
            .where(MonthClosing.user_id == user_id)
            .order_by(MonthClosing.year.desc(), MonthClosing.month.desc())
        )
    )
    for row in rows:
        end = month_end(row.year, row.month)
        if floor <= end <= last:
            return row
    return None


def month_is_closed(db: Session, user_id: int, day: date) -> bool:
    return affected_closing(db, user_id, day) is not None


def affected_closing(db: Session, user_id: int, day: date) -> tuple[int, int] | None:
    row = db.scalar(
        select(MonthClosing)
        .where(
            MonthClosing.user_id == user_id,
            or_(
                MonthClosing.year > day.year,
                and_(MonthClosing.year == day.year, MonthClosing.month >= day.month),
            ),
        )
        .order_by(MonthClosing.year, MonthClosing.month)
    )
    if row is None:
        return None
    return row.year, row.month


def closed_detail(year: int, month: int) -> dict:
    label = month_label(year, month)
    return {
        "code": "closed_month",
        "months": [f"{year:04d}-{month:02d}"],
        "message": (
            f"{label} ist abgeschlossen. Die Änderung wird gespeichert und die Abschlüsse "
            "ab diesem Monat neu gerechnet."
        ),
    }


def require_open(db: Session, pairs: list[tuple[int, date]], confirm: bool) -> list[tuple[int, int, int]]:
    found: dict[int, tuple[int, int]] = {}
    for user_id, day in pairs:
        hit = affected_closing(db, user_id, day)
        if hit is None:
            continue
        previous = found.get(user_id)
        if previous is None or hit < previous:
            found[user_id] = hit
    if not found:
        return []
    if not confirm:
        year, month = min(found.values())
        raise HTTPException(status_code=409, detail=closed_detail(year, month))
    return [(user_id, year, month) for user_id, (year, month) in found.items()]


def users_for_day(db: Session, day: date) -> list[tuple[int, date]]:
    rows = db.scalars(
        select(MonthClosing.user_id)
        .where(
            or_(
                MonthClosing.year > day.year,
                and_(MonthClosing.year == day.year, MonthClosing.month >= day.month),
            )
        )
        .distinct()
    )
    return [(user_id, day) for user_id in rows]


def any_closing(db: Session) -> bool:
    return db.scalar(select(MonthClosing.id).limit(1)) is not None


def earliest_per_user(db: Session) -> list[tuple[int, int, int]]:
    rows = db.scalars(select(MonthClosing).order_by(MonthClosing.user_id, MonthClosing.year, MonthClosing.month))
    first: dict[int, tuple[int, int]] = {}
    for row in rows:
        if row.user_id not in first:
            first[row.user_id] = (row.year, row.month)
    return [(user_id, year, month) for user_id, (year, month) in first.items()]


def _store(db: Session, user: User, snapshots: dict[tuple[int, int], float], actor_id: int | None, start: tuple[int, int], create: bool) -> int:
    written = 0
    now = now_utc()
    for (year, month), flex in snapshots.items():
        if (year, month) < start:
            continue
        row = db.scalar(
            select(MonthClosing).where(
                MonthClosing.user_id == user.id,
                MonthClosing.year == year,
                MonthClosing.month == month,
            )
        )
        if row is None:
            if not create:
                continue
            db.add(
                MonthClosing(
                    user_id=user.id,
                    year=year,
                    month=month,
                    flex_hours=flex,
                    closed_at=now,
                    closed_by_id=actor_id,
                )
            )
        else:
            row.flex_hours = flex
            row.closed_at = now
            row.closed_by_id = actor_id
        written += 1
    return written


def assert_past_month(year: int, month: int) -> None:
    if not 1 <= month <= 12:
        raise HTTPException(status_code=400, detail="Ungültiger Monat")
    if month_end(year, month) >= date.today():
        raise HTTPException(status_code=400, detail="Nur Monate, die schon vorbei sind")


def close_one(db: Session, user: User, year: int, month: int, actor_id: int | None) -> int:
    first = first_closable(user)
    if first > (year, month):
        return 0
    latest = db.scalar(
        select(MonthClosing)
        .where(MonthClosing.user_id == user.id)
        .order_by(MonthClosing.year.desc(), MonthClosing.month.desc())
    )
    begin = first
    if latest is not None:
        previous = (latest.year, latest.month)
        if previous >= (year, month):
            return 0
        begin = next_month(*previous)
        if begin < first:
            begin = first
    _total, snapshots = _walk(db, user, month_end(year, month))
    return _store(db, user, snapshots, actor_id, begin, create=True)


def close_through(
    db: Session,
    year: int,
    month: int,
    actor_id: int | None,
    on_user=None,
) -> int:
    assert_past_month(year, month)
    users = list(db.scalars(select(User).order_by(User.id)))
    written = 0
    total = len(users)
    if on_user is not None:
        on_user(0, total, written)
    for index, user in enumerate(users, start=1):
        written += close_one(db, user, year, month, actor_id)
        if on_user is not None:
            on_user(index, total, written)
    return written


def recalculate_user_from(db: Session, user: User, year: int, month: int, actor_id: int | None) -> None:
    latest = db.scalar(
        select(MonthClosing)
        .where(MonthClosing.user_id == user.id)
        .order_by(MonthClosing.year.desc(), MonthClosing.month.desc())
    )
    if latest is None:
        return
    if (latest.year, latest.month) < (year, month):
        return
    _total, snapshots = _walk(db, user, month_end(latest.year, latest.month))
    _store(db, user, snapshots, actor_id, (year, month), create=False)


def recalculate_pairs(
    db: Session,
    pairs: list[tuple[int, int, int]],
    actor_id: int | None,
    on_user=None,
) -> None:
    total = len(pairs)
    if on_user is not None:
        on_user(0, total)
    for index, (user_id, year, month) in enumerate(pairs, start=1):
        user = db.get(User, user_id)
        if user is not None:
            recalculate_user_from(db, user, year, month, actor_id)
        if on_user is not None:
            on_user(index, total)


def listed_total(db: Session, user: User, today: date) -> float | None:
    """Gesamtsaldo für Listen. Ohne Abschluss und bei langer Historie nicht die ganzen Jahre lesen."""
    last = employment_end(user, today)
    start = calc_start(user)
    if _latest_usable(db, user.id, last, start) is None and (last - start).days > 120:
        return None
    return flex_as_of(db, user, last)


def refresh_closed_day(db: Session, user: User, day: date, actor_id: int | None) -> None:
    hit = affected_closing(db, user.id, day)
    if hit is not None:
        recalculate_user_from(db, user, hit[0], hit[1], actor_id)
