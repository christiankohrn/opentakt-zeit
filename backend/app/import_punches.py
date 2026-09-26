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


def apply_import(db: Session, punches: list[dict]) -> dict[str, int]:
    stats = empty_stats()
    mapping = load_pnr_map()
    users: dict[int, User | None] = {}
    for item in punches:
        key = pnr_key(str(item.get("pnr") or ""))
        user_id = mapping.get(key)
        if not key or user_id is None:
            stats["unknown_pnr"] += 1
            continue
        if user_id not in users:
            users[user_id] = db.get(User, user_id)
        user = users[user_id]
        if user is None:
            stats["unknown_pnr"] += 1
            continue
        event_id = str(item.get("event_id") or "")
        existing = db.scalar(
            select(Punch).where(Punch.user_id == user.id, Punch.client_event_id == event_id)
        )
        if item.get("void"):
            _void(existing, stats)
            continue
        kind = str(item.get("kind") or "")
        at = item.get("at")
        if kind not in KINDS or not isinstance(at, datetime):
            stats["skipped"] += 1
            continue
        booked = _incoming_utc(at)
        if existing is None:
            db.add(
                Punch(
                    user_id=user.id,
                    kind=kind,
                    server_time=booked,
                    device_time=booked,
                    source=IMPORT_SOURCE,
                    client_event_id=event_id,
                    terminal_name=IMPORT_PLACE,
                )
            )
            stats["stored"] += 1
            continue
        if existing.source != IMPORT_SOURCE or existing.voided_by_id is not None:
            stats["manuell" if existing.voided_by_id is not None else "skipped"] += 1
            continue
        changed = existing.kind != kind or not _same_instant(existing.server_time, booked)
        restored = existing.voided_at is not None
        if not changed and not restored:
            stats["duplicate"] += 1
            continue
        existing.kind = kind
        existing.server_time = booked
        existing.device_time = booked
        existing.source = IMPORT_SOURCE
        existing.terminal_name = IMPORT_PLACE
        if restored:
            existing.voided_at = None
            existing.void_reason = None
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
