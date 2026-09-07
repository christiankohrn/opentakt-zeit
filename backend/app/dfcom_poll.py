from __future__ import annotations

import hashlib
import json
import logging
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import as_local, now_utc
from app.config import get_config
from app.datafox import parse_badge, parse_kind, parse_timestamp
from app.database import SessionLocal
from app.dfcom import DfcomClient, DfcomError, library_available, make_client, parse_record, record_params
from app.dfcom_lists import find_personal_list_id, packed_personal, personal_rows
from app.models import OrgSettings, TerminalDevice
from app.terminal_punch import apply_booking

log = logging.getLogger(__name__)

MAX_RECORDS_PER_DEVICE = 200
CONNECT_TIMEOUT_MS = 4000
BOOKING_TABLES = {"", "booking", "stempelung"}
_poll_lock = threading.Lock()
_stop = threading.Event()
_thread: threading.Thread | None = None


@dataclass
class DevicePollResult:
    terminal_id: int
    name: str
    host: str
    ok: bool
    error: str = ""
    read: int = 0
    stored: int = 0
    preview: int = 0
    quit: int = 0
    skipped: int = 0
    lists_written: int = 0
    samples: list[str] = field(default_factory=list)


@dataclass
class PollReport:
    at: str
    dry_run: bool
    library: bool
    busy: bool = False
    error: str = ""
    devices: list[DevicePollResult] = field(default_factory=list)


def org_row(db: Session) -> OrgSettings:
    row = db.get(OrgSettings, 1)
    if row is None:
        row = OrgSettings(id=1)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def event_id_for(terminal_id: int, raw: bytes) -> str:
    digest = hashlib.sha256(raw).hexdigest()[:24]
    return f"dfp-{terminal_id}-{digest}"[:64]


def _sample(result: DevicePollResult, text: str) -> None:
    if len(result.samples) < 5:
        result.samples.append(text[:160])


def _write_personal_list(
    db: Session,
    client: DfcomClient,
    device: TerminalDevice,
    result: DevicePollResult,
    *,
    force: bool,
) -> None:
    schemas = client.load_list_schemas(int(device.device_address))
    if not schemas:
        return
    list_id = find_personal_list_id(schemas)
    if list_id is None:
        _sample(result, "Liste PERSONAL fehlt")
        return
    schema = schemas[list_id]
    blob, row_count, row_size, digest = packed_personal(schema, personal_rows(db))
    if not force and device.last_list_hash == digest:
        _sample(result, "Personalliste unverändert")
        return
    client.write_list(int(device.device_address), list_id, blob, row_count, row_size)
    device.last_list_hash = digest
    result.lists_written += 1
    _sample(result, f"Personalliste geschrieben ({row_count})")


def _poll_device(
    db: Session,
    client: DfcomClient,
    device: TerminalDevice,
    *,
    dry_run: bool,
    now: datetime,
    sync_lists: bool = False,
    force_lists: bool = False,
    read_records: bool = True,
    set_clock: bool = True,
) -> DevicePollResult:
    result = DevicePollResult(terminal_id=device.id, name=device.name, host=device.host, ok=False)
    try:
        client.open(device.host, int(device.port), CONNECT_TIMEOUT_MS)
        if set_clock and not dry_run:
            try:
                client.set_time(int(device.device_address), as_local(now))
            except DfcomError as exc:
                log.warning("Uhrzeit %s: %s", device.host, exc)
        if read_records:
            schemas = client.load_schemas(int(device.device_address))
            for _ in range(MAX_RECORDS_PER_DEVICE):
                status, raw = client.read_record(int(device.device_address))
                if status == 0 or not raw:
                    break
                result.read += 1
                parsed = parse_record(raw, schemas)
                params = record_params(parsed)
                table = (parsed.table or "").strip().lower()
                badge = parse_badge(params)
                kind = parse_kind(params)
                booking_table = table in BOOKING_TABLES
                if booking_table and (badge or kind):
                    booking = apply_booking(
                        db,
                        badge=badge,
                        kind=kind,
                        timestamp=parse_timestamp(params),
                        event_id=event_id_for(device.id, raw),
                        source="terminal",
                        note=f"poll {device.host}",
                        persist=not dry_run,
                    )
                    if booking.outcome == "stored":
                        result.stored += 1
                    elif booking.outcome == "preview":
                        result.preview += 1
                    else:
                        result.skipped += 1
                    _sample(result, booking.detail)
                else:
                    result.skipped += 1
                    _sample(result, f"Tabelle {parsed.table or parsed.table_id} ignoriert")
                if dry_run:
                    break
                client.quit_record(int(device.device_address))
                result.quit += 1
        result.ok = True
        result.error = ""
        if not dry_run and (sync_lists or force_lists):
            try:
                _write_personal_list(db, client, device, result, force=force_lists)
            except DfcomError as exc:
                log.warning("Personalliste %s: %s", device.host, exc)
                _sample(result, f"Personalliste: {exc}")
                result.error = f"Personalliste: {exc}"
                if not read_records:
                    result.ok = False
    except DfcomError as exc:
        result.error = str(exc)
        log.warning("Polling %s: %s", device.host, exc)
    except Exception as exc:
        result.error = str(exc)
        log.exception("Polling %s", device.host)
    finally:
        try:
            client.close()
        except Exception:
            pass
    summary = (
        f"{'Testbetrieb, nicht bestätigt. ' if dry_run else ''}"
        f"{result.read} gelesen"
        + (f", {result.preview} Vorschau" if result.preview else "")
        + (f", {result.stored} gespeichert" if result.stored else "")
        + (f", {result.quit} bestätigt" if result.quit else "")
        + (f", {result.lists_written} Liste" if result.lists_written else "")
        + (f" — {result.error}" if result.error else "")
    )
    if result.samples:
        summary = f"{summary}. {result.samples[0]}"
    device.last_poll_at = now
    device.last_ok_at = now if result.ok else device.last_ok_at
    device.last_error = result.error
    device.last_summary = summary[:500]
    db.commit()
    return result


