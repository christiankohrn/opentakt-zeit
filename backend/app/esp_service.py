from __future__ import annotations

import hashlib
import hmac
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import now_utc
from app.config import get_config
from app.models import EspTerminal, OrgSettings

FIRMWARE_MAX_BYTES = 4 * 1024 * 1024


def hash_terminal_secret(value: str) -> str:
    """ESP-Secret als SHA-256-Hex ablegen, damit ein DB-Abzug es nicht verrät."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _is_secret_hash(value: str) -> bool:
    return len(value) == 64 and all(c in "0123456789abcdef" for c in value.lower())


def check_terminal_secret(provided: str, stored: str) -> bool:
    provided = (provided or "").strip()
    stored = (stored or "").strip()
    if not provided or not stored:
        return False
    candidate = hash_terminal_secret(provided) if _is_secret_hash(stored) else provided
    left = candidate.encode("utf-8")
    right = stored.encode("utf-8")
    if len(left) != len(right):
        return False
    return hmac.compare_digest(left, right)


def org_row(db: Session) -> OrgSettings:
    row = db.get(OrgSettings, 1)
    if row is None:
        row = OrgSettings(id=1)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def effective_secret(db: Session) -> str:
    row = org_row(db)
    stored = (row.esp_terminal_secret or "").strip()
    if stored:
        if not _is_secret_hash(stored):
            row.esp_terminal_secret = hash_terminal_secret(stored)
            db.commit()
            stored = row.esp_terminal_secret
        return stored
    return (get_config().esp_terminal_secret or "").strip()


def secret_source(db: Session) -> str:
    if (org_row(db).esp_terminal_secret or "").strip():
        return "db"
    if (get_config().esp_terminal_secret or "").strip():
        return "config"
    return ""


def firmware_path() -> Path:
    cfg = get_config()
    return Path(cfg.database_path).resolve().parent / "esp-firmware.bin"


def firmware_url() -> str:
    base = (get_config().public_url or "").rstrip("/")
    return f"{base}/api/terminals/esp/firmware.bin" if base else "/api/terminals/esp/firmware.bin"


def normalize_device_id(value: str | None) -> str:
    raw = (value or "").strip().replace(":", "").replace("-", "").replace(" ", "")
    return raw.upper()[:80]


def get_device(db: Session, device_id: str) -> EspTerminal | None:
    key = normalize_device_id(device_id)
    if not key:
        return None
    return db.scalar(select(EspTerminal).where(EspTerminal.device_id == key))


def touch_device(
    db: Session,
    device_id: str,
    *,
    firmware: int | None = None,
    ssid: str | None = None,
    ip: str | None = None,
) -> EspTerminal | None:
    key = normalize_device_id(device_id)
    if not key:
        return None
    row = db.scalar(select(EspTerminal).where(EspTerminal.device_id == key))
    if row is None:
        row = EspTerminal(device_id=key, name="")
        db.add(row)
    row.last_seen_at = now_utc()
    if firmware is not None:
        row.firmware = int(firmware)
    if ssid is not None:
        row.last_ssid = (ssid or "").strip()[:80]
    if ip is not None:
        row.last_ip = (ip or "").strip()[:64]
    db.commit()
    db.refresh(row)
    return row


def device_label(row: EspTerminal | None, device_id: str = "") -> str:
    if row and (row.name or "").strip():
        return row.name.strip()
    key = (row.device_id if row else device_id) or ""
    return key or "ESP-Terminal"
