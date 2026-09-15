from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.auth import as_local, now_utc
from app.balance import hired_on, summarize_user_day
from app.holidays import calendar_map
from app.models import Absence, Punch, User
from app.timecalc import punches_window_for_month, work_intervals
from app.workmodels import load_timelines

JUBILEE_YEARS = (10, 25, 40)
NIGHT_WINDOWS = (
    ("hours_20_24", time(20, 0), None),
    ("hours_0_4", time(0, 0), time(4, 0)),
    ("hours_4_6", time(4, 0), time(6, 0)),
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


def people_in_range(db: Session, start: date, end: date) -> list[User]:
    users = list(db.scalars(select(User).options(selectinload(User.work_model)).order_by(User.display_name)))
    return [user for user in users if employment_overlap(user, start, end)]


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


def sick_days_report(db: Session, year: int) -> list[dict]:
    start, end = year_bounds(year)
    people = people_in_range(db, start, end)
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


def month_balances_report(db: Session, month: str, today: date | None = None) -> list[dict]:
    start, last = month_bounds(month)
    today = today or as_local(now_utc()).date()
    people = people_in_range(db, start, last)
    timelines = load_timelines(db, [user.id for user in people])
    cal = calendar_map(db, start, last)
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
        absences = {
            row.day: row
            for row in db.scalars(
                select(Absence).where(Absence.user_id == user.id, Absence.day >= start, Absence.day <= last)
            )
        }
        work = soll = delta = 0.0
        sick_days = vacation_days = 0
        overlap = employment_overlap(user, start, last)
        if overlap is None:
            continue
        lo, hi = overlap
        cur = start
        while cur <= last:
            summary = summarize_user_day(
                user,
                punches,
                cur,
                timelines.get(user.id, []),
                absence=absences.get(cur),
                calendar=cal.get(cur),
            )
            if lo <= cur <= hi:
                kind = (absences.get(cur).kind if absences.get(cur) is not None else "") or ""
                if kind == "sick":
                    sick_days += 1
                elif kind == "vacation":
                    vacation_days += 1
                if cur <= today:
                    work += float(summary["work_hours"] or 0)
                    soll += float(summary["soll_hours"] or 0)
                    delta += float(summary["delta_hours"] or 0)
            cur += timedelta(days=1)
        rows.append(
            {
                "user_id": user.id,
                "display_name": user.display_name,
                "work_hours": round(work, 2),
                "soll_hours": round(soll, 2),
                "delta_hours": round(delta, 1),
                "sick_days": sick_days,
                "vacation_days": vacation_days,
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
