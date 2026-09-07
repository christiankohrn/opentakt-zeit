from __future__ import annotations

import ctypes
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol
from zoneinfo import ZoneInfo

from app.config import get_config

log = logging.getLogger(__name__)

TCP_CONNECTION_TYPE = 3
RECORD_BUFFER = 300
MAX_FIELD_NAME = 20

# Datafox field types (DFCDatBFeld).
TYPE_UINT32 = 1
TYPE_DATETIME = 2
TYPE_NUM_STRING = 3
TYPE_LATIN1 = 4
TYPE_DATE = 5
TYPE_TIME = 6


class DfcomError(RuntimeError):
    pass


@dataclass(frozen=True)
class RecordField:
    name: str
    type: int
    size: int


@dataclass(frozen=True)
class RecordSchema:
    table_id: int
    name: str
    fields: tuple[RecordField, ...]


@dataclass
class ParsedRecord:
    table: str
    fields: dict[str, str]
    raw: bytes
    table_id: int


class DfcomClient(Protocol):
    def open(self, host: str, port: int, timeout_ms: int) -> None: ...
    def close(self) -> None: ...
    def load_schemas(self, device_address: int) -> dict[int, RecordSchema]: ...
    def load_list_schemas(self, device_address: int) -> dict[int, RecordSchema]: ...
    def read_record(self, device_address: int) -> tuple[int, bytes]: ...
    def quit_record(self, device_address: int) -> int: ...
    def set_time(self, device_address: int, when: datetime) -> None: ...
    def write_list(self, device_address: int, list_id: int, blob: bytes, row_count: int, row_size: int) -> None: ...


def library_candidates() -> list[Path]:
    paths: list[Path] = []
    cfg_path = (get_config().dfcom_lib or "").strip()
    env_path = (os.environ.get("DFCOM_LIB") or "").strip()
    for raw in (env_path, cfg_path):
        if raw:
            paths.append(Path(raw))
    repo = Path(__file__).resolve().parents[2]
    paths.extend(
        [
            Path("/opt/zeiterfassung/lib/libDFCom.so"),
            repo / "lib" / "libDFCom.so",
            Path.cwd() / "lib" / "libDFCom.so",
        ]
    )
    seen: set[Path] = set()
    out: list[Path] = []
    for path in paths:
        resolved = path if path.is_absolute() else path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        out.append(resolved)
    return out


def find_library_path() -> Path | None:
    for path in library_candidates():
        if path.is_file():
            return path
    return None


def encode_df_datetime(dt: datetime) -> bytes:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("Europe/Berlin"))
    local = dt.astimezone(ZoneInfo("Europe/Berlin"))
    return bytes(
        [
            local.year // 100,
            local.year % 100,
            local.month,
            local.day,
            local.hour,
            local.minute,
            local.second,
        ]
    )


def decode_df_datetime(raw: bytes) -> datetime:
    if len(raw) < 7:
        raise ValueError("datetime field too short")
    century, year, month, day, hour, minute, second = raw[:7]
    return datetime(century * 100 + year, month, day, hour, minute, second, tzinfo=ZoneInfo("Europe/Berlin"))


def decode_field(ftype: int, size: int, data: bytes) -> str:
    chunk = data[:size] if size else data
    if ftype == TYPE_UINT32:
        return str(int.from_bytes(chunk[:4].ljust(4, b"\x00"), "little"))
    if ftype == TYPE_DATETIME:
        try:
            return decode_df_datetime(chunk).isoformat()
        except ValueError:
            return ""
    if ftype == TYPE_DATE and len(chunk) >= 4:
        try:
            return datetime(chunk[0] * 100 + chunk[1], chunk[2], chunk[3], tzinfo=ZoneInfo("Europe/Berlin")).date().isoformat()
        except ValueError:
            return ""
    if ftype == TYPE_TIME and len(chunk) >= 3:
        return f"{chunk[0]:02d}:{chunk[1]:02d}:{chunk[2]:02d}"
    text = chunk.split(b"\x00", 1)[0].decode("latin-1", errors="replace").strip()
    return text


