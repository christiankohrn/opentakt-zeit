from __future__ import annotations

import json
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


def stamped_break_minutes(events: list[Punch]) -> int:
    """Dauer der Paare Pause Beginn/Ende, auch zwischen Gehen und Kommen."""
    pause = timedelta(0)
    open_break: datetime | None = None
    for punch in events:
        t = _as_minute(punch.server_time)
        if punch.kind == "break_start":
            open_break = t
        elif punch.kind == "break_end" and open_break is not None:
            if t > open_break:
                pause += t - open_break
            open_break = None
    return int(pause.total_seconds() // 60)


DEFAULT_BREAK_RULES: tuple[dict[str, int], ...] = (
    {"after_hours": 6, "minutes": 30},
    {"after_hours": 9, "minutes": 45},
)


def default_break_steps() -> list[tuple[int, int]]:
    return [(int(item["after_hours"]) * 60, int(item["minutes"])) for item in DEFAULT_BREAK_RULES]


def break_steps(model: object | None) -> list[tuple[int, int]]:
    """Schwellen (ab Minute, Mindestpause). Leer heißt: keine Mindestpause."""
    raw = getattr(model, "break_rules", None) if model is not None else None
    if raw is None or raw == "":
        return default_break_steps()
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return default_break_steps()
    if not isinstance(raw, list):
        return default_break_steps()
    steps: list[tuple[int, int]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        after = item.get("after_hours")
        minutes = item.get("minutes")
        if after is None or minutes is None:
            continue
        try:
            after_minutes = int(round(float(after) * 60))
            need = int(minutes)
        except (TypeError, ValueError):
            continue
        if need <= 0 or after_minutes < 0:
            continue
        steps.append((after_minutes, need))
    steps.sort()
    return steps


def stamped_break_intervals(events: list[Punch]) -> list[tuple[datetime, datetime]]:
    """Paare Pause Beginn/Ende, auch zwischen Gehen und Kommen."""
    intervals: list[tuple[datetime, datetime]] = []
    open_break: datetime | None = None
    for punch in events:
        t = _as_minute(punch.server_time)
        if punch.kind == "break_start":
            open_break = t
        elif punch.kind == "break_end" and open_break is not None:
            if t > open_break:
                intervals.append((open_break, t))
            open_break = None
    return intervals


def _covered_minutes(blocks: list[tuple[datetime, datetime]], start: datetime, end: datetime) -> int:
    """Minuten von start bis end, die irgendein Block trifft. Überlappungen zählen einmal."""
    clipped: list[tuple[datetime, datetime]] = []
    for lo, hi in blocks:
        begin = max(lo, start)
        finish = min(hi, end)
        if finish > begin:
            clipped.append((begin, finish))
    clipped.sort()
    total = 0
    cursor: datetime | None = None
    for begin, finish in clipped:
        if cursor is None or begin >= cursor:
            total += int((finish - begin).total_seconds() // 60)
            cursor = finish
        elif finish > cursor:
            total += int((finish - cursor).total_seconds() // 60)
            cursor = finish
    return total


def window_break_minutes(
    anchor: datetime | None,
    spans: list[tuple[datetime, datetime]],
    breaks: list[tuple[datetime, datetime]],
    work_minutes: int,
    last_out: datetime | None,
    steps: list[tuple[int, int]] | None = None,
) -> int:
    """Mindestpause als Uhrzeitfenster: Beginn plus Schwelle, Dauer der hinterlegten Pause.

    Eine Schwelle gilt erst, wenn die Arbeitszeit sie überschreitet. Wer im Fenster
    noch anwesend ist und danach weiterarbeitet, verliert die volle Pause. Eine
    Lücke am Anfang des Fensters kürzt sie nicht. Die Minuten nach dem Fenster
    bleiben Arbeit: reicht die Zeit nicht für die volle Pause, bleibt die Ist-Zeit
    auf der Schwelle. Wer im Fenster Feierabend macht, verliert nur die Zeit bis
    zum Gehen. Die höhere Schwelle ersetzt die niedrigere erst, wenn ihr Fenster
    mehr Minuten trifft.
    """
    if anchor is None:
        return 0
    rules = default_break_steps() if steps is None else steps
    blocks = [*spans, *breaks]
    owed = 0
    for after, need in rules:
        if work_minutes <= after:
            continue
        window_start = anchor + timedelta(minutes=after)
        window_end = window_start + timedelta(minutes=need)
        covered = _covered_minutes(blocks, window_start, window_end)
        if covered <= 0:
            continue
        if last_out is not None and last_out >= window_end:
            step_owed = need
        else:
            step_owed = covered
        # Nach dem Fenster geleistete Minuten bleiben erhalten. Sonst fiele die
        # Ist-Zeit unter die Schwelle, die die Pause überhaupt geöffnet hat.
        if last_out is not None and last_out > window_end:
            step_owed = min(step_owed, work_minutes - after)
        owed = max(owed, step_owed)
    return owed


def break_warning_codes(work_minutes: int, pause_minutes: int, steps: list[tuple[int, int]]) -> list[str]:
    codes: list[str] = []
    for after, need in steps:
        if work_minutes <= after or pause_minutes >= need:
            continue
        if after == 6 * 60 and need == 30:
            codes.append("break_short")
        elif after == 9 * 60 and need == 45:
            codes.append("break_short_9h")
        else:
            hours = after / 60
            token = str(int(hours)) if hours.is_integer() else f"{hours:.2f}".rstrip("0").rstrip(".")
            codes.append(f"break_short:{need}:{token}")
    return codes


_WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def _clock_minutes(value: object) -> int | None:
    if not isinstance(value, str) or ":" not in value:
        return None
    hour, minute = value.split(":", 1)
    try:
        total = int(hour) * 60 + int(minute)
    except ValueError:
        return None
    if 0 <= total < 24 * 60:
        return total
    return None


def _shift_data(model) -> list:
    raw = getattr(model, "shifts", None) or ""
    if isinstance(raw, list):
        data = raw
    elif isinstance(raw, str) and raw.strip():
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return []
    else:
        return []
    return data if isinstance(data, list) else []


def _shift_rows(model, day: date) -> list[tuple[str, int, int]]:
    """Korridore der Schichten an diesem Wochentag. Leere Tage liefern nichts."""
    key = _WEEKDAYS[day.weekday()]
    rows: list[tuple[str, int, int]] = []
    for slot in _shift_data(model):
        if not isinstance(slot, dict):
            continue
        days = slot.get("days") if isinstance(slot.get("days"), dict) else None
        if days is not None:
            cell = days.get(key) or {}
            if not isinstance(cell, dict):
                continue
            start = _clock_minutes(cell.get("start"))
            end = _clock_minutes(cell.get("end"))
        else:
            start = _clock_minutes(slot.get("start"))
            end = _clock_minutes(slot.get("end"))
        if start is None or end is None or start == end:
            continue
        rows.append((str(slot.get("name") or ""), start, end))
    return rows


def _nearest_shift(minute: int, rows: list[tuple[str, int, int]]) -> tuple[str, int, int]:
    def distance(start: int) -> int:
        delta = abs(minute - start)
        return min(delta, 24 * 60 - delta)

    return min(rows, key=lambda row: (distance(row[1]), row[1], row[0]))


def _open_shift_in(punches: list[Punch]) -> datetime | None:
    started: datetime | None = None
    state = "away"
    for punch in sorted(punches, key=lambda item: _as_utc(item.server_time)):
        if punch.kind == "in":
            state = "in"
            started = punch.server_time
        elif punch.kind == "break_start" and state == "in":
            state = "break"
        elif punch.kind == "break_end" and state == "break":
            state = "in"
        elif punch.kind == "out":
            state = "away"
            started = None
    return started if state in {"in", "break"} else None


def _before_corridor(minute: int, start: int | None, end: int | None) -> bool:
    if start is None:
        return False
    if end is None or end > start:
        return minute < start
    return end < minute < start


def _after_corridor(minute: int, start: int | None, end: int | None) -> bool:
    if end is None:
        return False
    if start is None or end > start:
        return minute > end
    return end < minute < start


def _corridor_bounds(model, day: date) -> tuple[int | None, int | None]:
    raw = getattr(model, "booking_corridor", None) or ""
    if isinstance(raw, dict):
        data = raw
    elif isinstance(raw, str) and raw.strip():
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return None, None
    else:
        return None, None
    slot = data.get(_WEEKDAYS[day.weekday()]) or {}
    if not isinstance(slot, dict):
        return None, None
    return _clock_minutes(slot.get("start")), _clock_minutes(slot.get("end"))


def _grid_minute(minute: int, step: int, threshold: int) -> int:
    """Rasterrundung. Die Schwellenminute rundet noch ab, samt ihrer Sekunden.

    Sekunden sind hier schon abgeschnitten. Bei Schwelle 2 bleibt 2:59 unten,
    ab der nächsten vollen Minute (3:00) wird aufgerundet.
    """
    if step <= 0:
        return minute
    offset = minute % step
    if offset <= threshold:
        return minute - offset
    return minute + (step - offset)


def _near(minute: int, bound: int, before: int, after: int) -> bool:
    if before <= 0 and after <= 0:
        return False
    delta = minute - bound
    return -before <= delta <= after


def _shift_to_minute(t: datetime, minute_of_day: int) -> datetime:
    local = as_local(t)
    current = local.hour * 60 + local.minute
    return _as_minute(t + timedelta(minutes=minute_of_day - current))


def credit_start(
    t: datetime,
    model,
    day: date,
    bounds: tuple[int | None, int | None] | None = None,
    comp_time: bool = False,
) -> datetime:
    """Erstes Kommen: vor dem Korridor zählt nicht, Fenster zieht auf den Beginn, sonst Raster.

    Mit Zeitausgleich entfällt das Raster. Korridor und das Fenster um den Arbeitsbeginn bleiben.
    """
    local = as_local(t)
    minute = local.hour * 60 + local.minute
    start, end = bounds if bounds is not None else _corridor_bounds(model, day)
    before = int(getattr(model, "round_start_before", 0) or 0)
    after = int(getattr(model, "round_start_after", 0) or 0)
    pinned = False
    if _before_corridor(minute, start, end) and start is not None:
        minute = start
        pinned = True
    elif start is not None and _near(minute, start, before, after):
        minute = start
        pinned = True
    if not pinned and not comp_time:
        minute = _grid_minute(
            minute,
            int(getattr(model, "round_first_step", 0) or 0),
            int(getattr(model, "round_first_threshold", 0) or 0),
        )
    return _shift_to_minute(t, minute)


def credit_end(
    t: datetime,
    model,
    day: date,
    bounds: tuple[int | None, int | None] | None = None,
) -> datetime:
    """Letztes Gehen: nach dem Korridor zählt nicht, Fenster zieht auf das Ende, sonst Raster."""
    local = as_local(t)
    minute = local.hour * 60 + local.minute
    start, end = bounds if bounds is not None else _corridor_bounds(model, day)
    before = int(getattr(model, "round_end_before", 0) or 0)
    after = int(getattr(model, "round_end_after", 0) or 0)
    pinned = False
    if _after_corridor(minute, start, end) and end is not None:
        minute = end
        pinned = True
    elif end is not None and _near(minute, end, before, after):
        minute = end
        pinned = True
    if not pinned:
        minute = _grid_minute(
            minute,
            int(getattr(model, "round_last_step", 0) or 0),
            int(getattr(model, "round_last_threshold", 0) or 0),
        )
        if _after_corridor(minute, start, end) and end is not None:
            minute = end
    return _shift_to_minute(t, minute)


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
        if day_end > open_in:
            intervals.append((open_in, day_end))
    return intervals


def _closed_later(punches: list[Punch], end_utc: datetime) -> bool:
    """Whether a punch after this day continues the open shift (night shift)."""
    later = [p for p in punches if p.voided_at is None and _as_utc(p.server_time) >= end_utc]
    later.sort(key=lambda p: _as_utc(p.server_time))
    next_kind = later[0].kind if later else None
    return next_kind is not None and next_kind != "in"


def _consume_open_shift(punches: list[Punch], state: str) -> tuple[list[Punch], list[Punch]]:
    """Punches that finish an open shift, then whatever starts the next one."""
    if state not in {"in", "break"}:
        return [], list(punches)
    taken: list[Punch] = []
    for index, punch in enumerate(punches):
        if punch.kind == "in":
            return taken, list(punches[index:])
        taken.append(punch)
        if punch.kind == "out":
            return taken, list(punches[index + 1 :])
        if punch.kind == "break_start":
            state = "break"
        elif punch.kind == "break_end":
            state = "in"
    return taken, []


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
    has_shifts = bool(_shift_data(model)) if model is not None else False
    day_rows = _shift_rows(model, day) if has_shifts else []
    # Nachtschicht bleibt am Tag des Kommens. Das Gehen am Morgen gehört nicht
    # noch einmal zum Folgetag, auch wenn der Korridor nur an manchen Wochentagen steht.
    carried: list[Punch] = []
    continuation: list[Punch] = []
    if has_shifts and prev_state in {"in", "break"}:
        carried, events = _consume_open_shift(events, prev_state)
        prev_state = "away"
    if has_shifts:
        state = prev_state
        for punch in events:
            if punch.kind == "in":
                state = "in"
            elif punch.kind == "break_start" and state == "in":
                state = "break"
            elif punch.kind == "break_end" and state == "break":
                state = "in"
            elif punch.kind == "out":
                state = "away"
        if state in {"in", "break"}:
            later = [p for p in punches if p.voided_at is None and _as_utc(p.server_time) >= end_utc]
            later.sort(key=lambda p: _as_utc(p.server_time))
            taken, _rest = _consume_open_shift(later, state)
            if any(p.kind == "out" for p in taken):
                continuation = taken
                events = [*events, *continuation]

    work = timedelta(0)
    pause = timedelta(0)
    open_in: datetime | None = None
    open_break: datetime | None = None
    first_in: datetime | None = None
    last_out: datetime | None = None
    # Kommen bis Gehen, die Pause dazwischen bleibt im Fenster. Eine Lücke
    # zwischen Gehen und dem nächsten Kommen ist nicht anwesend.
    spans: list[tuple[datetime, datetime]] = []
    span_open: datetime | None = None
    still_open = False
    if prev_state == "in":
        open_in = start_utc
        first_in = start_utc
        span_open = start_utc
    elif prev_state == "break":
        open_break = start_utc
        span_open = start_utc

    first_in_punch = next((p for p in events if p.kind == "in"), None)
    last_out_punch = next((p for p in reversed(events) if p.kind == "out"), None)
    comp_time = absence is not None and getattr(absence, "kind", None) == "comp_time"
    active_bounds: tuple[int | None, int | None] | None = None
    shift_names: list[str] = []
    if has_shifts and prev_state in {"in", "break"}:
        origin = _open_shift_in(prev)
        if origin is not None:
            local = as_local(origin)
            origin_rows = _shift_rows(model, local.date())
            if origin_rows:
                name, start, end = _nearest_shift(local.hour * 60 + local.minute, origin_rows)
                active_bounds = (start, end)
                shift_names.append(name)

    for p in events:
        t = _as_minute(p.server_time)
        if p.kind == "in" and open_in is None and open_break is None and has_shifts:
            # Eine zweite Schicht am selben Tag gibt es nicht. Spätere Buchungen
            # bleiben im Korridor der ersten.
            if day_rows and active_bounds is None:
                local = as_local(p.server_time)
                name, start, end = _nearest_shift(local.hour * 60 + local.minute, day_rows)
                active_bounds = (start, end)
                if name not in shift_names:
                    shift_names.append(name)
            if active_bounds is not None:
                t = credit_start(t, model, day, active_bounds, comp_time=comp_time and p is first_in_punch)
        elif model is not None and p is first_in_punch and not has_shifts:
            t = credit_start(t, model, day, comp_time=comp_time)
        elif p.kind == "out" and has_shifts and active_bounds is not None:
            t = credit_end(t, model, day, active_bounds)
        elif model is not None and p is last_out_punch and not has_shifts:
            t = credit_end(t, model, day)
        if p.kind == "in":
            if open_in is None and open_break is None:
                open_in = t
                if first_in is None:
                    first_in = t
                if span_open is None:
                    span_open = t
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
                if t > open_in:
                    work += t - open_in
                open_in = None
            if span_open is not None:
                if t > span_open:
                    spans.append((span_open, t))
                span_open = None
            last_out = t

    day_end = _as_minute(min(now, end_utc))
    # Ein noch nicht begonnener Tag erbt die offene Schicht nicht. Sonst steht dort
    # 00:00 offen und die Dauer läuft von der Zukunft bis jetzt rückwärts.
    if now < start_utc and not events:
        open_in = None
        open_break = None
        first_in = None
        span_open = None
    elif open_break or open_in:
        still_open = True
        credit_tail = now < end_utc or _closed_later(punches, end_utc)
        if credit_tail:
            if open_break and day_end > open_break:
                pause += day_end - open_break
            if open_in and day_end > open_in:
                work += day_end - open_in

    work_minutes = int(work.total_seconds() // 60)
    pause_minutes = max(int(pause.total_seconds() // 60), stamped_break_minutes(events))
    steps = break_steps(model)
    auto_minutes = 0
    if auto_break and not still_open:
        # Gestempelte Minuten zählen auf das Fenster an. Ist die Stempelpause
        # länger, bleibt sie stehen und es wird nichts zusätzlich abgezogen.
        required = window_break_minutes(
            first_in, spans, stamped_break_intervals(events), work_minutes, last_out, steps
        )
        if pause_minutes < required:
            auto_minutes = required - pause_minutes
            work_minutes -= auto_minutes
            pause_minutes = required
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
    warnings.extend(break_warning_codes(work_minutes, pause_minutes, steps))
    if work_h > 10:
        warnings.append("over_10h")
    if pause_h >= 1.5:
        warnings.append("break_long")

    def fmt(dt: datetime | None) -> str | None:
        return as_local(dt).strftime("%H:%M") if dt else None

    def punch_row(p: Punch) -> dict:
        return {
            "id": p.id,
            "kind": p.kind,
            "time": as_local(_as_utc(p.server_time)).strftime("%H:%M"),
            "source": p.source,
            "device_id": p.device_id,
            "terminal_name": p.terminal_name or "",
            "voided": p.voided_at is not None,
        }

    carried_ids = {id(p) for p in carried}
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
        "shift": " · ".join(shift_names) if shift_names else None,
        "punches": [punch_row(p) for p in all_in_day],
    }
    if carried or continuation:
        span = [p for p in all_in_day if id(p) not in carried_ids]
        span.extend(continuation)
        result["span_punches"] = [punch_row(p) for p in span]
    # Schule und Sonderurlaub füllen die Sollzeit wie Urlaub und Krankheit.
    # Zeitausgleich nicht: der Tag bleibt bei null Ist, das Konto fällt um die Sollzeit.
    credited = {"vacation", "sick", "school", "special_leave"}
    paid = credited | {"holiday", "company_off"}
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
        fills = absence is not None and absence.kind in credited
        if fills:
            stamped = 0.0 if not events else float(result["work_hours"])
            if not events:
                result["break_hours"] = 0.0
                result["auto_break_minutes"] = 0
            target = float(result["soll_hours"])
            # Krankheit füllt nur die Lücke bis zur Sollzeit. Anwesenheit darüber bleibt.
            if absence is not None and absence.kind == "sick":
                result["work_hours"] = max(target, stamped)
                result["delta_hours"] = result["work_hours"] - target
            else:
                result["work_hours"] = target + stamped
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
        and not (absence is not None and absence.kind == "comp_time")
    ):
        result["warnings"] = [*result["warnings"], "missing_day"]
    return result
