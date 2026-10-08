from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.auth import as_local, now_utc
from app.balance import days_in_range, hired_on, is_employed, load_day_model_map, month_days
from app.holidays import calendar_map
from app.models import Absence, AccountEntry, Punch, User
from app.names import name_sort_key
from app.timecalc import punches_window_for_month, soll_hours, work_intervals
from app.workmodels import load_frozen_map, load_timelines, model_for, overlay_model

JUBILEE_YEARS = (10, 25, 40)
NIGHT_WINDOWS = (
    ("hours_20_24", time(20, 0), None),
    ("hours_0_4", time(0, 0), time(4, 0)),
    ("hours_4_6", time(4, 0), time(6, 0)),
)
VACATION_NOTE = "Urlaub „inkl. Zukunft“ enthält gebuchte Tage nach dem Stichtag im Kalenderjahr."
JOURNAL_ACCOUNT_NOTE = "Resturlaub = Jahresanspruch - genommen - verplant + manuelle Buchungen. Anspruch am Stammsatz unter Urlaubstage/Jahr."
PUNCH_LABELS = {
    "in": "Kommen",
    "out": "Gehen",
    "break_start": "Pause Beginn",
    "break_end": "Pause Ende",
}
ABSENCE_LABELS = {
    "vacation": "Urlaub",
    "sick": "Krankheit",
    "holiday": "Feiertag",
    "company_off": "Betriebsfrei",
    "other": "Abwesend",
}
WEEKDAYS = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")
MONTHS = (
    "Januar",
    "Februar",
    "März",
    "April",
    "Mai",
    "Juni",
    "Juli",
    "August",
    "September",
    "Oktober",
    "November",
    "Dezember",
)


CSV_UNSAFE_LEAD = ("=", "+", "-", "@", "\t", "\r", "\n")


def safe_csv_cell(value):
    """Prefix spreadsheet formula triggers so exports stay plain text."""
    if isinstance(value, str) and value.startswith(CSV_UNSAFE_LEAD):
        return "'" + value
    return value


def year_bounds(year: int) -> tuple[date, date]:
    return date(year, 1, 1), date(year, 12, 31)


def month_bounds(month: str) -> tuple[date, date]:
    year, mon = (int(part) for part in month.split("-"))
    start = date(year, mon, 1)
    end = date(year + 1, 1, 1) if mon == 12 else date(year, mon + 1, 1)
    return start, end - timedelta(days=1)


def half_bounds(year: int, half: int) -> tuple[date, date]:
    if half == 1:
        return date(year, 1, 1), date(year, 6, 30)
    return date(year, 7, 1), date(year, 12, 31)


def employment_overlap(user: User, start: date, end: date) -> tuple[date, date] | None:
    hire = hired_on(user)
    leave = user.left_on or date.max
    lo = max(start, hire)
    hi = min(end, leave)
    if lo > hi:
        return None
    return lo, hi


def people_in_range(db: Session, start: date, end: date, user_ids: set[int] | None = None) -> list[User]:
    users = sorted(
        db.scalars(select(User).options(selectinload(User.work_model), selectinload(User.department))),
        key=lambda user: name_sort_key(user.display_name),
    )
    people = [user for user in users if employment_overlap(user, start, end)]
    if user_ids is None:
        return people
    return [user for user in people if user.id in user_ids]


def format_day_label(iso: str) -> str:
    day = date.fromisoformat(iso)
    return f"{day.strftime('%d.%m.')} {WEEKDAYS[day.weekday()]}"


def format_month_label(month: str) -> str:
    year, mon = (int(part) for part in month.split("-"))
    return f"{MONTHS[mon - 1]} {year}"


def format_de_date(value: date | str) -> str:
    if isinstance(value, str):
        value = date.fromisoformat(value)
    return value.strftime("%d.%m.%Y")


