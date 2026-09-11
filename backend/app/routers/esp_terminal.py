from __future__ import annotations

import hmac
import json
import logging
import secrets

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import current_user, require_admin
from app.balance import account_hours, format_flex
from app.database import get_db
from app.esp_display import DEFAULT_OK_LINE1, DEFAULT_OK_LINE2, LINE_MAX, punch_values, render_line
from app.esp_service import (
    FIRMWARE_MAX_BYTES,
    device_label,
    effective_secret,
    firmware_path,
    firmware_url,
    normalize_device_id,
    org_row,
    secret_source,
    touch_device,
)
from app.models import AuditEvent, EspTerminal, Punch, User
from app.schemas import (
    EspDeviceOut,
    EspDevicePatch,
    EspHelloIn,
    EspHelloOut,
    EspPunchIn,
    EspPunchOut,
    EspTerminalSettingsIn,
    EspTerminalSettingsOut,
)
from app.terminal_punch import apply_booking, auto_kind_for, find_user_by_badge

log = logging.getLogger(__name__)

router = APIRouter(prefix="/terminals/esp", tags=["esp-terminal"])
hr_router = APIRouter(prefix="/hr/esp-terminal", tags=["esp-terminal"])


def _secret(db: Session) -> str:
    return effective_secret(db)


def _secret_ok(db: Session, provided: str) -> bool:
    expected = _secret(db)
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


def _require_terminal(request: Request, db: Session) -> None:
    if not _secret(db):
        raise HTTPException(503, "ESP-Terminal nicht konfiguriert")
    if not _secret_ok(db, _provided_key(request)):
        raise HTTPException(401, "Falsches Secret")


def _client_ip(request: Request) -> str:
    forwarded = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    if forwarded:
        return forwarded[:64]
    if request.client:
        return (request.client.host or "")[:64]
    return ""


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


def _device_out(row: EspTerminal) -> EspDeviceOut:
    return EspDeviceOut(
        id=row.id,
        device_id=row.device_id,
        name=row.name,
        firmware=row.firmware,
        last_ssid=row.last_ssid,
        last_ip=row.last_ip,
        last_seen_at=row.last_seen_at,
        wifi_ssid=row.wifi_ssid,
        wifi_pass_set=bool((row.wifi_pass or "").strip()),
    )


def _hello_payload(db: Session, device: EspTerminal) -> EspHelloOut:
    row = org_row(db)
    wanted = int(row.esp_firmware_version or 0)
    bin_path = firmware_path()
    offer = wanted > 0 and bin_path.is_file() and wanted > int(device.firmware or 0)
    wifi_ssid = (device.wifi_ssid or "").strip()
    wifi_pass = (device.wifi_pass or "").strip() if wifi_ssid else ""
    return EspHelloOut(
        name=device_label(device),
        fw=wanted,
        firmware_url=firmware_url() if offer else "",
        wifi_ssid=wifi_ssid,
        wifi_pass=wifi_pass,
    )


