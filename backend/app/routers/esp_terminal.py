from __future__ import annotations

import hmac
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.auth import current_user, require_admin
from app.balance import account_hours, format_flex
from app.config import get_config
from app.database import get_db
from app.dfcom_poll import org_row
from app.esp_display import DEFAULT_OK_LINE1, DEFAULT_OK_LINE2, punch_values, render_line
from app.models import AuditEvent, Punch, User
from app.schemas import EspPunchIn, EspPunchOut, EspTerminalSettingsIn, EspTerminalSettingsOut
from app.terminal_punch import apply_booking, auto_kind_for, find_user_by_badge

log = logging.getLogger(__name__)

router = APIRouter(prefix="/terminals/esp", tags=["esp-terminal"])
hr_router = APIRouter(prefix="/hr/esp-terminal", tags=["esp-terminal"])


def _secret() -> str:
    return (get_config().esp_terminal_secret or "").strip()


def _secret_ok(provided: str) -> bool:
    expected = _secret()
    if not expected or not provided:
        return False
    left = provided.encode("utf-8")
    right = expected.encode("utf-8")
    if len(left) != len(right):
        return False
    return hmac.compare_digest(left, right)


def _provided_key(request: Request) -> str:
    auth = request.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return (request.headers.get("x-terminal-key") or "").strip()


def _lines(db: Session, *, display_name: str | None, kind: str | None, punch: Punch | None) -> tuple[str, str]:
    row = org_row(db)
    flex_month = ""
    flex_total = ""
    account_user = db.get(User, punch.user_id) if punch is not None else None
    if account_user and punch:
        try:
            month_h, total_h = account_hours(db, account_user, punch.server_time)
            flex_month = format_flex(month_h)
            flex_total = format_flex(total_h)
        except Exception:
            log.exception("esp flex display failed")
    values = punch_values(
        display_name=display_name or (account_user.display_name if account_user else None),
        kind=kind,
        flex_month=flex_month,
        flex_total=flex_total,
    )
    line1 = render_line(getattr(row, "esp_ok_line1", None) or DEFAULT_OK_LINE1, values)
    line2 = render_line(getattr(row, "esp_ok_line2", None) or DEFAULT_OK_LINE2, values)
    return line1 or "OK", line2


@router.post("/punch", response_model=EspPunchOut)
def punch(payload: EspPunchIn, request: Request, db: Session = Depends(get_db)):
    if not _secret():
        raise HTTPException(503, "ESP-Terminal nicht konfiguriert")
    if not _secret_ok(_provided_key(request)):
        raise HTTPException(401, "Zugang verweigert")

    badge = (payload.badge or "").strip()
    user = find_user_by_badge(db, badge)
    if not user:
        return EspPunchOut(ok=False, line1="Unbekannt", line2="Ausweis")

    kind = auto_kind_for(db, user)
    device = (payload.device_id or "").strip()
    result = apply_booking(
        db,
        badge=badge,
        kind=kind,
        timestamp=None,
        event_id=f"esp-{payload.event_id.strip()}"[:64],
        source="esp",
        note=f"esp {device}".strip() if device else "esp",
        persist=True,
    )
    if result.outcome == "unknown":
        return EspPunchOut(ok=False, line1="Unbekannt", line2="Ausweis")
    if result.outcome == "invalid":
        return EspPunchOut(ok=False, line1="Ungueltig", line2="Buchung")
    if result.outcome == "conflict":
        return EspPunchOut(ok=False, line1="Nicht moeglich", line2=render_line(result.detail, {}), kind=kind)

    punch_row = db.get(Punch, result.punch_id) if result.punch_id else None
    line1, line2 = _lines(db, display_name=result.display_name, kind=result.kind, punch=punch_row)
    return EspPunchOut(ok=True, line1=line1, line2=line2, kind=result.kind)


def _admin(request: Request, db: Session) -> User:
    return require_admin(current_user(request, db))


def _settings_out(db: Session) -> EspTerminalSettingsOut:
    row = org_row(db)
    return EspTerminalSettingsOut(
        secret_configured=bool(_secret()),
        ok_line1=getattr(row, "esp_ok_line1", None) or DEFAULT_OK_LINE1,
        ok_line2=getattr(row, "esp_ok_line2", None) or DEFAULT_OK_LINE2,
    )


@hr_router.get("", response_model=EspTerminalSettingsOut)
def get_esp_settings(request: Request, db: Session = Depends(get_db)):
    _admin(request, db)
    return _settings_out(db)


@hr_router.patch("", response_model=EspTerminalSettingsOut)
def patch_esp_settings(payload: EspTerminalSettingsIn, request: Request, db: Session = Depends(get_db)):
    actor = _admin(request, db)
    row = org_row(db)
    dumped = payload.model_dump(exclude_unset=True)
    if "ok_line1" in dumped and dumped["ok_line1"] is not None:
        row.esp_ok_line1 = dumped["ok_line1"].strip() or DEFAULT_OK_LINE1
    if "ok_line2" in dumped and dumped["ok_line2"] is not None:
        row.esp_ok_line2 = dumped["ok_line2"].strip() or DEFAULT_OK_LINE2
    db.add(
        AuditEvent(
            actor_id=actor.id,
            action="esp.settings",
            entity_type="org",
            entity_id="1",
            payload=json.dumps(dumped),
        )
    )
    db.commit()
    return _settings_out(db)