def booking_text(day: dict) -> str:
    punch_parts: list[str] = []
    for punch in day.get("punches") or []:
        if punch.get("voided"):
            continue
        label = PUNCH_LABELS.get(punch.get("kind") or "", punch.get("kind") or "")
        time_text = punch.get("time") or ""
        place = (punch.get("terminal_name") or "").strip()
        punch_parts.append(f"{label} {time_text} ({place})" if place else f"{label} {time_text}".strip())
    punch_line = "  ·  ".join(part for part in punch_parts if part)
    calendar = day.get("calendar") or {}
    absence = day.get("absence") or {}
    label = calendar.get("name") or absence.get("note") or ""
    if not label and absence.get("kind"):
        label = ABSENCE_LABELS.get(absence["kind"], absence["kind"])
    if label and punch_line:
        return f"{label} · {punch_line}"
    if label:
        return label
    if punch_line:
        return punch_line
    if day.get("first_in"):
        end = day.get("last_out") or ("offen" if day.get("open") else "—")
        return f"{day['first_in']} – {end}"
    return "—"


def _add_years(day: date, years: int) -> date:
    try:
        return day.replace(year=day.year + years)
    except ValueError:
        return date(day.year + years, day.month, 28)


def _anniversary_in_year(original: date, year: int) -> date:
    try:
        return original.replace(year=year)
    except ValueError:
        return date(year, original.month, 28)


def _in_period(day: date, start: date, end: date) -> bool:
    return start <= day <= end


def _count_absence_days(
    user: User,
    absences: list[Absence],
    start: date,
    end: date,
    skip: set[date] | None = None,
) -> int:
    overlap = employment_overlap(user, start, end)
    if overlap is None:
        return 0
    lo, hi = overlap
    return sum(
        1
        for row in absences
        if row.user_id == user.id and lo <= row.day <= hi and (not skip or row.day not in skip)
    )


def _vacation_free_days(db: Session, users: list[User], start: date, end: date) -> dict[int, set[date]]:
    """Days that consume no vacation quota: roster weekends plus public holidays."""
    timelines = load_timelines(db, [user.id for user in users])
    frozen_map = load_frozen_map(db, [user.id for user in users])
    day_models = load_day_model_map(db, [user.id for user in users], start, end)
    cal = calendar_map(db, start, end)
    free: dict[int, set[date]] = {}
    for user in users:
        days = set()
        cur = start
        while cur <= end:
            entry = cal.get(cur)
            model = day_models.get((user.id, cur)) or model_for(timelines.get(user.id, []), cur, user.work_model)
            blob = frozen_map.get((user.id, cur.year, cur.month)) or {}
            fields = blob.get(str(model.id)) if model is not None else None
            if isinstance(fields, dict):
                model = overlay_model(model, fields)
            if entry is not None and entry.kind in {"holiday", "company_off"}:
                days.add(cur)
            elif soll_hours(model, cur) <= 0:
                days.add(cur)
            cur += timedelta(days=1)
        free[user.id] = days
    return free


def absence_days_report(
    db: Session,
    kind: str,
    start: date,
    end: date,
    user_ids: set[int] | None = None,
) -> list[dict]:
    people = people_in_range(db, start, end, user_ids)
    year_start, year_end = year_bounds(start.year)
    if end.year != start.year:
        year_end = year_bounds(end.year)[1]
    absences = list(
        db.scalars(select(Absence).where(Absence.kind == kind, Absence.day >= year_start, Absence.day <= max(end, year_end)))
    )
    free: dict[int, set[date]] = {}
    if kind == "vacation":
        free = _vacation_free_days(db, people, min(start, year_start), max(end, year_end))
    rows = []
    for user in people:
        skip = free.get(user.id)
        period_days = _count_absence_days(user, absences, start, end, skip)
        year_days = _count_absence_days(user, absences, year_start, year_end, skip)
        row = {
            "user_id": user.id,
            "display_name": user.display_name,
            "period_days": period_days,
            "year_days": year_days,
        }
        if kind == "sick":
            row["sick_days"] = period_days
        rows.append(row)
    return rows


def sick_days_report(
    db: Session, start: date, end: date, user_ids: set[int] | None = None
) -> list[dict]:
    return absence_days_report(db, "sick", start, end, user_ids)


def vacation_days_report(
    db: Session, start: date, end: date, user_ids: set[int] | None = None
) -> list[dict]:
    return absence_days_report(db, "vacation", start, end, user_ids)


