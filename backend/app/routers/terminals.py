from __future__ import annotations

import hmac
import json
import logging
from urllib.parse import parse_qsl
from uuid import uuid4

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.balance import account_hours, format_flex
from app.config import get_config
from app.datafox import ack_body, flatten_params, parse_badge, parse_kind, parse_timestamp
from app.database import get_db
from app.models import Punch, User
from app.punches import KIND_LABELS
from app.terminal_punch import apply_booking

router = APIRouter(prefix="/terminals", tags=["terminals"])
log = logging.getLogger(__name__)


def _latin1(body: str, status_code: int = 200) -> Response:
    return Response(
        content=body.encode("iso-8859-1", errors="replace"),
        status_code=status_code,
        media_type="text/html; charset=ISO-8859-1",
    )


def _secret_ok(provided: str) -> bool:
    expected = (get_config().datafox_secret or "").strip()
    if not expected or not provided:
        return False
    left = provided.encode("utf-8")
    right = expected.encode("utf-8")
    if len(left) != len(right):
        return False
    return hmac.compare_digest(left, right)


async def _params(request: Request) -> dict[str, str]:
    data: dict[str, str] = {k: v for k, v in request.query_params.multi_items()}
    if request.method != "POST":
        return flatten_params(data)
    raw = await request.body()
    if not raw:
        return flatten_params(data)
    ctype = (request.headers.get("content-type") or "").lower()
    if "json" in ctype:
        try:
            parsed = json.loads(raw.decode("utf-8"))
            if isinstance(parsed, dict):
                data.update({str(k): str(v) for k, v in parsed.items() if v is not None})
        except ValueError:
            pass
    else:
        text = raw.decode("iso-8859-1", errors="replace")
        data.update(dict(parse_qsl(text, keep_blank_values=True)))
    return flatten_params(data)


@router.api_route("/datafox", methods=["GET", "POST"])
async def datafox(request: Request, db: Session = Depends(get_db)):
    cfg = get_config()
    if not (cfg.datafox_secret or "").strip():
        return _latin1("df_api=1&df_msg=Terminal%20nicht%20konfiguriert,5,2,0", 503)

    params = await _params(request)
    key = params.get("k") or params.get("key") or request.headers.get("x-datafox-key") or ""
    if not _secret_ok(key):
        return _latin1(ack_body({"df_msg": "Zugang verweigert,5,2,0", "df_beep": "2"}))

    table = (params.get("df_table") or params.get("table") or "").strip().lower()
    if table in {"alive", "info"} or params.get("df_type") == "kvp":
        return _latin1(ack_body())

    badge = parse_badge(params)
    kind = parse_kind(params)
    if not badge or not kind:
        if not badge and not kind:
            return _latin1(ack_body())
        return _latin1(ack_body({"df_msg": "Ungueltige Buchung,5,2,0", "df_beep": "2"}))

    event_id = (params.get("df_id") or params.get("id") or "").strip() or uuid4().hex
    result = apply_booking(
        db,
        badge=badge,
        kind=kind,
        timestamp=parse_timestamp(params),
        event_id=f"df-{event_id}"[:64],
        source="terminal",
        note=f"terminal {request.client.host if request.client else ''}".strip(),
        persist=True,
    )
    if result.outcome == "unknown":
        return _latin1(ack_body({"df_msg": "Unbekannter Ausweis,5,2,0", "df_beep": "2"}))
    if result.outcome == "invalid":
        return _latin1(ack_body({"df_msg": "Ungueltige Buchung,5,2,0", "df_beep": "2"}))
    if result.outcome == "conflict":
        return _latin1(ack_body({"df_msg": f"{result.detail[:80]},6,2,0", "df_beep": "2"}))

    user = db.get(User, result.user_id) if result.user_id else None
    punch = db.get(Punch, result.punch_id) if result.punch_id else None
    first = (user.display_name.split()[0] if user and user.display_name else None) or "OK"
    label = KIND_LABELS.get(result.kind or "", result.kind or "")
    line2 = label
    if user and punch:
        try:
            month_h, total_h = account_hours(db, user, punch.server_time)
            line2 = f"{label} {format_flex(month_h)}/{format_flex(total_h)}"
        except Exception:
            log.exception("flex display failed user=%s", user.id)
    log.info("terminal punch user=%s kind=%s", result.user_id, result.kind)
    return _latin1(ack_body({"df_msg": f"{first}\\r{line2},4,1,0", "df_beep": "1"}))
