from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import date, timedelta
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.auth import as_local, now_utc
from app.models import MonthClosing, User, WorkModel, WorkModelAssignment
from app.timecalc import model_on_day

WEEKDAY_KEYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
_CLOCK = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
RULE_FIELDS = (
    "hours_mon",
    "hours_tue",
    "hours_wed",
    "hours_thu",
    "hours_fri",
    "hours_sat",
    "hours_sun",
    "round_start_before",
    "round_start_after",
    "round_end_before",
    "round_end_after",
    "round_first_threshold",
    "round_first_step",
    "round_last_threshold",
    "round_last_step",
    "booking_corridor",
    "shifts",
)
CLOSED_NOTICE = (
    "Abgeschlossene Monate behalten die bisherige Berechnung. Die Änderung gilt nur für offene Monate."
)

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


def corridor_dict(raw: object) -> dict:
    if isinstance(raw, dict):
        data = raw
    elif isinstance(raw, str) and raw.strip():
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return {}
    else:
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def normalize_corridor(raw: dict | None) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for key, slot in (raw or {}).items():
        if key not in WEEKDAY_KEYS or slot is None:
            continue
        start = getattr(slot, "start", None) if not isinstance(slot, dict) else slot.get("start")
        end = getattr(slot, "end", None) if not isinstance(slot, dict) else slot.get("end")
        start = (start or "").strip()
        end = (end or "").strip()
        if start and not _CLOCK.match(start):
            raise ValueError("Buchungskorridor braucht eine Uhrzeit HH:MM")
        if end and not _CLOCK.match(end):
            raise ValueError("Buchungskorridor braucht eine Uhrzeit HH:MM")
        if start or end:
            out[key] = {"start": start, "end": end}
    return out


def _pair(slot: object) -> tuple[str, str]:
    if isinstance(slot, dict):
        start, end = slot.get("start"), slot.get("end")
    else:
        start, end = getattr(slot, "start", None), getattr(slot, "end", None)
    return (start or "").strip(), (end or "").strip()


def normalize_shifts(raw: list | None) -> list[dict]:
    out: list[dict] = []
    defaults = ("Früh", "Spät", "Nacht", "Schicht 4")
    for index, slot in enumerate(raw or []):
        if slot is None:
            continue
        if isinstance(slot, dict):
            name = slot.get("name")
            days_in = slot.get("days") if isinstance(slot.get("days"), dict) else {}
            legacy_start, legacy_end = _pair(slot)
        else:
            name = getattr(slot, "name", None)
            days_in = getattr(slot, "days", None) or {}
            if not isinstance(days_in, dict):
                days_in = {}
            legacy_start, legacy_end = _pair(slot)
        if not days_in and legacy_start and legacy_end:
            days_in = {key: {"start": legacy_start, "end": legacy_end} for key in WEEKDAY_KEYS}
        days: dict[str, dict[str, str]] = {}
        for key, value in days_in.items():
            if key not in WEEKDAY_KEYS or value is None:
                continue
            start, end = _pair(value)
            if not start and not end:
                continue
            if not start or not end:
                raise ValueError("Jeder angegebene Korridor braucht Beginn und Ende")
            if not _CLOCK.match(start) or not _CLOCK.match(end):
                raise ValueError("Schicht braucht eine Uhrzeit HH:MM")
            if start == end:
                raise ValueError("Beginn und Ende einer Schicht dürfen nicht gleich sein")
            days[key] = {"start": start, "end": end}
        name = (name or "").strip()
        if not name and not days:
            continue
        if not name:
            name = defaults[index] if index < len(defaults) else f"Schicht {index + 1}"
        out.append({"name": name[:40], "days": days})
    if len(out) > 4:
        raise ValueError("Höchstens 4 Schichten")
    return out


def shifts_list(raw: object) -> list:
    if isinstance(raw, list):
        data = raw
    elif isinstance(raw, str) and raw.strip():
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return []
    else:
        return []
    return data if isinstance(data, list) else []


def rules_payload(model: WorkModel) -> dict:
    payload = {name: getattr(model, name) for name in RULE_FIELDS if name not in {"booking_corridor", "shifts"}}
    payload["booking_corridor"] = corridor_dict(model.booking_corridor)
    payload["shifts"] = shifts_list(getattr(model, "shifts", ""))
    return payload


def overlay_model(model: WorkModel | None, fields: dict | None):
    if model is None or not fields:
        return model
    data = {name: getattr(model, name, None) for name in ("id", "name", "kind", *RULE_FIELDS)}
    data.update(fields)
    if isinstance(data.get("booking_corridor"), dict):
        data["booking_corridor"] = json.dumps(data["booking_corridor"])
    if isinstance(data.get("shifts"), list):
        data["shifts"] = json.dumps(data["shifts"])
    return SimpleNamespace(**data)


def load_frozen_map(db: Session, user_ids: list[int]) -> dict[tuple[int, int, int], dict]:
    if not user_ids:
        return {}
    rows = db.scalars(select(MonthClosing).where(MonthClosing.user_id.in_(user_ids)))
    out: dict[tuple[int, int, int], dict] = {}
    for row in rows:
        try:
            blob = json.loads(row.rules_json or "{}")
        except json.JSONDecodeError:
            blob = {}
        out[(row.user_id, row.year, row.month)] = blob if isinstance(blob, dict) else {}
    return out


def _month_days(year: int, month: int):
    cursor = date(year, month, 1)
    while cursor.month == month:
        yield cursor
        cursor += timedelta(days=1)


def month_uses_model(timeline: Timeline, year: int, month: int, model_id: int, fallback: WorkModel | None) -> bool:
    for day in _month_days(year, month):
        found = model_for(timeline, day, fallback)
        if found is not None and found.id == model_id:
            return True
    return False


def _affected_users(db: Session, model_id: int) -> list[User]:
    assigned = {
        row.user_id
        for row in db.scalars(select(WorkModelAssignment).where(WorkModelAssignment.work_model_id == model_id))
    }
    direct = set(db.scalars(select(User.id).where(User.work_model_id == model_id)))
    ids = assigned | direct
    if not ids:
        return []
    return list(db.scalars(select(User).where(User.id.in_(ids))))


def closed_month_count(db: Session, model_id: int) -> int:
    count = 0
    for user in _affected_users(db, model_id):
        timeline = load_timeline(db, user.id)
        rows = db.scalars(select(MonthClosing).where(MonthClosing.user_id == user.id))
        for closing in rows:
            if month_uses_model(timeline, closing.year, closing.month, model_id, user.work_model):
                count += 1
    return count


def freeze_rules(db: Session, model: WorkModel) -> None:
    """Bisherige Regeln an abgeschlossene Monate heften, die dieses Modell nutzen."""
    current = rules_payload(model)
    key = str(model.id)
    for user in _affected_users(db, model_id=model.id):
        timeline = load_timeline(db, user.id)
        rows = db.scalars(select(MonthClosing).where(MonthClosing.user_id == user.id))
        for closing in rows:
            if not month_uses_model(timeline, closing.year, closing.month, model.id, user.work_model):
                continue
            try:
                blob = json.loads(closing.rules_json or "{}")
            except json.JSONDecodeError:
                blob = {}
            if not isinstance(blob, dict):
                blob = {}
            if key in blob:
                continue
            blob[key] = current
            closing.rules_json = json.dumps(blob)


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