def vacation_planner_report(
    db: Session,
    start: date,
    end: date,
    user_ids: set[int] | None = None,
    as_of: date | None = None,
    today: date | None = None,
) -> dict:
    """Per-day absences of all kinds plus vacation quota per person.

    The quota always refers to the calendar year of ``start``; callers pass
    a month or a year inside a single year.
    """
    from app.accounts import vacation_days

    today = today or as_local(now_utc()).date()
    as_of = as_of or today
    people = people_in_range(db, start, end, user_ids)
    year_start, year_end = year_bounds(start.year)
    rows = list(
        db.scalars(select(Absence).where(Absence.day >= start, Absence.day <= end).order_by(Absence.day))
    )
    vac_year = list(
        db.scalars(
            select(Absence).where(
                Absence.kind == "vacation", Absence.day >= year_start, Absence.day <= year_end
            )
        )
    )
    free = _vacation_free_days(db, people, year_start, year_end)
    cal = calendar_map(db, start, end)
    days_by_user: dict[int, list[dict]] = {}
    for row in rows:
        days_by_user.setdefault(row.user_id, []).append({"day": row.day.isoformat(), "kind": row.kind})
    out = []
    for user in people:
        skip = free.get(user.id, set())
        taken = _count_absence_days(user, vac_year, year_start, min(as_of, year_end), skip)
        planned_from = max(as_of + timedelta(days=1), year_start)
        planned = _count_absence_days(user, vac_year, planned_from, year_end, skip)
        allowance = user.vacation_days_year
        remaining = None
        if allowance is not None:
            booked = vacation_days(db, user.id, year_start, year_end)
            remaining = float(allowance) - taken - planned + booked
        out.append(
            {
                "user_id": user.id,
                "display_name": user.display_name,
                "department_id": user.department_id,
                "department_name": user.department.name if user.department else None,
                "active": bool(user.active),
                "vacation_allowance": allowance,
                "vacation_taken": taken,
                "vacation_planned": planned,
                "vacation_remaining": remaining,
                "days": days_by_user.get(user.id, []),
            }
        )
    return {
        "from": start.isoformat(),
        "to": end.isoformat(),
        "year": start.year,
        "as_of": as_of.isoformat(),
        "calendar": [
            {"day": day.isoformat(), "kind": info.kind, "name": info.name}
            for day, info in sorted(cal.items())
        ],
        "people": out,
    }


def person_month_snapshot(
    db: Session,
    user: User,
    month: str,
    as_of: date | None = None,
    today: date | None = None,
) -> dict | None:
    start, last = month_bounds(month)
    today = today or as_local(now_utc()).date()
    as_of = as_of or today
    hours_until = min(as_of, today)
    prev_last = start - timedelta(days=1)
    year_start, year_end = year_bounds(start.year)
    overlap = employment_overlap(user, start, last)
    if overlap is None:
        return None
    hire = hired_on(user)
    hist_last = max(last, hours_until, year_end)
    if hire > hist_last:
        return None
    from app.accounts import vacation_days
    from app.closings import flex_as_of, month_delta

    flex_prev = flex_as_of(db, user, min(prev_last, hours_until))
    flex_month = month_delta(db, user, start.year, start.month, hours_until)
    days = days_in_range(db, user, year_start, hist_last)
    vac_prev = vac_ytd = vac_year = 0
    sick_prev = sick_ytd = 0
    for summary in days:
        day = date.fromisoformat(str(summary["date"]))
        kind = ((summary.get("absence") or {}) or {}).get("kind") or ""
        if not is_employed(user, day) or day < year_start or day > year_end:
            continue
        if kind == "vacation" and float(summary.get("soll_hours") or 0) <= 0:
            # Weekends and public holidays carry no target hours: booked rows
            # stay visible on the day, but consume no vacation quota.
            continue
        if kind == "vacation":
            vac_year += 1
            if day <= prev_last:
                vac_prev += 1
            if day <= as_of:
                vac_ytd += 1
        elif kind == "sick":
            if day <= prev_last:
                sick_prev += 1
            if day <= as_of:
                sick_ytd += 1
    vac_month = vac_ytd - vac_prev
    vac_planned = vac_year - vac_ytd
    allowance = user.vacation_days_year
    booked_prev = vacation_days(db, user.id, year_start, prev_last)
    booked_year = vacation_days(db, user.id, year_start, year_end)
    remaining_prev = remaining = None
    if allowance is not None:
        remaining_prev = float(allowance) - vac_prev + booked_prev
        remaining = float(allowance) - vac_ytd - vac_planned + booked_year
    return {
        "user_id": user.id,
        "display_name": user.display_name,
        "flex_prev": flex_prev,
        "flex_month": flex_month,
        "flex_total": flex_prev + flex_month,
        "vacation_prev": vac_prev,
        "vacation_month": vac_month,
        "vacation_total": vac_ytd,
        "vacation_future": vac_year,
        "vacation_planned": vac_planned,
        "vacation_allowance": allowance,
        "vacation_remaining_prev": remaining_prev,
        "vacation_remaining": remaining,
        "sick_prev": sick_prev,
        "sick_month": sick_ytd - sick_prev,
        "sick_total": sick_ytd,
    }