def _run_on_devices(
    db: Session,
    *,
    client: DfcomClient | None,
    force: bool,
    require_enabled: bool,
    dry_run_error: str | None,
    read_records: bool,
    sync_lists: bool,
    force_lists: bool,
    set_clock: bool,
) -> PollReport:
    row = org_row(db)
    now = now_utc()
    report = PollReport(
        at=now.isoformat(),
        dry_run=bool(row.dfcom_poll_dry_run),
        library=True,
    )
    if require_enabled and not force and not row.dfcom_poll_enabled:
        report.error = "Polling ist ausgeschaltet."
        report.library = library_available() or client is not None
        return report
    if dry_run_error and row.dfcom_poll_dry_run:
        report.error = dry_run_error
        report.library = library_available() or client is not None
        return report
    if not _poll_lock.acquire(blocking=False):
        report.busy = True
        report.error = "Polling läuft bereits."
        return report
    try:
        handle = client if client is not None else make_client()
        if handle is None:
            report.library = False
            report.error = "libDFCom.so fehlt. deploy/install-dfcom.sh auf dem Server ausführen."
            row.dfcom_last_poll = json.dumps(asdict(report), ensure_ascii=False)
            db.commit()
            return report
        devices = list(db.scalars(select(TerminalDevice).where(TerminalDevice.enabled.is_(True)).order_by(TerminalDevice.id)))
        if not devices:
            report.error = "Kein aktives Terminal eingetragen."
        for device in devices:
            report.devices.append(
                _poll_device(
                    db,
                    handle,
                    device,
                    dry_run=bool(row.dfcom_poll_dry_run),
                    now=now,
                    sync_lists=sync_lists,
                    force_lists=force_lists,
                    read_records=read_records,
                    set_clock=set_clock,
                )
            )
        row.dfcom_last_poll = json.dumps(asdict(report), ensure_ascii=False)
        db.commit()
        return report
    finally:
        _poll_lock.release()


def poll_once(db: Session, *, client: DfcomClient | None = None, force: bool = False) -> PollReport:
    row = org_row(db)
    return _run_on_devices(
        db,
        client=client,
        force=force,
        require_enabled=True,
        dry_run_error=None,
        read_records=True,
        sync_lists=bool(row.dfcom_sync_lists) and not row.dfcom_poll_dry_run,
        force_lists=False,
        set_clock=True,
    )


def push_lists_once(db: Session, *, client: DfcomClient | None = None) -> PollReport:
    return _run_on_devices(
        db,
        client=client,
        force=True,
        require_enabled=False,
        dry_run_error="Testbetrieb: Listen werden nicht geschrieben.",
        read_records=False,
        sync_lists=False,
        force_lists=True,
        set_clock=False,
    )


def _interval_sec(db: Session) -> int:
    row = org_row(db)
    return max(10, min(300, int(row.dfcom_poll_interval_sec or 20)))


def _run_loop() -> None:
    while True:
        db = SessionLocal()
        try:
            row = org_row(db)
            interval = _interval_sec(db)
            if row.dfcom_poll_enabled:
                poll_once(db)
        except Exception:
            log.exception("dfcom poll loop")
            interval = 20
        finally:
            db.close()
        if _stop.wait(interval):
            break


def start_background() -> None:
    global _thread
    if get_config().environment in {"test", "testing"}:
        return
    if _thread is not None and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_run_loop, name="dfcom-poll", daemon=True)
    _thread.start()


def stop_background() -> None:
    _stop.set()
