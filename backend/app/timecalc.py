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
    active.sort(key=lambda p: _as_utc(p.server_time))
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


def _as_minute(dt: datetime) -> datetime:
    """Clock minute used for durations. The display already hides seconds."""
    return _as_utc(dt).replace(second=0, microsecond=0)


def work_intervals(
    punches: list[Punch],
    day: date,
    now: datetime | None = None,
) -> list[tuple[datetime, datetime]]:
    """UTC work intervals on this local day, excluding breaks. Open shifts run until min(now, day end)."""
    start_utc, end_utc = local_day_bounds(day)
    now = now or datetime.now(tz=ZoneInfo("UTC"))
    events = [
        p
        for p in punches
        if p.voided_at is None and start_utc <= _as_utc(p.server_time) < end_utc
    ]
    events.sort(key=lambda p: _as_utc(p.server_time))
    prev = [p for p in punches if p.voided_at is None and _as_utc(p.server_time) < start_utc]
    prev_state = status_from_punches(prev)
    intervals: list[tuple[datetime, datetime]] = []
    open_in: datetime | None = start_utc if prev_state == "in" else None
    open_break: datetime | None = start_utc if prev_state == "break" else None
    for p in events:
        t = _as_minute(p.server_time)
        if p.kind == "in":
            # Batch imports store stamps verbatim; a second "in" must not
            # move the start forward and drop the earlier time.
            if open_in is None and open_break is None:
                open_in = t
        elif p.kind == "break_start" and open_in:
            intervals.append((open_in, t))
            open_in = None
            open_break = t
        elif p.kind == "break_end" and open_break:
            open_break = None
            open_in = t
        elif p.kind == "out":
            if open_break:
                open_break = None
            if open_in:
                intervals.append((open_in, t))
                open_in = None
    day_end = _as_minute(min(now, end_utc))
    if open_in:
        if now >= end_utc and not _closed_later(punches, end_utc):
            # Forgotten checkout: the shift was never closed, so the tail
            # until midnight is unknown and must not be credited.
            return intervals
        intervals.append((open_in, day_end))
    return intervals


def _closed_later(punches: list[Punch], end_utc: datetime) -> bool:
    """Whether a punch after this day continues the open shift (night shift)."""
    later = [p for p in punches if p.voided_at is None and _as_utc(p.server_time) >= end_utc]
    later.sort(key=lambda p: _as_utc(p.server_time))
    next_kind = later[0].kind if later else None
    return next_kind is not None and next_kind != "in"


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
    all_in_day.sort(key=lambda p: _as_utc(p.server_time))
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
        t = _as_minute(p.server_time)
        if p.kind == "in":
            if open_in is None and open_break is None:
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

    day_end = _as_minute(min(now, end_utc))
    if open_break or open_in:
        still_open = True
        credit_tail = now < end_utc or _closed_later(punches, end_utc)
        if credit_tail:
            if open_break:
                pause += day_end - open_break
            if open_in:
                work += day_end - open_in

    work_minutes = int(work.total_seconds() // 60)
    pause_minutes = int(pause.total_seconds() // 60)
    auto_minutes = 0
    if auto_break and not still_open:
        stamped_break = pause_minutes > 0 or any(p.kind in {"break_start", "break_end"} for p in events)
        if not stamped_break:
            if work_minutes > 9 * 60 + 45:
                auto_minutes = 45
            elif work_minutes > 9 * 60 + 30:
                auto_minutes = work_minutes - 9 * 60
            elif work_minutes > 6 * 60 + 30:
                auto_minutes = 30
            elif work_minutes > 6 * 60:
                auto_minutes = work_minutes - 6 * 60
            if auto_minutes:
                work_minutes -= auto_minutes
                pause_minutes = auto_minutes
    work_h = work_minutes / 60
    pause_h = pause_minutes / 60
    auto_applied = auto_minutes / 60

    soll = soll_hours(model, day)
    warnings: list[str] = []
    if still_open and now >= end_utc:
        if _closed_later(punches, end_utc):
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
        "work_hours": work_h,
        "break_hours": pause_h,
        "soll_hours": soll,
        "delta_hours": work_h - soll,
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
        fills = absence is not None and absence.kind in {"vacation", "sick"}
        if fills:
            stamped = 0.0 if not events else float(result["work_hours"])
            if not events:
                result["break_hours"] = 0.0
                result["auto_break_minutes"] = 0
            result["work_hours"] = float(result["soll_hours"]) + stamped
            result["delta_hours"] = stamped
        elif not events:
            result["work_hours"] = 0.0
            result["break_hours"] = 0.0
            result["auto_break_minutes"] = 0
            result["delta_hours"] = 0.0
        else:
            result["delta_hours"] = result["work_hours"] - result["soll_hours"]
    today = as_local(now).date()
    if day > today:
        # Nothing settled yet: future days carry no delta and no warnings,
        # so journals and balances agree without capping each sum separately.
        result["delta_hours"] = 0.0
        result["warnings"] = []
    if (
        result["soll_hours"] > 0
        and not events
        and prev_state == "away"
        and not off
        and day < today
    ):
        result["warnings"] = [*result["warnings"], "missing_day"]
    return result
