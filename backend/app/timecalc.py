from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.auth import as_local, local_day_bounds
from app.models import Punch, WorkModel

KINDS = ("in", "out", "break_start", "break_end")
VALID_TRANSITIONS = {
    "away": {"in"},
    "in": {"out", "break_start"},
    "break": {"break_end", "out"},
}


def status_from_punches(punches: list[Punch]) -> str:
    active = [p for p in punches if p.voided_at is None]
    active.sort(key=lambda p: p.server_time)
    state = "away"
    for p in active:
        if p.kind == "in":
            state = "in"
        elif p.kind == "break_start":
            state = "break"
        elif p.kind == "break_end":
            state = "in"
        elif p.kind == "out":
            state = "away"
    return state


def allowed_kinds(state: str) -> list[str]:
    return sorted(VALID_TRANSITIONS.get(state, set()))


def punches_window_for_month(start: date, last: date) -> tuple[datetime, datetime]:
    """Include the neighbouring days so night shifts across midnight are visible."""
    q_start, _ = local_day_bounds(start - timedelta(days=1))
    _, q_end = local_day_bounds(last + timedelta(days=1))
    return q_start, q_end


def model_on_day(
    timeline: list[tuple[date, WorkModel | None]],
    day: date,
    fallback: WorkModel | None = None,
) -> WorkModel | None:
    current = fallback
    for start, model in timeline:
        if start <= day:
            current = model
        else:
            break
    return current


def soll_hours(model: WorkModel | None, day: date) -> float:
    if not model:
        return 0.0
    mapping = {
        0: model.hours_mon,
        1: model.hours_tue,
        2: model.hours_wed,
        3: model.hours_thu,
        4: model.hours_fri,
        5: model.hours_sat,
        6: model.hours_sun,
    }
    return float(mapping[day.weekday()])


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=ZoneInfo("UTC"))
    return dt.astimezone(ZoneInfo("UTC"))


def summarize_day(
    punches: list[Punch],
    day: date,
    model: WorkModel | None,
    now: datetime | None = None,
    absence=None,
    auto_break: bool = False,
    calendar=None,
) -> dict:
    start_utc, end_utc = local_day_bounds(day)
    now = now or datetime.now(tz=ZoneInfo("UTC"))
    all_in_day = [p for p in punches if start_utc <= _as_utc(p.server_time) < end_utc]
    all_in_day.sort(key=lambda p: p.server_time)
    events = [p for p in all_in_day if p.voided_at is None]

    prev = [p for p in punches if p.voided_at is None and _as_utc(p.server_time) < start_utc]
    prev_state = status_from_punches(prev)

    work = timedelta(0)
    pause = timedelta(0)
    open_in: datetime | None = None
    open_break: datetime | None = None
    first_in: datetime | None = None
    last_out: datetime | None = None
    still_open = False
    if prev_state == "in":
        open_in = start_utc
        first_in = start_utc
    elif prev_state == "break":
        open_break = start_utc

    for p in events:
        t = _as_utc(p.server_time)
        if p.kind == "in":
            open_in = t
            if first_in is None:
                first_in = t
        elif p.kind == "break_start" and open_in:
            work += t - open_in
            open_in = None
            open_break = t
        elif p.kind == "break_end" and open_break:
            pause += t - open_break
            open_break = None
            open_in = t
        elif p.kind == "out":
            if open_break:
                pause += t - open_break
                open_break = None
            if open_in:
                work += t - open_in
                open_in = None
            last_out = t

    day_end = min(now, end_utc)
    if open_break:
        pause += day_end - open_break
        still_open = True
    if open_in:
        work += day_end - open_in
        still_open = True

    work_h = work.total_seconds() / 3600
    pause_h = pause.total_seconds() / 3600
    auto_applied = 0.0
    if auto_break and not still_open:
        stamped_break = pause_h > 0.001 or any(p.kind in {"break_start", "break_end"} for p in events)
        if not stamped_break:
            if work_h > 9:
                auto_applied = 0.75
            elif work_h > 6:
                auto_applied = 0.5
            if auto_applied:
                work_h -= auto_applied
                pause_h = auto_applied

    soll = soll_hours(model, day)
    warnings: list[str] = []
    if still_open and now >= end_utc:
        later = [
            p
            for p in punches
            if p.voided_at is None and _as_utc(p.server_time) >= end_utc
        ]
        later.sort(key=lambda p: p.server_time)
        next_kind = later[0].kind if later else None
        if next_kind and next_kind != "in":
            warnings.append("overnight")
        else:
            warnings.append("checkout_missing")
    if work_h > 6 and pause_h < 0.5:
        warnings.append("break_short")
    if work_h > 9 and pause_h < 0.75:
        warnings.append("break_short_9h")
    if work_h > 10:
        warnings.append("over_10h")
    if pause_h >= 1.5:
        warnings.append("break_long")

    def fmt(dt: datetime | None) -> str | None:
        return as_local(dt).strftime("%H:%M") if dt else None

    result = {
        "date": day.isoformat(),
        "first_in": fmt(first_in),
        "last_out": fmt(last_out),
        "work_hours": round(work_h, 2),
        "break_hours": round(pause_h, 2),
        "soll_hours": soll,
        "delta_hours": round(work_h - soll, 2),
        "open": still_open,
        "warnings": warnings,
        "auto_break_minutes": int(round(auto_applied * 60)) if auto_applied else 0,
        "accepted": None,
        "absence": None,
        "calendar": None,
        "weekday": day.weekday(),
        "punches": [
            {
                "id": p.id,
                "kind": p.kind,
                "time": as_local(_as_utc(p.server_time)).strftime("%H:%M"),
                "source": p.source,
                "device_id": p.device_id,
                "terminal_name": p.terminal_name or "",
                "voided": p.voided_at is not None,
            }
            for p in all_in_day
        ],
    }
    paid = {"vacation", "sick", "holiday", "company_off"}
    if calendar is not None:
        result["calendar"] = {"kind": calendar.kind, "name": calendar.name, "source": calendar.source}
    if absence is not None:
        result["absence"] = {"kind": absence.kind, "note": absence.note}
    off = (absence is not None and absence.kind in paid) or (
        calendar is not None and calendar.kind in {"holiday", "company_off"}
    )
    if off:
        result["warnings"] = []
        result["open"] = False
        if calendar is not None and calendar.kind in {"holiday", "company_off"}:
            result["soll_hours"] = 0.0
        if not events:
            result["work_hours"] = 0.0
            result["break_hours"] = 0.0
            result["auto_break_minutes"] = 0
            result["delta_hours"] = 0.0
        elif absence is not None and absence.kind in paid:
            result["delta_hours"] = 0.0
        else:
            result["delta_hours"] = round(result["work_hours"] - result["soll_hours"], 2)
    today = as_local(now).date()
    if (
        result["soll_hours"] > 0
        and not events
        and prev_state == "away"
        and not off
        and day < today
    ):
        result["warnings"] = [*result["warnings"], "missing_day"]
    return result