def month_balances_report(
    db: Session,
    month: str,
    as_of: date | None = None,
    today: date | None = None,
    user_ids: set[int] | None = None,
) -> list[dict]:
    start, last = month_bounds(month)
    people = people_in_range(db, start, last, user_ids)
    rows = []
    for user in people:
        snapshot = person_month_snapshot(db, user, month, as_of=as_of, today=today)
        if snapshot:
            rows.append(snapshot)
    return rows


def jubilees_report(db: Session, year: int, half: int, user_ids: set[int] | None = None) -> list[dict]:
    start, end = half_bounds(year, half)
    people = people_in_range(db, start, end, user_ids)
    events: list[dict] = []
    for user in people:
        if user.birthday:
            birthday = _anniversary_in_year(user.birthday, year)
            if _in_period(birthday, start, end):
                events.append(
                    {
                        "user_id": user.id,
                        "display_name": user.display_name,
                        "date": birthday.isoformat(),
                        "origin_date": user.birthday.isoformat(),
                        "kind": "birthday",
                        "label": "Geburtstag",
                        "years": year - user.birthday.year,
                    }
                )
        hire = user.hired_on
        if hire:
            anniversary = _anniversary_in_year(hire, year)
            if _in_period(anniversary, start, end) and anniversary >= hire:
                events.append(
                    {
                        "user_id": user.id,
                        "display_name": user.display_name,
                        "date": anniversary.isoformat(),
                        "origin_date": hire.isoformat(),
                        "kind": "hire",
                        "label": "Eintritt",
                        "years": year - hire.year,
                    }
                )
            for mark in JUBILEE_YEARS:
                when = _add_years(hire, mark)
                if _in_period(when, start, end):
                    events.append(
                        {
                            "user_id": user.id,
                            "display_name": user.display_name,
                            "date": when.isoformat(),
                            "origin_date": hire.isoformat(),
                            "kind": f"jubilee_{mark}",
                            "label": f"Jubiläum {mark}",
                            "years": mark,
                        }
                    )
    events.sort(key=lambda row: (row["date"], name_sort_key(row["display_name"]), row["kind"]))
    return events


def _window_bounds(day: date, start_t: time, end_t: time | None) -> tuple[datetime, datetime]:
    tz = ZoneInfo("UTC")
    from app.auth import local_tz

    local = local_tz()
    start = datetime.combine(day, start_t, tzinfo=local)
    if end_t is None:
        end = datetime.combine(day + timedelta(days=1), time(0, 0), tzinfo=local)
    else:
        end = datetime.combine(day, end_t, tzinfo=local)
    return start.astimezone(tz), end.astimezone(tz)


def _overlap_hours(intervals: list[tuple[datetime, datetime]], start: datetime, end: datetime) -> float:
    total = 0.0
    for a, b in intervals:
        lo = max(a, start)
        hi = min(b, end)
        if hi > lo:
            total += (hi - lo).total_seconds() / 3600
    return total