def parse_record(raw: bytes, schemas: dict[int, RecordSchema]) -> ParsedRecord:
    if not raw:
        raise ValueError("empty record")
    table_id = raw[0]
    schema = schemas.get(table_id)
    if schema is None:
        return ParsedRecord(table="", fields={}, raw=raw, table_id=table_id)
    offset = 1
    fields: dict[str, str] = {}
    for item in schema.fields:
        end = offset + item.size
        chunk = raw[offset:end]
        if len(chunk) < item.size:
            break
        fields[item.name] = decode_field(item.type, item.size, chunk)
        offset = end
    return ParsedRecord(table=schema.name, fields=fields, raw=raw, table_id=table_id)


def record_params(parsed: ParsedRecord) -> dict[str, str]:
    params: dict[str, str] = {}
    for key, value in parsed.fields.items():
        params[key] = value
        params[key.lower()] = value
        params[f"df_col_{key.lower()}"] = value
    if parsed.table:
        params["df_table"] = parsed.table
        params["table"] = parsed.table
    return params


def pack_record(schema: RecordSchema, values: dict[str, str | datetime | int]) -> bytes:
    """Build a binary record for tests (first byte = table id)."""
    parts = [bytes([schema.table_id])]
    for item in schema.fields:
        raw = values.get(item.name, values.get(item.name.lower(), ""))
        if item.type == TYPE_UINT32:
            number = int(raw) if not isinstance(raw, datetime) else 0
            parts.append(int(number).to_bytes(item.size, "little"))
        elif item.type == TYPE_DATETIME:
            if isinstance(raw, datetime):
                dt = raw
            else:
                dt = datetime.fromisoformat(str(raw))
            blob = encode_df_datetime(dt)
            parts.append(blob.ljust(item.size, b"\x00")[: item.size])
        else:
            text = "" if isinstance(raw, datetime) else str(raw)
            parts.append(text.encode("latin-1", errors="replace").ljust(item.size, b"\x00")[: item.size])
    return b"".join(parts)


def booking_schema(*, table_id: int = 0) -> RecordSchema:
    return RecordSchema(
        table_id=table_id,
        name="Booking",
        fields=(
            RecordField("badge", TYPE_LATIN1, 16),
            RecordField("fn", TYPE_LATIN1, 4),
            RecordField("timestamp", TYPE_DATETIME, 7),
        ),
    )


def stempelung_schema(*, table_id: int = 0) -> RecordSchema:
    return RecordSchema(
        table_id=table_id,
        name="Stempelung",
        fields=(
            RecordField("Karte", TYPE_LATIN1, 21),
            RecordField("Auftrag", TYPE_LATIN1, 21),
            RecordField("Tätigkeit", TYPE_LATIN1, 21),
            RecordField("Datum/Zeit", TYPE_DATETIME, 7),
            RecordField("Kennzeichen", TYPE_LATIN1, 2),
            RecordField("Paket", TYPE_LATIN1, 21),
        ),
    )


def personal_list_schema(*, list_id: int = 0) -> RecordSchema:
    return RecordSchema(
        table_id=list_id,
        name="PERSONAL",
        fields=(
            RecordField("KARTE", TYPE_LATIN1, 16),
            RecordField("UKO", TYPE_LATIN1, 16),
            RecordField("ZKO", TYPE_LATIN1, 16),
            RecordField("NAME", TYPE_LATIN1, 21),
            RecordField("KENNZEICHEN", TYPE_LATIN1, 2),
            RecordField("KARTE2", TYPE_LATIN1, 11),
        ),
    )


def pack_list_field(text: str, size: int) -> bytes:
    n = max(0, int(size))
    if n == 0:
        return b""
    payload = (text or "").encode("latin-1", errors="replace")[: max(0, n - 1)]
    return payload.ljust(n, b"\x00")[:n]


def list_row_size(schema: RecordSchema) -> int:
    return sum(item.size for item in schema.fields)


def pack_list_row(schema: RecordSchema, values: dict[str, str]) -> bytes:
    lower = {k.lower(): v for k, v in values.items()}
    parts: list[bytes] = []
    for item in schema.fields:
        text = values.get(item.name, lower.get(item.name.lower(), ""))
        parts.append(pack_list_field("" if text is None else str(text), item.size))
    return b"".join(parts)


def pack_list_rows(schema: RecordSchema, rows: list[dict[str, str]]) -> bytes:
    return b"".join(pack_list_row(schema, row) for row in rows)