@router.post("/punch", response_model=EspPunchOut)
def punch(payload: EspPunchIn, request: Request, db: Session = Depends(get_db)):
    _require_terminal(request, db)

    badge = (payload.badge or "").strip()
    user = find_user_by_badge(db, badge)
    if not user:
        return EspPunchOut(ok=False, line1="Unbekannt", line2="Ausweis")

    device = touch_device(
        db,
        payload.device_id,
        firmware=payload.fw or None,
        ssid=payload.ssid or None,
        ip=_client_ip(request),
    )
    place = device_label(device, payload.device_id)
    kind = auto_kind_for(db, user)
    result = apply_booking(
        db,
        badge=badge,
        kind=kind,
        timestamp=None,
        event_id=f"esp-{payload.event_id.strip()}"[:64],
        source="esp",
        note=place,
        persist=True,
        device_id=device.device_id if device else normalize_device_id(payload.device_id) or None,
        terminal_name=place,
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


@router.post("/hello", response_model=EspHelloOut)
def hello(payload: EspHelloIn, request: Request, db: Session = Depends(get_db)):
    _require_terminal(request, db)
    device = touch_device(
        db,
        payload.device_id,
        firmware=payload.fw,
        ssid=payload.ssid or None,
        ip=(payload.ip or "").strip() or _client_ip(request),
    )
    if device is None:
        raise HTTPException(400, "Geräte-ID fehlt")
    return _hello_payload(db, device)


@router.get("/firmware.bin")
def download_firmware(request: Request, db: Session = Depends(get_db)):
    _require_terminal(request, db)
    path = firmware_path()
    if not path.is_file():
        raise HTTPException(404, "Keine Firmware hinterlegt")
    return FileResponse(path, media_type="application/octet-stream", filename="firmware.bin")


def _admin(request: Request, db: Session) -> User:
    return require_admin(current_user(request, db))


def _settings_out(db: Session) -> EspTerminalSettingsOut:
    row = org_row(db)
    devices = list(db.scalars(select(EspTerminal).order_by(EspTerminal.id)))
    secret = _secret(db)
    return EspTerminalSettingsOut(
        secret=secret,
        secret_configured=bool(secret),
        secret_source=secret_source(db),
        ok_line1=getattr(row, "esp_ok_line1", None) or DEFAULT_OK_LINE1,
        ok_line2=getattr(row, "esp_ok_line2", None) or DEFAULT_OK_LINE2,
        line_max=LINE_MAX,
        firmware_version=int(row.esp_firmware_version or 0),
        firmware_uploaded=firmware_path().is_file(),
        devices=[_device_out(d) for d in devices],
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
    if "secret" in dumped and dumped["secret"] is not None:
        value = dumped["secret"].strip()
        row.esp_terminal_secret = value
    audit = {k: v for k, v in dumped.items() if k != "secret"}
    if "secret" in dumped:
        audit["secret"] = "gesetzt" if (dumped["secret"] or "").strip() else "geleert"
    db.add(
        AuditEvent(
            actor_id=actor.id,
            action="esp.settings",
            entity_type="org",
            entity_id="1",
            payload=json.dumps(audit),
        )
    )
    db.commit()
    return _settings_out(db)


@hr_router.post("/secret", response_model=EspTerminalSettingsOut)
def generate_esp_secret(request: Request, db: Session = Depends(get_db)):
    actor = _admin(request, db)
    row = org_row(db)
    row.esp_terminal_secret = secrets.token_urlsafe(32)
    db.add(
        AuditEvent(
            actor_id=actor.id,
            action="esp.secret",
            entity_type="org",
            entity_id="1",
            payload="neu",
        )
    )
    db.commit()
    return _settings_out(db)


@hr_router.patch("/devices/{device_pk}", response_model=EspDeviceOut)
def patch_esp_device(device_pk: int, payload: EspDevicePatch, request: Request, db: Session = Depends(get_db)):
    actor = _admin(request, db)
    row = db.get(EspTerminal, device_pk)
    if row is None:
        raise HTTPException(404, "Gerät nicht gefunden")
    dumped = payload.model_dump(exclude_unset=True)
    if "name" in dumped and dumped["name"] is not None:
        row.name = dumped["name"].strip()[:120]
    if dumped.get("clear_wifi"):
        row.wifi_ssid = ""
        row.wifi_pass = ""
    else:
        if "wifi_ssid" in dumped and dumped["wifi_ssid"] is not None:
            row.wifi_ssid = dumped["wifi_ssid"].strip()[:80]
        if "wifi_pass" in dumped and dumped["wifi_pass"] is not None:
            row.wifi_pass = dumped["wifi_pass"]
    db.add(
        AuditEvent(
            actor_id=actor.id,
            action="esp.device",
            entity_type="esp_terminal",
            entity_id=str(row.id),
            payload=json.dumps({"name": row.name, "wifi": bool(row.wifi_ssid)}),
        )
    )
    db.commit()
    db.refresh(row)
    return _device_out(row)


@hr_router.post("/firmware", response_model=EspTerminalSettingsOut)
async def upload_esp_firmware(
    request: Request,
    db: Session = Depends(get_db),
    file: UploadFile = File(...),
    version: int = Form(...),
):
    actor = _admin(request, db)
    if version < 1:
        raise HTTPException(400, "Firmware-Version muss mindestens 1 sein")
    raw = await file.read()
    if not raw:
        raise HTTPException(400, "Leere Datei")
    if len(raw) > FIRMWARE_MAX_BYTES:
        raise HTTPException(400, "Firmware ist größer als 4 MB")
    if raw[0] != 0xE9:
        raise HTTPException(400, "Keine ESP32-Firmware (.bin, Magic 0xE9)")
    path = firmware_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    row = org_row(db)
    row.esp_firmware_version = version
    db.add(
        AuditEvent(
            actor_id=actor.id,
            action="esp.firmware",
            entity_type="org",
            entity_id="1",
            payload=json.dumps({"version": version, "bytes": len(raw)}),
        )
    )
    db.commit()
    return _settings_out(db)
