from __future__ import annotations

from collections import defaultdict
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.auth import as_local, now_utc
from app.models import User, WorkModel, WorkModelAssignment
from app.timecalc import model_on_day

BACKFILL_FROM = date(2000, 1, 1)
Timeline = list[tuple[date, WorkModel | None]]


def load_timeline(db: Session, user_id: int) -> Timeline:
    rows = list(
        db.scalars(
            select(WorkModelAssignment)
            .options(selectinload(WorkModelAssignment.work_model))
            .where(WorkModelAssignment.user_id == user_id)
            .order_by(WorkModelAssignment.valid_from)
        )
    )
    return [(r.valid_from, r.work_model) for r in rows]


def load_timelines(db: Session, user_ids: list[int]) -> dict[int, Timeline]:
    out: dict[int, Timeline] = defaultdict(list)
    if not user_ids:
        return out
    rows = list(
        db.scalars(
            select(WorkModelAssignment)
            .options(selectinload(WorkModelAssignment.work_model))
            .where(WorkModelAssignment.user_id.in_(user_ids))
            .order_by(WorkModelAssignment.user_id, WorkModelAssignment.valid_from)
        )
    )
    for r in rows:
        out[r.user_id].append((r.valid_from, r.work_model))
    return out


def model_for(timeline: Timeline, day: date, fallback: WorkModel | None = None) -> WorkModel | None:
    return model_on_day(timeline, day, fallback)


def sync_current_model(user: User, timeline: Timeline, today: date | None = None) -> None:
    today = today or as_local(now_utc()).date()
    model = model_on_day(timeline, today, None)
    user.work_model_id = model.id if model else None


def upsert_assignment(
    db: Session,
    user: User,
    work_model_id: int,
    valid_from: date,
    actor_id: int,
) -> WorkModelAssignment:
    if not db.get(WorkModel, work_model_id):
        raise ValueError("Arbeitszeitmodell nicht gefunden")
    existing = db.scalar(
        select(WorkModelAssignment).where(
            WorkModelAssignment.user_id == user.id,
            WorkModelAssignment.valid_from == valid_from,
        )
    )
    if existing:
        existing.work_model_id = work_model_id
        existing.created_by_id = actor_id
        row = existing
    else:
        row = WorkModelAssignment(
            user_id=user.id,
            work_model_id=work_model_id,
            valid_from=valid_from,
            created_by_id=actor_id,
        )
        db.add(row)
    db.flush()
    db.refresh(row)
    timeline = load_timeline(db, user.id)
    sync_current_model(user, timeline)
    return row


def ensure_initial_assignment(db: Session, user: User, valid_from: date = BACKFILL_FROM) -> None:
    if not user.work_model_id:
        return
    has = db.scalar(select(WorkModelAssignment.id).where(WorkModelAssignment.user_id == user.id).limit(1))
    if has:
        return
    db.add(
        WorkModelAssignment(
            user_id=user.id,
            work_model_id=user.work_model_id,
            valid_from=valid_from,
            created_by_id=user.id,
        )
    )
