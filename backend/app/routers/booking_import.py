"""Schnittstelle für die laufende Buchungs-Übernahme."""

from __future__ import annotations

import hmac
import re
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.config import get_config
from app.database import get_db
from app.import_punches import apply_import, apply_openings

router = APIRouter(prefix="/import", tags=["import"])

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


def _token_ok(provided: str, expected: str) -> bool:
    left = provided.encode("utf-8")
    right = expected.encode("utf-8")
    if not left or not right or len(left) != len(right):
        return False
    return hmac.compare_digest(left, right)


def require_token(request: Request) -> None:
    expected = (get_config().import_token or "").strip()
    if not expected:
        raise HTTPException(503, "Import ist nicht konfiguriert")
    header = request.headers.get("authorization") or ""
    provided = header[7:].strip() if header.lower().startswith("bearer ") else ""
    if not _token_ok(provided, expected):
        raise HTTPException(401, "Zugang verweigert")


@router.post("/punches")
def import_punches(
    payload: ImportBatchIn,
    request: Request,
    db: Session = Depends(get_db),
):
    require_token(request)
    try:
        stats = apply_import(db, [item.model_dump() for item in payload.punches])
    except FileNotFoundError:
        raise HTTPException(409, "pnr-map.json fehlt neben der Datenbank") from None
    except ValueError:
        raise HTTPException(409, "pnr-map.json ist ungültig") from None
    return stats


@router.post("/openings")
def import_openings(
    payload: OpeningsIn,
    request: Request,
    db: Session = Depends(get_db),
):
    require_token(request)
    try:
        return apply_openings(db, [item.model_dump() for item in payload.people])
    except FileNotFoundError:
        raise HTTPException(409, "pnr-map.json fehlt neben der Datenbank") from None
    except ValueError:
        raise HTTPException(409, "pnr-map.json ist ungültig") from None