def night_hours_report(db: Session, month: str, now: datetime | None = None, user_ids: set[int] | None = None) -> list[dict]:
    start, last = month_bounds(month)
    people = people_in_range(db, start, last, user_ids)
    q_start, q_end = punches_window_for_month(start, last)
    rows = []
    for user in people:
        punches = list(
            db.scalars(
                select(Punch)
                .where(Punch.user_id == user.id, Punch.server_time >= q_start, Punch.server_time < q_end)
                .order_by(Punch.server_time)
            )
        )
        hours = {"hours_20_24": 0.0, "hours_0_4": 0.0, "hours_4_6": 0.0}
        cur = start
        while cur <= last:
            intervals = work_intervals(punches, cur, now=now)
            for key, start_t, end_t in NIGHT_WINDOWS:
                w0, w1 = _window_bounds(cur, start_t, end_t)
                hours[key] += _overlap_hours(intervals, w0, w1)
            cur += timedelta(days=1)
        band_1 = hours["hours_20_24"]
        band_2 = hours["hours_0_4"]
        band_3 = hours["hours_4_6"]
        rows.append(
            {
                "user_id": user.id,
                "display_name": user.display_name,
                "hours_20_24": band_1,
                "hours_0_4": band_2,
                "hours_4_6": band_3,
                "hours_1_plus_3": band_1 + band_3,
            }
        )
    return rows


def journal_report(db: Session, user: User, month: str) -> dict:
    from app.closings import calc_start

    year, mon = (int(part) for part in month.split("-"))
    _start, last = month_bounds(month)
    days = month_days(db, user, year, mon)
    entry_from = max(_start, calc_start(db, user))
    entry_by_day: dict[str, float] = {}
    if last >= entry_from:
        for row in db.scalars(
            select(AccountEntry).where(
                AccountEntry.user_id == user.id,
                AccountEntry.kind == "time",
                AccountEntry.day >= entry_from,
                AccountEntry.day <= last,
            )
        ):
            key = row.day.isoformat()
            entry_by_day[key] = entry_by_day.get(key, 0.0) + float(row.amount)
    rows: list[dict] = []
    week_work = week_soll = week_delta = 0.0
    month_work = month_soll = month_delta = 0.0
    for index, day in enumerate(days):
        rows.append(
            {
                "type": "day",
                "label": format_day_label(str(day["date"])),
                "booking": booking_text(day),
                "work_hours": float(day["work_hours"] or 0),
                "soll_hours": float(day["soll_hours"] or 0),
                "delta_hours": float(day["delta_hours"] or 0),
            }
        )
        booked = entry_by_day.get(str(day["date"]), 0.0)
        week_work += float(day["work_hours"] or 0)
        week_soll += float(day["soll_hours"] or 0)
        week_delta += float(day["delta_hours"] or 0) + booked
        month_work += float(day["work_hours"] or 0)
        month_soll += float(day["soll_hours"] or 0)
        month_delta += float(day["delta_hours"] or 0) + booked
        nxt = days[index + 1] if index + 1 < len(days) else None
        if day.get("weekday") == 6 or nxt is None:
            rows.append(
                {
                    "type": "week",
                    "label": "Woche",
                    "booking": "",
                    "work_hours": week_work,
                    "soll_hours": week_soll,
                    "delta_hours": week_delta,
                }
            )
            week_work = week_soll = week_delta = 0.0
    rows.append(
        {
            "type": "month",
            "label": "Monat",
            "booking": "",
            "work_hours": month_work,
            "soll_hours": month_soll,
            "delta_hours": month_delta,
        }
    )
    snapshot = person_month_snapshot(db, user, month, as_of=min(last, as_local(now_utc()).date())) or {
        "flex_prev": 0.0,
        "flex_month": 0.0,
        "flex_total": 0.0,
        "vacation_month": 0,
        "vacation_planned": 0,
        "vacation_allowance": user.vacation_days_year,
        "vacation_remaining_prev": None,
        "vacation_remaining": None,
    }
    return {
        "user_id": user.id,
        "display_name": user.display_name,
        "month": month,
        "month_label": format_month_label(month),
        "rows": rows,
        "accounts": {
            "flex_prev": snapshot["flex_prev"],
            "flex_month": snapshot["flex_month"],
            "flex_total": snapshot["flex_total"],
            "vacation_month": snapshot["vacation_month"],
            "vacation_planned": snapshot["vacation_planned"],
            "vacation_allowance": snapshot["vacation_allowance"],
            "vacation_remaining_prev": snapshot["vacation_remaining_prev"],
            "vacation_remaining": snapshot["vacation_remaining"],
        },
    }


def journal_people(db: Session, month: str, user_ids: set[int] | None = None) -> list[User]:
    start, last = month_bounds(month)
    return people_in_range(db, start, last, user_ids)
