"""Schnittstelle für die laufende Buchungs-Übernahme."""

from __future__ import annotations

import json
import re
import secrets
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.auth import current_user, require_admin
from app.config import get_config
from app.database import get_db
from app.import_punches import apply_import, apply_openings
from app.models import AuditEvent, OrgSettings, User
from app.ratelimit import IMPORT_MAX, IMPORT_WINDOW, check, clear, client_key, record
from app.security import check_secret, hash_secret, is_secret_hash

router = APIRouter(prefix="/import", tags=["import"])
hr_router = APIRouter(prefix="/hr/import", tags=["import"])

_EVENT_ID = re.compile(r"[A-Za-z0-9_.:-]{1,64}")


class ImportPunchIn(BaseModel):
    pnr: str
    event_id: str
    kind: str | None = None
    at: datetime | None = None
    void: bool = False

    @field_validator("event_id")
    @classmethod
    def check_event_id(cls, value: str) -> str:
        if not _EVENT_ID.fullmatch(value):
            raise ValueError("ungültige Kennung")
        return value


class OpeningIn(BaseModel):
    pnr: str
    hours: float
    on: date


class OpeningsIn(BaseModel):
    people: list[OpeningIn] = Field(default_factory=list)

    @field_validator("people")
    @classmethod
    def check_people(cls, value: list[OpeningIn]) -> list[OpeningIn]:
        if len(value) > 1000:
            raise ValueError("höchstens 1000 Personen je Aufruf")
        return value


class ImportBatchIn(BaseModel):
    punches: list[ImportPunchIn] = Field(default_factory=list)

    @field_validator("punches")
    @classmethod
    def check_batch(cls, value: list[ImportPunchIn]) -> list[ImportPunchIn]:
        if len(value) > 1000:
            raise ValueError("höchstens 1000 Buchungen je Aufruf")
        return value


def _org(db: Session) -> OrgSettings:
    row = db.get(OrgSettings, 1)
    if row is None:
        row = OrgSettings(id=1)
        db.add(row)
        db.flush()
    return row


def effective_token(db: Session) -> str:
    row = _org(db)
    stored = (row.import_token or "").strip()
    if stored:
        if not is_secret_hash(stored):
            row.import_token = hash_secret(stored)
            db.commit()
            stored = row.import_token
        return stored
    return (get_config().import_token or "").strip()


def token_source(db: Session) -> str:
    if (_org(db).import_token or "").strip():
        return "db"
    if (get_config().import_token or "").strip():
        return "config"
    return ""


def require_token(request: Request, db: Session, *, endpoint: str) -> None:
    key = client_key(request, "import")
    check(key, IMPORT_MAX, IMPORT_WINDOW)
    expected = effective_token(db)
    if not expected:
        raise HTTPException(503, "Import ist nicht konfiguriert")
    header = request.headers.get("authorization") or ""
    provided = header[7:].strip() if header.lower().startswith("bearer ") else ""
    if not check_secret(provided, expected):
        record(key, IMPORT_WINDOW)
        db.add(
            AuditEvent(
                actor_id=None,
                action="import.denied",
                entity_type="import",
                entity_id=endpoint,
            )
        )
        db.commit()
        raise HTTPException(401, "Zugang verweigert")
    clear(key)


def _audit_batch(db: Session, action: str, stats: dict) -> None:
    if not any(int(stats.get(k) or 0) for k in ("stored", "updated", "voided")):
        return
    db.add(
        AuditEvent(
            actor_id=None,
            action=action,
            entity_type="import",
            entity_id="batch",
            payload=json.dumps(stats),
        )
    )
    db.commit()


@router.post("/punches")
def import_punches(
    payload: ImportBatchIn,
    request: Request,
    db: Session = Depends(get_db),
):
    require_token(request, db, endpoint="punches")
    try:
        stats = apply_import(db, [item.model_dump() for item in payload.punches])
    except FileNotFoundError:
        raise HTTPException(409, "pnr-map.json fehlt neben der Datenbank") from None
    except ValueError:
        raise HTTPException(409, "pnr-map.json ist ungültig") from None
    _audit_batch(db, "import.punches", stats)
    return stats


@router.post("/openings")
def import_openings(
    payload: OpeningsIn,
    request: Request,
    db: Session = Depends(get_db),
):
    require_token(request, db, endpoint="openings")
    try:
        stats = apply_openings(db, [item.model_dump() for item in payload.people])
    except FileNotFoundError:
        raise HTTPException(409, "pnr-map.json fehlt neben der Datenbank") from None
    except ValueError:
        raise HTTPException(409, "pnr-map.json ist ungültig") from None
    _audit_batch(db, "import.openings", stats)
    return stats


class ImportTokenOut(BaseModel):
    token: str = ""
    configured: bool = False
    source: str = ""


class ImportTokenIn(BaseModel):
    token: Optional[str] = Field(default=None, max_length=200)


def _admin(request: Request, db: Session) -> User:
    return require_admin(current_user(request, db))


def _token_out(db: Session, *, reveal: str = "") -> ImportTokenOut:
    expected = effective_token(db)
    return ImportTokenOut(token=reveal, configured=bool(expected), source=token_source(db) if expected else "")


@hr_router.get("", response_model=ImportTokenOut)
def import_token_status(request: Request, db: Session = Depends(get_db)):
    _admin(request, db)
    return _token_out(db)


@hr_router.patch("", response_model=ImportTokenOut)
def set_import_token(payload: ImportTokenIn, request: Request, db: Session = Depends(get_db)):
    actor = _admin(request, db)
    dumped = payload.model_dump(exclude_unset=True)
    if "token" in dumped and dumped["token"] is not None:
        value = dumped["token"].strip()
        _org(db).import_token = hash_secret(value) if value else ""
        db.add(
            AuditEvent(
                actor_id=actor.id,
                action="import.token",
                entity_type="org",
                entity_id="1",
                payload="gesetzt" if value else "geleert",
            )
        )
        db.commit()
    return _token_out(db)


@hr_router.post("/token", response_model=ImportTokenOut)
def rotate_import_token(request: Request, db: Session = Depends(get_db)):
    actor = _admin(request, db)
    plaintext = secrets.token_urlsafe(32)
    _org(db).import_token = hash_secret(plaintext)
    db.add(
        AuditEvent(
            actor_id=actor.id,
            action="import.token",
            entity_type="org",
            entity_id="1",
            payload="neu",
        )
    )
    db.commit()
    return _token_out(db, reveal=plaintext)
