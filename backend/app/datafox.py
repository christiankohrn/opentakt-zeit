from __future__ import annotations

from datetime import datetime
from urllib.parse import quote
from zoneinfo import ZoneInfo

from app.auth import as_local, now_utc

KIND_ALIASES = {
    "1": "in",
    "k": "in",
    "in": "in",
    "kommen": "in",
    "f1": "in",
    "2": "out",
    "g": "out",
    "out": "out",
    "gehen": "out",
    "f2": "out",
    "3": "break_start",
    "p": "break_start",
    "pause": "break_start",
    "pausebeginn": "break_start",
    "pause_beginn": "break_start",
    "break_start": "break_start",
    "f3": "break_start",
    "4": "break_end",
    "pauseende": "break_end",
    "pause_ende": "break_end",
    "break_end": "break_end",
    "f4": "break_end",
}

# BSS/TopZeit table Stempelung: Kennzeichen 0 = Kommen, 1 = Gehen (not HTTP fn).
STEMPELUNG_KENNZEICHEN = {
    "0": "in",
    "1": "out",
}
HTTP_KIND_FIELDS = ("fn", "kind", "status", "aktion", "function", "taste")


def normalize_badge(value: str) -> set[str]:
    raw = (value or "").strip().replace(" ", "").replace(":", "").replace("-", "")
    if not raw:
        return set()
    keys = {raw, raw.lower(), raw.upper(), raw.lstrip("0") or "0"}
    for base in (10, 16):
        try:
            n = int(raw, base)
        except ValueError:
            continue
        if n < 0:
            continue
        keys.add(str(n))
        keys.add(format(n, "X"))
        keys.add(format(n, "x"))
    return {k for k in keys if k}


def col(params: dict[str, str], *names: str) -> str:
    lower = {k.lower(): v for k, v in params.items()}
    for name in names:
        key = name.lower()
        if key in lower and str(lower[key]).strip():
            return str(lower[key]).strip()
        prefixed = f"df_col_{key}"
        if prefixed in lower and str(lower[prefixed]).strip():
            return str(lower[prefixed]).strip()
    return ""


def _table_name(params: dict[str, str]) -> str:
    return (params.get("df_table") or params.get("table") or "").strip().lower()


def parse_kind(params: dict[str, str]) -> str | None:
    table = _table_name(params)
    kz = col(params, "kennzeichen", "kz")
    http_raw = col(params, *HTTP_KIND_FIELDS)
    if table == "stempelung" or (kz and not http_raw):
        if not kz:
            return None
        return STEMPELUNG_KENNZEICHEN.get(kz.strip().lower())
    key = http_raw.strip().lower().replace(" ", "").replace("-", "_")
    return KIND_ALIASES.get(key)


def parse_badge(params: dict[str, str]) -> str:
    return col(params, "badge", "karte", "transponder", "ausweis", "card", "cardno", "rfid")


def parse_timestamp(params: dict[str, str]) -> datetime | None:
    raw = col(params, "timestamp", "datum/zeit", "datumzeit", "time", "dt", "datetime", "zeit")
    if not raw:
        return None
    text = raw.replace(" ", "T", 1)
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("Europe/Berlin"))
    return dt.astimezone(ZoneInfo("UTC"))


def flatten_params(params: dict[str, str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in params.items():
        k = key.strip()
        v = value if isinstance(value, str) else str(value)
        out[k] = v
        if k.lower().startswith("df_col_"):
            out[k[7:]] = v
    return out


def ack_body(extra: dict[str, str] | None = None) -> str:
    parts = ["df_api=1"]
    for key, value in (extra or {}).items():
        if value == "":
            continue
        parts.append(f"{key}={quote(str(value), safe='\\,', encoding='iso-8859-1', errors='replace')}")
    dt = as_local(now_utc()).strftime("%Y-%m-%dT%H:%M:%S")
    if extra is None or "df_time" not in extra:
        parts.append(f"df_time={quote(dt, safe='')}")
    return "&".join(parts)
