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


def parse_kind(params: dict[str, str]) -> str | None:
    raw = col(params, "fn", "kind", "status", "aktion", "function", "taste")
    key = raw.strip().lower().replace(" ", "").replace("-", "_")
    return KIND_ALIASES.get(key)


def parse_badge(params: dict[str, str]) -> str:
    return col(params, "badge", "transponder", "ausweis", "card", "cardno", "rfid")


def parse_timestamp(params: dict[str, str]) -> datetime | None:
    raw = col(params, "timestamp", "time", "dt", "datetime", "zeit")
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
