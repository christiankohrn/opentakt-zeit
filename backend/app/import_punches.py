"""Übernimmt fertige Buchungen. Zeiten bleiben erhalten, Wiederholungen ändern nichts doppelt."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.auth import as_local, local_tz, now_utc
from app.config import get_config
from app.models import Absence, MonthClosing, Punch, User

IMPORT_SOURCE = "import"
IMPORT_PLACE = "Import"
DELETE_REASON = "In der Quelle gelöscht"
KINDS = {"in", "out", "break_start", "break_end"}
STAT_KEYS = ("stored", "updated", "voided", "duplicate", "unknown_pnr", "skipped", "manuell", "before_ledger")


def pnr_key(value: str | None) -> str:
    text = (value or "").strip()
    if not text or text == "<null>":
        return ""
    if text.replace(".", "", 1).isdigit() and text.count(".") <= 1 and "." in text:
        text = str(int(float(text)))
    if text.isdigit():
        return str(int(text))
    return text.casefold()


def map_path() -> Path:
    return Path(get_config().database_path).resolve().parent / "pnr-map.json"


def load_pnr_map() -> dict[str, int]:
    path = map_path()
    if not path.is_file():
        raise FileNotFoundError(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("pnr-map.json")
    # Die Datei behält die Nummer aus der Quelle, auch mit führender Null.
    # Die Buchung sucht die gekürzte Form, sonst trifft 01046 den Eintrag nie.
    found: dict[str, int] = {}
    for key, value in data.items():
        norm = pnr_key(str(key))
        if norm and norm not in found:
            found[norm] = int(value)
    return found


def _incoming_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=local_tz())
    return dt.astimezone(ZoneInfo("UTC"))


def _stored_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=ZoneInfo("UTC"))
    return dt.astimezone(ZoneInfo("UTC"))


def _same_instant(stored: datetime, incoming_utc: datetime) -> bool:
    return abs((_stored_utc(stored) - _stored_utc(incoming_utc)).total_seconds()) < 1


def empty_stats() -> dict[str, int]:
    return {key: 0 for key in STAT_KEYS}


def _load_existing(db: Session, event_ids: list[str]) -> dict[tuple[int, str], Punch]:
    found: dict[tuple[int, str], Punch] = {}
    unique = [event_id for event_id in dict.fromkeys(event_ids) if event_id]
    for start in range(0, len(unique), 400):
        chunk = unique[start : start + 400]
        rows = db.scalars(select(Punch).where(Punch.client_event_id.in_(chunk))).all()
        for punch in rows:
            found[(punch.user_id, punch.client_event_id or "")] = punch
    return found


def apply_import(db: Session, punches: list[dict]) -> dict[str, int]:
    stats = empty_stats()
    mapping = load_pnr_map()
    resolved: list[tuple[dict, int]] = []
    for item in punches:
        key = pnr_key(str(item.get("pnr") or ""))
        user_id = mapping.get(key)
        if not key or user_id is None:
            stats["unknown_pnr"] += 1
            continue
        resolved.append((item, user_id))
    user_ids = list({user_id for _, user_id in resolved})
    users = {
        user.id: user
        for user in db.scalars(select(User).where(User.id.in_(user_ids))).all()
    } if user_ids else {}
    existing = _load_existing(db, [str(item.get("event_id") or "") for item, _user_id in resolved])
    from app.closings import ledger_from

    floor = ledger_from(db)
    touched: set[tuple[int, date]] = set()
    for item, user_id in resolved:
        user = users.get(user_id)
        if user is None:
            stats["unknown_pnr"] += 1
            continue
        event_id = str(item.get("event_id") or "")
        known = existing.get((user.id, event_id))
        if item.get("void"):
            if known is not None and known.server_time is not None and _before(floor, known.server_time):
                stats["before_ledger"] += 1
                continue
            if known is not None and known.server_time is not None and known.voided_at is None and known.voided_by_id is None and known.source == IMPORT_SOURCE:
                touched.add((user.id, as_local(known.server_time).date()))
            _void(known, stats)
            continue
        kind = str(item.get("kind") or "")
        at = item.get("at")
        if kind not in KINDS or not isinstance(at, datetime):
            stats["skipped"] += 1
            continue
        booked = _incoming_utc(at)
        if _before(floor, booked):
            stats["before_ledger"] += 1
            continue
        if known is None:
            punch = Punch(
                user_id=user.id,
                kind=kind,
                server_time=booked,
                device_time=booked,
                source=IMPORT_SOURCE,
                client_event_id=event_id,
                terminal_name=IMPORT_PLACE,
            )
            db.add(punch)
            existing[(user.id, event_id)] = punch
            stats["stored"] += 1
            touched.add((user.id, as_local(booked).date()))
            continue
        if known.source != IMPORT_SOURCE or known.voided_by_id is not None:
            stats["manuell" if known.voided_by_id is not None else "skipped"] += 1
            continue
        changed = known.kind != kind or not _same_instant(known.server_time, booked)
        restored = known.voided_at is not None
        if not changed and not restored:
            stats["duplicate"] += 1
            continue
        previous_day = as_local(known.server_time).date() if known.server_time is not None else None
        known.kind = kind
        known.server_time = booked
        known.device_time = booked
        known.source = IMPORT_SOURCE
        known.terminal_name = IMPORT_PLACE
        if restored:
            known.voided_at = None
            known.void_reason = None
        stats["updated"] += 1
        touched.add((user.id, as_local(booked).date()))
        if previous_day is not None:
            touched.add((user.id, previous_day))
    db.flush()
    from app.closings import refresh_closed_day

    refreshed: set[int] = set()
    for user_id, day in sorted(touched):
        if user_id in refreshed:
            continue
        user = users.get(user_id)
        if user is None:
            continue
        refresh_closed_day(db, user, day, None)
        refreshed.add(user_id)
    db.commit()
    return stats


def apply_absences(db: Session, days: list[dict]) -> dict[str, int]:
    """Legt Krankheitstage an. Ein vorhandener Tag bleibt, auch wenn er kein Krankheitstag ist."""
    stats = {"stored": 0, "duplicate": 0, "unknown_pnr": 0, "skipped": 0, "before_ledger": 0}
    mapping = load_pnr_map()
    actor_id = db.scalar(select(User.id).where(User.role == "admin").order_by(User.id))
    if actor_id is None:
        raise ValueError("kein Administrator")
    from app.closings import ledger_from, refresh_closed_day

    floor = ledger_from(db)
    touched: dict[int, date] = {}
    for item in days:
        key = pnr_key(str(item.get("pnr") or ""))
        user_id = mapping.get(key)
        if not key or user_id is None:
            stats["unknown_pnr"] += 1
            continue
        day = item.get("day")
        if not isinstance(day, date) or str(item.get("kind") or "sick") != "sick":
            stats["skipped"] += 1
            continue
        if floor is not None and day < floor:
            stats["before_ledger"] += 1
            continue
        existing = db.scalar(select(Absence).where(Absence.user_id == user_id, Absence.day == day))
        if existing is not None:
            stats["duplicate" if existing.kind == "sick" else "skipped"] += 1
            continue
        db.add(
            Absence(
                user_id=user_id,
                day=day,
                kind="sick",
                note=None,
                created_by_id=actor_id,
            )
        )
        stats["stored"] += 1
        previous = touched.get(user_id)
        if previous is None or day < previous:
            touched[user_id] = day
    db.flush()
    if touched:
        users = {
            user.id: user
            for user in db.scalars(select(User).where(User.id.in_(list(touched)))).all()
        }
        for user_id, day in touched.items():
            user = users.get(user_id)
            if user is not None:
                refresh_closed_day(db, user, day, None)
    db.commit()
    return stats


def _before(floor: date | None, moment: datetime | None) -> bool:
    if floor is None or moment is None:
        return False
    return as_local(moment).date() < floor


def apply_openings(db: Session, people: list[dict]) -> dict[str, int]:
    """Übernimmt den Endsaldo je Personalnummer. Das ist der Stand am Beginn von `on`."""
    from app.closings import recalculate_pairs

    stats = {"updated": 0, "unknown_pnr": 0}
    mapping = load_pnr_map()
    changed: list[tuple[User, date]] = []
    for item in people:
        key = pnr_key(str(item.get("pnr") or ""))
        user_id = mapping.get(key)
        if not key or user_id is None:
            stats["unknown_pnr"] += 1
            continue
        user = db.get(User, user_id)
        on = item.get("on")
        if user is None or not isinstance(on, date):
            stats["unknown_pnr"] += 1
            continue
        user.opening_balance_hours = float(item.get("hours") or 0)
        user.opening_balance_on = on
        changed.append((user, on))
        stats["updated"] += 1
    db.flush()
    pairs: list[tuple[int, int, int]] = []
    for user, on in changed:
        early = list(
            db.scalars(
                select(MonthClosing).where(
                    MonthClosing.user_id == user.id,
                    or_(
                        MonthClosing.year < on.year,
                        and_(MonthClosing.year == on.year, MonthClosing.month < on.month),
                    ),
                )
            )
        )
        for row in early:
            db.delete(row)
        later = db.scalar(
            select(MonthClosing.id).where(
                MonthClosing.user_id == user.id,
                or_(
                    MonthClosing.year > on.year,
                    and_(MonthClosing.year == on.year, MonthClosing.month >= on.month),
                ),
            )
        )
        if later is not None:
            pairs.append((user.id, on.year, on.month))
    db.flush()
    recalculate_pairs(db, pairs, None)
    db.commit()
    return stats


def _void(existing: Punch | None, stats: dict[str, int]) -> None:
    if existing is None or existing.source != IMPORT_SOURCE:
        stats["skipped"] += 1
        return
    if existing.voided_by_id is not None:
        stats["manuell"] += 1
        return
    if existing.voided_at is not None:
        stats["duplicate"] += 1
        return
    existing.voided_at = now_utc()
    existing.void_reason = DELETE_REASON
    stats["voided"] += 1
