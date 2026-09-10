from __future__ import annotations

import json
import re

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import current_user, require_admin
from app.database import get_db
from app.dfcom import find_library_path, library_available
from app.dfcom_poll import org_row, poll_once, push_lists_once
from app.models import AuditEvent, TerminalDevice, User
from app.schemas import DfcomSettingsIn, DfcomSettingsOut, TerminalDeviceIn, TerminalDeviceOut, TerminalDevicePatch

router = APIRouter(prefix="/hr/dfcom", tags=["dfcom"])

_HOST = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.-]*$")


def _admin(request: Request, db: Session) -> User:
    return require_admin(current_user(request, db))


def _last_poll(row) -> dict | None:
    raw = row.dfcom_last_poll or ""
    if not raw.strip():
        return None
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _payload(db: Session) -> DfcomSettingsOut:
    row = org_row(db)
    path = find_library_path()
    terminals = list(db.scalars(select(TerminalDevice).order_by(TerminalDevice.id)))
    return DfcomSettingsOut(
        library_ok=library_available(),
        library_path=str(path) if path else None,
        poll_enabled=bool(row.dfcom_poll_enabled),
        poll_dry_run=bool(row.dfcom_poll_dry_run),
        poll_interval_sec=int(row.dfcom_poll_interval_sec or 20),
        sync_lists=bool(getattr(row, "dfcom_sync_lists", True)),
        last_poll=_last_poll(row),
        terminals=[TerminalDeviceOut.model_validate(item) for item in terminals],
    )


def _clean_host(host: str) -> str:
    value = (host or "").strip()
    if not value or not _HOST.match(value) or "://" in value:
        raise HTTPException(400, "Host ist ungültig (nur Name oder IP, ohne http://).")
    return value


@router.get("", response_model=DfcomSettingsOut)
def get_dfcom(request: Request, db: Session = Depends(get_db)):
    _admin(request, db)
    return _payload(db)


@router.patch("", response_model=DfcomSettingsOut)
def patch_dfcom(payload: DfcomSettingsIn, request: Request, db: Session = Depends(get_db)):
    actor = _admin(request, db)
    row = org_row(db)
    dumped = payload.model_dump(exclude_unset=True)
    if "poll_enabled" in dumped:
        row.dfcom_poll_enabled = bool(dumped["poll_enabled"])
    if "poll_dry_run" in dumped:
        row.dfcom_poll_dry_run = bool(dumped["poll_dry_run"])
    if "poll_interval_sec" in dumped and dumped["poll_interval_sec"] is not None:
        row.dfcom_poll_interval_sec = int(dumped["poll_interval_sec"])
    if "sync_lists" in dumped:
        row.dfcom_sync_lists = bool(dumped["sync_lists"])
    db.add(
        AuditEvent(
            actor_id=actor.id,
            action="dfcom.settings",
            entity_type="org",
            entity_id="1",
            payload=json.dumps(dumped),
        )
    )
    db.commit()
    return _payload(db)


@router.post("/poll")
def run_poll(request: Request, db: Session = Depends(get_db)):
    _admin(request, db)
    report = poll_once(db, force=True)
    return asdict(report)


@router.post("/lists")
def run_lists(request: Request, db: Session = Depends(get_db)):
    _admin(request, db)
    report = push_lists_once(db)
    return asdict(report)


@router.post("/terminals", response_model=TerminalDeviceOut)
def create_terminal(payload: TerminalDeviceIn, request: Request, db: Session = Depends(get_db)):
    actor = _admin(request, db)
    device = TerminalDevice(
        name=(payload.name or "Terminal").strip() or "Terminal",
        host=_clean_host(payload.host),
        port=int(payload.port),
        device_address=int(payload.device_address),
        enabled=bool(payload.enabled),
    )
    db.add(device)
    db.add(
        AuditEvent(
            actor_id=actor.id,
            action="dfcom.terminal.create",
            entity_type="terminal",
            payload=device.host,
        )
    )
    db.commit()
    db.refresh(device)
    return device


@router.patch("/terminals/{terminal_id}", response_model=TerminalDeviceOut)
def patch_terminal(terminal_id: int, payload: TerminalDevicePatch, request: Request, db: Session = Depends(get_db)):
    actor = _admin(request, db)
    device = db.get(TerminalDevice, terminal_id)
    if not device:
        raise HTTPException(404, "Terminal nicht gefunden")
    dumped = payload.model_dump(exclude_unset=True)
    if "name" in dumped and dumped["name"] is not None:
        device.name = dumped["name"].strip() or device.name
    if "host" in dumped and dumped["host"] is not None:
        device.host = _clean_host(dumped["host"])
    if "port" in dumped and dumped["port"] is not None:
        device.port = int(dumped["port"])
    if "device_address" in dumped and dumped["device_address"] is not None:
        device.device_address = int(dumped["device_address"])
    if "enabled" in dumped and dumped["enabled"] is not None:
        device.enabled = bool(dumped["enabled"])
    db.add(
        AuditEvent(
            actor_id=actor.id,
            action="dfcom.terminal.patch",
            entity_type="terminal",
            entity_id=str(device.id),
            payload=json.dumps(dumped),
        )
    )
    db.commit()
    db.refresh(device)
    return device


@router.delete("/terminals/{terminal_id}")
def delete_terminal(terminal_id: int, request: Request, db: Session = Depends(get_db)):
    actor = _admin(request, db)
    device = db.get(TerminalDevice, terminal_id)
    if not device:
        raise HTTPException(404, "Terminal nicht gefunden")
    db.delete(device)
    db.add(
        AuditEvent(
            actor_id=actor.id,
            action="dfcom.terminal.delete",
            entity_type="terminal",
            entity_id=str(terminal_id),
        )
    )
    db.commit()
    return {"ok": True}
