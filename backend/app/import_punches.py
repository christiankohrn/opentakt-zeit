"""Übernimmt fertige Buchungen. Zeiten bleiben erhalten, Wiederholungen ändern nichts doppelt."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import local_tz, now_utc
from app.config import get_config
from app.models import Punch, User

IMPORT_SOURCE = "import"
IMPORT_PLACE = "Import"
DELETE_REASON = "In der Quelle gelöscht"
KINDS = {"in", "out", "break_start", "break_end"}
STAT_KEYS = ("stored", "updated", "voided", "duplicate", "unknown_pnr", "skipped", "manuell")


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
    return {str(key): int(value) for key, value in data.items()}


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
    for item, user_id in resolved:
        user = users.get(user_id)
        if user is None:
            stats["unknown_pnr"] += 1
            continue
        event_id = str(item.get("event_id") or "")
        known = existing.get((user.id, event_id))
        if item.get("void"):
            _void(known, stats)
            continue
        kind = str(item.get("kind") or "")
        at = item.get("at")
        if kind not in KINDS or not isinstance(at, datetime):
            stats["skipped"] += 1
            continue
        booked = _incoming_utc(at)
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
            continue
        if known.source != IMPORT_SOURCE or known.voided_by_id is not None:
            stats["manuell" if known.voided_by_id is not None else "skipped"] += 1
            continue
        changed = known.kind != kind or not _same_instant(known.server_time, booked)
        restored = known.voided_at is not None
        if not changed and not restored:
            stats["duplicate"] += 1
            continue
        known.kind = kind
        known.server_time = booked
        known.device_time = booked
        known.source = IMPORT_SOURCE
        known.terminal_name = IMPORT_PLACE
        if restored:
            known.voided_at = None
            known.void_reason = None
        stats["updated"] += 1
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
