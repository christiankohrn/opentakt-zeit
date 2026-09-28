"""Manuelle Buchungen auf Zeit- und Urlaubskonto."""

from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AccountEntry


def _sum(db: Session, user_id: int, kind: str, start: date, end: date) -> float:
    if end < start:
        return 0.0
    total = db.scalar(
        select(func.coalesce(func.sum(AccountEntry.amount), 0.0)).where(
            AccountEntry.user_id == user_id,
            AccountEntry.kind == kind,
            AccountEntry.day >= start,
            AccountEntry.day <= end,
        )
    )
    return float(total or 0.0)


def time_hours(db: Session, user_id: int, start: date, end: date) -> float:
    return _sum(db, user_id, "time", start, end)


def vacation_days(db: Session, user_id: int, start: date, end: date) -> float:
    return _sum(db, user_id, "vacation", start, end)
