from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import delete

from app.auth import local_day_bounds
from app.closings import close_one
from app.database import SessionLocal
from app.models import MonthClosing, Punch, User, WorkModel, WorkModelAssignment
from tests.test_closings import login, put_day, users_by_name


def _hours(client, user_id: int, day: date) -> float:
    res = client.get(f"/api/hr/users/{user_id}/days?month={day.strftime('%Y-%m')}")
    assert res.status_code == 200, res.text
    found = next(row for row in res.json()["days"] if row["date"] == day.isoformat())
    return float(found["work_hours"])


def _closed_weekday() -> date:
    day = date.today().replace(day=1) - timedelta(days=1)
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


def test_model_change_keeps_closed_months_and_updates_open_ones(client):
    login(client)
    user_id = users_by_name(client)["mitarbeiter"]["id"]
    closed_day = _closed_weekday()
    open_day = date.today()
    previous_hire = None
    db = SessionLocal()
    try:
        user = db.get(User, user_id)
        assert user is not None
        previous_hire = user.hired_on
        user.hired_on = date(2020, 1, 1)
        db.commit()
    finally:
        db.close()

    created = client.post(
        "/api/hr/work-models",
        json={
            "name": "Rundungstest",
            "kind": "flextime",
            "hours_mon": 8,
            "hours_tue": 8,
            "hours_wed": 8,
            "hours_thu": 8,
            "hours_fri": 8,
            "hours_sat": 8,
            "hours_sun": 8,
        },
    )
    assert created.status_code == 200, created.text
    model_id = created.json()["id"]
    assigned = client.post(
        f"/api/hr/users/{user_id}/work-models",
        json={"work_model_id": model_id, "valid_from": closed_day.replace(day=1).isoformat()},
    )
    assert assigned.status_code == 200, assigned.text
    assignment_id = assigned.json()["id"]
    try:
        for day in (closed_day, open_day):
            stored = put_day(client, user_id, day, "06:24", "14:46")
            assert stored.status_code == 200, stored.text
        db = SessionLocal()
        try:
            user = db.get(User, user_id)
            assert close_one(db, user, closed_day.year, closed_day.month, user_id) >= 1
            db.commit()
        finally:
            db.close()
        before_closed = _hours(client, user_id, closed_day)
        before_open = _hours(client, user_id, open_day)
        updated = client.patch(
            f"/api/hr/work-models/{model_id}",
            json={**created.json(), "round_first_threshold": 2, "round_first_step": 15},
        )
        assert updated.status_code == 200, updated.text
        body = updated.json()
        assert body["closed_months"] >= 1
        assert "offene Monate" in body["notice"]
        assert _hours(client, user_id, closed_day) == before_closed
        assert abs(_hours(client, user_id, open_day) - (before_open - 6 / 60)) < 1e-6
    finally:
        db = SessionLocal()
        try:
            db.execute(delete(MonthClosing).where(MonthClosing.user_id == user_id))
            for day in (closed_day, open_day):
                start, end = local_day_bounds(day)
                db.execute(delete(Punch).where(Punch.user_id == user_id, Punch.server_time >= start, Punch.server_time < end))
            db.execute(delete(WorkModelAssignment).where(WorkModelAssignment.id == assignment_id))
            user = db.get(User, user_id)
            flextime = db.scalar(select_flextime(db))
            if user is not None:
                user.hired_on = previous_hire
                if flextime is not None:
                    user.work_model_id = flextime.id
            db.commit()
        finally:
            db.close()


def select_flextime(db):
    from sqlalchemy import select

    return select(WorkModel).where(WorkModel.kind == "flextime")
