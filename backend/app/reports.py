from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.auth import as_local, now_utc
from app.balance import days_in_range, hired_on, month_days
from app.models import Absence, Punch, User
from app.timecalc import punches_window_for_month, work_intervals

JUBILEE_YEARS = (10, 25, 40)
NIGHT_WINDOWS = (
    ("hours_20_24", time(20, 0), None),
    ("hours_0_4", time(0, 0), time(4, 0)),
    ("hours_4_6", time(4, 0), time(6, 0)),
)
VACATION_NOTE = "Urlaubstage nach dem Stichtag stehen in der Spalte „Urlaub geplant“."
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


def sick_days_report(
    db: Session, start: date, end: date, user_ids: set[int] | None = None
) -> list[dict]:
    people = people_in_range(db, start, end, user_ids)
    absences = list(
        db.scalars(select(Absence).where(Absence.kind == "sick", Absence.day >= start, Absence.day <= end))
    )
    counts: dict[int, int] = {user.id: 0 for user in people}
    by_user: dict[int, User] = {user.id: user for user in people}
    for row in absences:
        user = by_user.get(row.user_id)
        if user is None:
            continue
        overlap = employment_overlap(user, start, end)
        if overlap is None:
            continue
        lo, hi = overlap
        if lo <= row.day <= hi:
            counts[user.id] += 1
    return [
        {"user_id": user.id, "display_name": user.display_name, "sick_days": counts[user.id]} for user in people
    ]


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
    people = people_in_range(db, start, last)
    rows = []
    for user in people:
        overlap = employment_overlap(user, start, last)
        if overlap is None:
            continue
        lo, hi = overlap
        hire = hired_on(user)
        hist_last = max(last, hours_until)
        if hire > hist_last:
            continue
        days = days_in_range(db, user, hire, hist_last)
        work = soll = delta = carry = 0.0
        sick_days = vacation_days = vacation_planned_days = 0
        for summary in days:
            day = date.fromisoformat(str(summary["date"]))
            kind = ((summary.get("absence") or {}) or {}).get("kind") or ""
            if day < start:
                if day <= hours_until:
                    carry += float(summary["delta_hours"] or 0)
                continue
            if day > last:
                continue
            if lo <= day <= hi:
                if kind == "sick":
                    sick_days += 1
                elif kind == "vacation":
                    if day <= as_of:
                        vacation_days += 1
                    else:
                        vacation_planned_days += 1
                if day <= hours_until:
                    work += float(summary["work_hours"] or 0)
                    soll += float(summary["soll_hours"] or 0)
                    delta += float(summary["delta_hours"] or 0)
        rows.append(
            {
                "user_id": user.id,
                "display_name": user.display_name,
                "work_hours": round(work, 2),
                "soll_hours": round(soll, 2),
                "delta_hours": round(delta, 1),
                "carry_hours": round(carry, 1),
                "total_hours": round(carry + delta, 1),
                "sick_days": sick_days,
                "vacation_days": vacation_days,
                "vacation_planned_days": vacation_planned_days,
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