class FakeDfcom:
    """In-memory DFCom stand-in for tests (no vendor library)."""

    def __init__(self, schemas: dict[int, RecordSchema] | None = None):
        self.schemas = schemas or {0: booking_schema()}
        self.list_schemas: dict[int, RecordSchema] = {}
        self.records: list[bytes] = []
        self.index = 0
        self.quit_count = 0
        self.time_set: list[datetime] = []
        self.opened: list[tuple[str, int]] = []
        self.fail_open = False
        self.closed = 0
        self.written_lists: list[dict[str, object]] = []

    def open(self, host: str, port: int, timeout_ms: int) -> None:
        if self.fail_open:
            raise DfcomError("Verbindung fehlgeschlagen")
        self.opened.append((host, port))

    def close(self) -> None:
        self.closed += 1

    def load_schemas(self, device_address: int) -> dict[int, RecordSchema]:
        return self.schemas

    def load_list_schemas(self, device_address: int) -> dict[int, RecordSchema]:
        return self.list_schemas

    def read_record(self, device_address: int) -> tuple[int, bytes]:
        if self.index >= len(self.records):
            return 0, b""
        status = 3 if self.quit_count == self.index else 4
        return status, self.records[self.index]

    def quit_record(self, device_address: int) -> int:
        if self.index >= len(self.records):
            return 0
        self.index += 1
        self.quit_count += 1
        return 3

    def set_time(self, device_address: int, when: datetime) -> None:
        self.time_set.append(when)

    def write_list(self, device_address: int, list_id: int, blob: bytes, row_count: int, row_size: int) -> None:
        self.written_lists.append(
            {
                "address": device_address,
                "list_id": list_id,
                "blob": blob,
                "row_count": row_count,
                "row_size": row_size,
            }
        )


def _bind(lib: ctypes.CDLL) -> None:
    lib.DFCComOpenIV.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_int]
    lib.DFCComOpenIV.restype = ctypes.c_int
    lib.DFCComClose.argtypes = [ctypes.c_int]
    lib.DFCComClose.restype = None
    lib.DFCLoadDatensatzbeschreibung.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_int)]
    lib.DFCLoadDatensatzbeschreibung.restype = ctypes.c_int
    lib.DFCDatBCnt.argtypes = [ctypes.c_int]
    lib.DFCDatBCnt.restype = ctypes.c_int
    lib.DFCDatBDatensatz.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_char_p, ctypes.POINTER(ctypes.c_int)]
    lib.DFCDatBDatensatz.restype = ctypes.c_int
    lib.DFCDatBFeld.argtypes = [
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.POINTER(ctypes.c_int),
        ctypes.POINTER(ctypes.c_int),
    ]
    lib.DFCDatBFeld.restype = ctypes.c_int
    lib.DFCReadRecord.argtypes = [
        ctypes.c_int,
        ctypes.c_int,
        ctypes.POINTER(ctypes.c_ubyte),
        ctypes.POINTER(ctypes.c_int),
        ctypes.POINTER(ctypes.c_int),
    ]
    lib.DFCReadRecord.restype = ctypes.c_int
    lib.DFCQuitRecord.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_int)]
    lib.DFCQuitRecord.restype = ctypes.c_int
    lib.DFCComSetTime.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_ubyte)]
    lib.DFCComSetTime.restype = ctypes.c_int
    lib.DFCGetErrorText.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
    lib.DFCGetErrorText.restype = None
    _bind_optional(
        lib,
        "DFCLoadListenbeschreibung",
        [ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_int)],
        ctypes.c_int,
    )
    _bind_optional(lib, "DFCListBCnt", [ctypes.c_int], ctypes.c_int)
    _bind_optional(
        lib,
        "DFCListBDatensatz",
        [ctypes.c_int, ctypes.c_int, ctypes.c_char_p, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int)],
        ctypes.c_int,
    )
    _bind_optional(
        lib,
        "DFCListBFeld",
        [
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_int),
        ],
        ctypes.c_int,
    )
    _bind_optional(lib, "DFCClrListenBuffer", [ctypes.c_int], ctypes.c_int)
    _bind_optional(
        lib,
        "DFCMakeListe",
        [ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_ubyte), ctypes.c_int],
        ctypes.c_int,
    )
    _bind_optional(
        lib,
        "DFCLoadListen",
        [ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_int)],
        ctypes.c_int,
    )


