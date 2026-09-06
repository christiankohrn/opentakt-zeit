from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import as_local, local_day_bounds, now_utc
from app.models import Punch, User
from app.timecalc import allowed_kinds, status_from_punches

KIND_LABELS = {
    "in": "Kommen",
    "out": "Gehen",
    "break_start": "Pause",
    "break_end": "Pause Ende",
}

STATE_LABELS = {
    "away": "abwesend",
    "in": "anwesend",
    "break": "in der Pause",
}


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=ZoneInfo("UTC"))
    return dt.astimezone(ZoneInfo("UTC"))


def booking_time(device_time: datetime | None, now: datetime | None = None) -> datetime:
    """Prefer the device timestamp for offline/terminal punches, within a safe window."""
    now = now or now_utc()
    if device_time is None:
        return now
    dt = _as_utc(device_time)
    if dt > now + timedelta(minutes=5):
        return now
    if dt < now - timedelta(hours=72):
        return now
    return dt


def punches_around(db: Session, user_id: int, at: datetime) -> list[Punch]:
    day = as_local(at).date()
    start, _ = local_day_bounds(day - timedelta(days=2))
    _, end = local_day_bounds(day + timedelta(days=1))
    return list(
        db.scalars(
            select(Punch)
            .where(Punch.user_id == user_id, Punch.server_time >= start, Punch.server_time < end)
            .order_by(Punch.server_time)
        )
    )


def record_punch(
    db: Session,
    user: User,
    kind: str,
    *,
    source: str,
    client_event_id: str,
    device_time: datetime | None = None,
    note: str | None = None,
) -> Punch:
    existing = db.scalar(select(Punch).where(Punch.user_id == user.id, Punch.client_event_id == client_event_id))
    if existing:
        return existing
    booked = booking_time(device_time)
    punches = punches_around(db, user.id, booked)
    state = status_from_punches(punches)
    if kind not in allowed_kinds(state):
        raise HTTPException(
            status_code=409,
            detail=f"{KIND_LABELS.get(kind, kind)} ist im Status {STATE_LABELS.get(state, state)} nicht möglich",
        )
    punch = Punch(
        user_id=user.id,
        kind=kind,
        server_time=booked,
        device_time=device_time,
        source=source,
        client_event_id=client_event_id,
        note=note,
    )
    db.add(punch)
    db.commit()
    db.refresh(punch)
    return punch
