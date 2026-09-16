from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.auth import as_local, now_utc
from app.balance import days_in_range, hired_on, is_employed, month_days
from app.models import Absence, Punch, User
from app.timecalc import punches_window_for_month, work_intervals

JUBILEE_YEARS = (10, 25, 40)
NIGHT_WINDOWS = (
    ("hours_20_24", time(20, 0), None),
    ("hours_0_4", time(0, 0), time(4, 0)),
    ("hours_4_6", time(4, 0), time(6, 0)),
)
VACATION_NOTE = "Urlaub „inkl. Zukunft“ enthält gebuchte Tage nach dem Stichtag im Kalenderjahr."
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
    users = list(db.scalars(select(User).options(selectinload(User.work_model)).order_by(User.display_name)))
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


def _count_absence_days(user: User, absences: list[Absence], start: date, end: date) -> int:
    overlap = employment_overlap(user, start, end)
    if overlap is None:
        return 0
    lo, hi = overlap
    return sum(1 for row in absences if row.user_id == user.id and lo <= row.day <= hi)


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
    rows = []
    for user in people:
        period_days = _count_absence_days(user, absences, start, end)
        year_days = _count_absence_days(user, absences, year_start, year_end)
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


def month_balances_report(
    db: Session,
    month: str,
    as_of: date | None = None,
    today: date | None = None,
) -> list[dict]:
    start, last = month_bounds(month)
    today = today or as_local(now_utc()).date()
    as_of = as_of or today
    hours_until = min(as_of, today)
    prev_last = start - timedelta(days=1)
    year_start, year_end = year_bounds(start.year)
    people = people_in_range(db, start, last)
    rows = []
    for user in people:
        overlap = employment_overlap(user, start, last)
        if overlap is None:
            continue
        hire = hired_on(user)
        hist_last = max(last, hours_until, year_end)
        if hire > hist_last:
            continue
        days = days_in_range(db, user, hire, hist_last)
        flex_prev = flex_month = 0.0
        vac_prev = vac_ytd = vac_year = 0
        sick_prev = sick_ytd = 0
        for summary in days:
            day = date.fromisoformat(str(summary["date"]))
            kind = ((summary.get("absence") or {}) or {}).get("kind") or ""
            if day < start and day <= hours_until:
                flex_prev += float(summary["delta_hours"] or 0)
            elif start <= day <= last and day <= hours_until and is_employed(user, day):
                flex_month += float(summary["delta_hours"] or 0)
            if not is_employed(user, day) or day < year_start or day > year_end:
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
        rows.append(
            {
                "user_id": user.id,
                "display_name": user.display_name,
                "flex_prev": round(flex_prev, 1),
                "flex_month": round(flex_month, 1),
                "flex_total": round(flex_prev + flex_month, 1),
                "vacation_prev": vac_prev,
                "vacation_month": vac_ytd - vac_prev,
                "vacation_total": vac_ytd,
                "vacation_future": vac_year,
                "sick_prev": sick_prev,
                "sick_month": sick_ytd - sick_prev,
                "sick_total": sick_ytd,
            }
        )
    return rows


def jubilees_report(db: Session, year: int, half: int) -> list[dict]:
    start, end = half_bounds(year, half)
    people = people_in_range(db, start, end)
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
    events.sort(key=lambda row: (row["date"], row["display_name"], row["kind"]))
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


def night_hours_report(db: Session, month: str, now: datetime | None = None) -> list[dict]:
    start, last = month_bounds(month)
    people = people_in_range(db, start, last)
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
        band_1 = round(hours["hours_20_24"], 2)
        band_2 = round(hours["hours_0_4"], 2)
        band_3 = round(hours["hours_4_6"], 2)
        rows.append(
            {
                "user_id": user.id,
                "display_name": user.display_name,
                "hours_20_24": band_1,
                "hours_0_4": band_2,
                "hours_4_6": band_3,
                "hours_1_plus_3": round(band_1 + band_3, 2),
            }
        )
    return rows


def journal_report(db: Session, user: User, month: str) -> dict:
    year, mon = (int(part) for part in month.split("-"))
    days = month_days(db, user, year, mon)
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
        week_work += float(day["work_hours"] or 0)
        week_soll += float(day["soll_hours"] or 0)
        week_delta += float(day["delta_hours"] or 0)
        month_work += float(day["work_hours"] or 0)
        month_soll += float(day["soll_hours"] or 0)
        month_delta += float(day["delta_hours"] or 0)
        nxt = days[index + 1] if index + 1 < len(days) else None
        if day.get("weekday") == 6 or nxt is None:
            rows.append(
                {
                    "type": "week",
                    "label": "Woche",
                    "booking": "",
                    "work_hours": round(week_work, 2),
                    "soll_hours": round(week_soll, 2),
                    "delta_hours": round(week_delta, 2),
                }
            )
            week_work = week_soll = week_delta = 0.0
    rows.append(
        {
            "type": "month",
            "label": "Monat",
            "booking": "",
            "work_hours": round(month_work, 2),
            "soll_hours": round(month_soll, 2),
            "delta_hours": round(month_delta, 2),
        }
    )
    return {
        "user_id": user.id,
        "display_name": user.display_name,
        "month": month,
        "month_label": format_month_label(month),
        "rows": rows,
    }


def journal_people(db: Session, month: str, user_ids: set[int] | None = None) -> list[User]:
    start, last = month_bounds(month)
    return people_in_range(db, start, last, user_ids)