def _bind_optional(lib: ctypes.CDLL, name: str, argtypes: list, restype) -> None:
    fn = getattr(lib, name, None)
    if fn is None:
        return
    fn.argtypes = argtypes
    fn.restype = restype


class NativeDfcom:
    def __init__(self, lib: ctypes.CDLL, connection_id: int = 1):
        self._lib = lib
        self._conn = connection_id
        self._open = False

    def _err(self, code: int) -> str:
        buf = ctypes.create_string_buffer(200)
        try:
            self._lib.DFCGetErrorText(self._conn, int(code), 0, buf, 199)
            text = buf.value.decode("latin-1", errors="replace").strip()
        except Exception:
            text = ""
        return text or f"DFCom-Fehler {code}"

    def open(self, host: str, port: int, timeout_ms: int) -> None:
        if self._open:
            self.close()
        ok = self._lib.DFCComOpenIV(self._conn, 0, TCP_CONNECTION_TYPE, host.encode("ascii", "ignore"), int(port), int(timeout_ms))
        if not ok:
            raise DfcomError(f"TCP zu {host}:{port} fehlgeschlagen")
        self._open = True

    def close(self) -> None:
        if not self._open:
            return
        try:
            self._lib.DFCComClose(self._conn)
        finally:
            self._open = False

    def load_schemas(self, device_address: int) -> dict[int, RecordSchema]:
        err = ctypes.c_int(0)
        if not self._lib.DFCLoadDatensatzbeschreibung(self._conn, int(device_address), ctypes.byref(err)):
            raise DfcomError(self._err(err.value) or "Datensatzbeschreibung fehlt")
        count = int(self._lib.DFCDatBCnt(self._conn))
        schemas: dict[int, RecordSchema] = {}
        for table_id in range(max(count, 0)):
            name_buf = ctypes.create_string_buffer(MAX_FIELD_NAME)
            field_count = ctypes.c_int(0)
            if not self._lib.DFCDatBDatensatz(self._conn, table_id, name_buf, ctypes.byref(field_count)):
                continue
            fields: list[RecordField] = []
            for field_i in range(int(field_count.value)):
                fname = ctypes.create_string_buffer(MAX_FIELD_NAME)
                ftype = ctypes.c_int(0)
                fsize = ctypes.c_int(0)
                if not self._lib.DFCDatBFeld(self._conn, table_id, field_i, fname, ctypes.byref(ftype), ctypes.byref(fsize)):
                    continue
                fields.append(
                    RecordField(
                        name=fname.value.decode("latin-1", errors="replace").strip() or f"f{field_i}",
                        type=int(ftype.value),
                        size=int(fsize.value),
                    )
                )
            schemas[table_id] = RecordSchema(
                table_id=table_id,
                name=name_buf.value.decode("latin-1", errors="replace").strip(),
                fields=tuple(fields),
            )
        return schemas

    def read_record(self, device_address: int) -> tuple[int, bytes]:
        buf = (ctypes.c_ubyte * RECORD_BUFFER)()
        size = ctypes.c_int(RECORD_BUFFER)
        err = ctypes.c_int(0)
        status = int(self._lib.DFCReadRecord(self._conn, int(device_address), buf, ctypes.byref(size), ctypes.byref(err)))
        if status < 0:
            raise DfcomError(self._err(err.value) or "Lesen fehlgeschlagen")
        n = max(0, min(int(size.value), RECORD_BUFFER))
        return status, bytes(buf[:n])

    def quit_record(self, device_address: int) -> int:
        err = ctypes.c_int(0)
        status = int(self._lib.DFCQuitRecord(self._conn, int(device_address), ctypes.byref(err)))
        if status < 0:
            raise DfcomError(self._err(err.value) or "Bestätigen fehlgeschlagen")
        return status

    def set_time(self, device_address: int, when: datetime) -> None:
        blob = encode_df_datetime(when)
        arr = (ctypes.c_ubyte * 7)(*blob)
        if not self._lib.DFCComSetTime(self._conn, int(device_address), arr):
            raise DfcomError("Uhrzeit setzen fehlgeschlagen")

    def load_list_schemas(self, device_address: int) -> dict[int, RecordSchema]:
        load_fn = getattr(self._lib, "DFCLoadListenbeschreibung", None)
        count_fn = getattr(self._lib, "DFCListBCnt", None)
        rec_fn = getattr(self._lib, "DFCListBDatensatz", None)
        field_fn = getattr(self._lib, "DFCListBFeld", None)
        if not all((load_fn, count_fn, rec_fn, field_fn)):
            return {}
        err = ctypes.c_int(0)
        if not load_fn(self._conn, int(device_address), ctypes.byref(err)):
            log.warning("Listenbeschreibung %s", self._err(err.value))
            return {}
        count = int(count_fn(self._conn))
        schemas: dict[int, RecordSchema] = {}
        for list_id in range(max(count, 0)):
            name_buf = ctypes.create_string_buffer(MAX_FIELD_NAME)
            field_count = ctypes.c_int(0)
            unused = ctypes.c_int(0)
            if not rec_fn(self._conn, list_id, name_buf, ctypes.byref(field_count), ctypes.byref(unused)):
                continue
            fields: list[RecordField] = []
            for field_i in range(int(field_count.value)):
                fname = ctypes.create_string_buffer(MAX_FIELD_NAME)
                ftype = ctypes.c_int(0)
                fsize = ctypes.c_int(0)
                if not field_fn(self._conn, list_id, field_i, fname, ctypes.byref(ftype), ctypes.byref(fsize)):
                    continue
                fields.append(
                    RecordField(
                        name=fname.value.decode("latin-1", errors="replace").strip() or f"f{field_i}",
                        type=int(ftype.value),
                        size=int(fsize.value),
                    )
                )
            schemas[list_id] = RecordSchema(
                table_id=list_id,
                name=name_buf.value.decode("latin-1", errors="replace").strip(),
                fields=tuple(fields),
            )
        return schemas

    def write_list(self, device_address: int, list_id: int, blob: bytes, row_count: int, row_size: int) -> None:
        clear_fn = getattr(self._lib, "DFCClrListenBuffer", None)
        make_fn = getattr(self._lib, "DFCMakeListe", None)
        load_fn = getattr(self._lib, "DFCLoadListen", None)
        if not all((clear_fn, make_fn, load_fn)):
            raise DfcomError("Listen schreiben wird von dieser libDFCom.so nicht unterstützt")
        if not clear_fn(self._conn):
            raise DfcomError("Listenpuffer leeren fehlgeschlagen")
        total = max(0, int(row_count) * int(row_size))
        if blob and total == 0:
            total = len(blob)
        payload = blob[:total] if total else b""
        arr = (ctypes.c_ubyte * max(total, 1)).from_buffer_copy(payload.ljust(max(total, 1), b"\x00"))
        ptr = ctypes.cast(arr, ctypes.POINTER(ctypes.c_ubyte))
        if not make_fn(self._conn, int(list_id), int(row_count), int(total), ptr, 0):
            raise DfcomError("Liste aufbauen fehlgeschlagen")
        err = ctypes.c_int(0)
        if not load_fn(self._conn, int(device_address), ctypes.byref(err)):
            raise DfcomError(self._err(err.value) or "Liste laden fehlgeschlagen")


_factory = None
_native_lib: ctypes.CDLL | None = None
_native_failed = False


def set_client_factory(factory) -> None:
    global _factory
    _factory = factory


def library_available() -> bool:
    if _factory is not None:
        return True
    return find_library_path() is not None


def load_native_library() -> ctypes.CDLL | None:
    global _native_lib, _native_failed
    if _native_lib is not None:
        return _native_lib
    if _native_failed:
        return None
    path = find_library_path()
    if path is None:
        return None
    try:
        lib = ctypes.CDLL(str(path))
        _bind(lib)
        _native_lib = lib
        log.info("DFCom geladen: %s", path)
        return lib
    except OSError:
        _native_failed = True
        log.exception("libDFCom.so konnte nicht geladen werden (%s)", path)
        return None


def make_client() -> DfcomClient | None:
    if _factory is not None:
        return _factory()
    lib = load_native_library()
    if lib is None:
        return None
    return NativeDfcom(lib)
