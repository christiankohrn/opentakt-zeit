from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.auth import as_local, now_utc
from app.holidays import calendar_map
from app.models import Absence, Punch, User
from app.timecalc import punches_window_for_month, summarize_day
from app.workmodels import load_timeline, model_for


def hired_on(user: User) -> date:
    if user.hired_on:
        return user.hired_on
    if user.created_at:
        return as_local(user.created_at).date()
    return date(2000, 1, 1)


def is_employed(user: User, day: date) -> bool:
    if day < hired_on(user):
        return False
    if user.left_on is not None and day > user.left_on:
        return False
    return True


def employment_end(user: User, today: date) -> date:
    if user.left_on is not None and user.left_on < today:
        return user.left_on
    return today


def summarize_user_day(user: User, punches, day: date, timeline, absence=None, calendar=None) -> dict:
    employed = is_employed(user, day)
    summary = summarize_day(
        punches,
        day,
        model_for(timeline, day, user.work_model) if employed else None,
        absence=absence,
        auto_break=bool(user.auto_break),
        calendar=calendar,
    )
    if not employed:
        summary["soll_hours"] = 0.0
        summary["delta_hours"] = 0.0
        summary["warnings"] = [w for w in summary["warnings"] if w != "missing_day"]
    return summary


def _flex_sum(days: list[dict], month: str | None = None) -> float:
    total = 0.0
    for d in days:
        if month and not str(d.get("date", "")).startswith(month):
            continue
        total += float(d.get("delta_hours") or 0)
    return round(total, 1)


def days_in_range(db: Session, user: User, start: date, last: date) -> list[dict]:
    if last < start:
        return []
    end = last + timedelta(days=1)
    q_start, q_end = punches_window_for_month(start, last)
    punches = list(
        db.scalars(
            select(Punch)
            .where(Punch.user_id == user.id, Punch.server_time >= q_start, Punch.server_time < q_end)
            .order_by(Punch.server_time)
        )
    )
    absences = {
        a.day: a
        for a in db.scalars(select(Absence).where(Absence.user_id == user.id, Absence.day >= start, Absence.day <= last))
    }
    timeline = load_timeline(db, user.id)
    cal = calendar_map(db, start, last)
    days = []
    cur = start
    while cur < end:
        days.append(
            summarize_user_day(
                user,
                punches,
                cur,
                timeline,
                absence=absences.get(cur),
                calendar=cal.get(cur),
            )
        )
        cur += timedelta(days=1)
    return days


def month_days(db: Session, user: User, year: int, month: int) -> list[dict]:
    start = date(year, month, 1)
    end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    last = end - timedelta(days=1)
    return days_in_range(db, user, start, last)


def account_hours(db: Session, user: User, when=None, month: str | None = None) -> tuple[float, float]:
    if user.work_model is None:
        user = db.scalar(select(User).options(selectinload(User.work_model)).where(User.id == user.id)) or user
    local = as_local(when or now_utc())
    today = local.date()
    start = hired_on(user)
    last = employment_end(user, today)
    if start > last:
        return 0.0, 0.0
    days = days_in_range(db, user, start, last)
    month_key = month or local.strftime("%Y-%m")
    return _flex_sum(days, month_key), _flex_sum(days)


def month_flex_hours(db: Session, user: User, when=None) -> float:
    month, _total = account_hours(db, user, when)
    return month


def format_flex(hours: float) -> str:
    sign = "+" if hours >= 0 else ""
    return f"{sign}{hours:.1f}h".replace(".", ",")
