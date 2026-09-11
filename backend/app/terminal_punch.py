from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import now_utc
from app.datafox import normalize_badge
from app.models import AuditEvent, Punch, User
from app.punches import KIND_LABELS, punches_around, record_punch
from app.timecalc import status_from_punches


@dataclass
class BookingResult:
    outcome: str
    detail: str
    user_id: int | None = None
    punch_id: int | None = None
    kind: str | None = None
    display_name: str | None = None


def find_user_by_badge(db: Session, badge: str) -> User | None:
    keys = normalize_badge(badge)
    if not keys:
        return None
    users = list(db.scalars(select(User).where(User.active.is_(True), User.transponder_id.is_not(None))))
    for user in users:
        if normalize_badge(user.transponder_id or "") & keys:
            return user
    return None


def auto_kind_for(db: Session, user: User, when: datetime | None = None) -> str:
    punches = punches_around(db, user.id, when or now_utc())
    if status_from_punches(punches) == "away":
        return "in"
    return "out"


def apply_booking(
    db: Session,
    *,
    badge: str,
    kind: str | None,
    timestamp: datetime | None,
    event_id: str,
    source: str,
    note: str | None,
    persist: bool,
    enforce_state: bool = True,
    device_id: str | None = None,
    terminal_name: str | None = None,
) -> BookingResult:
    if not badge or not kind:
        return BookingResult("invalid", "Ungültige Buchung")
    user = find_user_by_badge(db, badge)
    if not user:
        return BookingResult("unknown", "Unbekannter Ausweis")
    label = KIND_LABELS.get(kind, kind)
    if not persist:
        return BookingResult(
            "preview",
            f"{user.display_name}: {label}",
            user_id=user.id,
            kind=kind,
            display_name=user.display_name,
        )
    existing = db.scalar(select(Punch).where(Punch.user_id == user.id, Punch.client_event_id == event_id))
    try:
        punch = record_punch(
            db,
            user,
            kind,
            source=source,
            client_event_id=event_id[:64],
            device_time=timestamp,
            note=note,
            enforce_state=enforce_state,
            device_id=device_id,
            terminal_name=terminal_name,
        )
    except HTTPException as exc:
        if exc.status_code == 409:
            return BookingResult(
                "conflict",
                str(exc.detail),
                user_id=user.id,
                kind=kind,
                display_name=user.display_name,
            )
        raise
    if existing is None:
        db.add(
            AuditEvent(
                actor_id=user.id,
                action="terminal.punch",
                entity_type="punch",
                entity_id=str(punch.id),
                payload=label,
            )
        )
        db.commit()
        return BookingResult(
            "stored",
            f"{user.display_name}: {label}",
            user_id=user.id,
            punch_id=punch.id,
            kind=kind,
            display_name=user.display_name,
        )
    return BookingResult(
        "duplicate",
        f"{user.display_name}: {label} (bereits gespeichert)",
        user_id=user.id,
        punch_id=punch.id,
        kind=kind,
        display_name=user.display_name,
    )
