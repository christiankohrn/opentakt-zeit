from __future__ import annotations

import time
from datetime import date, timedelta


def login(client, username="admin", password="change-me"):
    res = client.post("/api/auth/login", json={"username": username, "password": password})
    assert res.status_code == 200, res.text
    return res.json()


def users_by_name(client) -> dict:
    res = client.get("/api/hr/users")
    assert res.status_code == 200, res.text
    return {u["username"]: u for u in res.json()}


def ended_weekday() -> date:
    today = date.today()
    end = today.replace(day=1) - timedelta(days=1)
    day = end
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


def put_day(client, user_id: int, day: date, start: str, end: str, confirm: bool = False):
    return client.put(
        f"/api/hr/users/{user_id}/days/{day.isoformat()}",
        json={
            "reason": "Testkorrektur",
            "punches": [{"kind": "in", "time": start}, {"kind": "out", "time": end}],
            "confirm_closed": confirm,
        },
    )


def wait_job(client) -> dict:
    last = {}
    for _ in range(100):
        res = client.get("/api/hr/closings/job")
        assert res.status_code == 200, res.text
        last = res.json()
        if not last["running"]:
            return last
        time.sleep(0.05)
    raise AssertionError(last)


def flex_of(client, year: int, month: int, user_id: int) -> float:
    detail = client.get(f"/api/hr/closings/{year}/{month}")
    assert detail.status_code == 200, detail.text
    people = {row["user_id"]: row for row in detail.json()["people"]}
    return people[user_id]["flex_hours"]


def _reset_person(user_id: int, day: date) -> None:
    from sqlalchemy import delete

    from app.auth import local_day_bounds
    from app.database import SessionLocal
    from app.models import MonthClosing, Punch, User

    start, end = local_day_bounds(day)
    db = SessionLocal()
    try:
        user = db.get(User, user_id)
        if user is not None:
            user.hired_on = None
            user.opening_balance_hours = 0
            user.opening_balance_on = None
        db.execute(delete(MonthClosing).where(MonthClosing.user_id == user_id))
        db.execute(delete(Punch).where(Punch.user_id == user_id, Punch.server_time >= start, Punch.server_time < end))
        db.commit()
    finally:
        db.close()


def test_close_warns_and_recalculates(client):
    login(client)
    person = users_by_name(client)["mitarbeiter"]
    day = ended_weekday()
    try:
        _run_close(client, person, day)
    finally:
        _reset_person(person["id"], day)


def _run_close(client, person, day: date) -> None:
    month_start = day.replace(day=1)
    account = client.patch(
        f"/api/hr/users/{person['id']}/account",
        json={
            "hired_on": month_start.isoformat(),
            "opening_balance_hours": 10,
            "opening_balance_on": day.isoformat(),
        },
    )
    assert account.status_code == 200, account.text
    assert account.json()["opening_balance_hours"] == 10

    stored = put_day(client, person["id"], day, "08:00", "16:00")
    assert stored.status_code == 200, stored.text

    closed = client.post("/api/hr/closings", json={"year": day.year, "month": day.month})
    assert closed.status_code == 200, closed.text
    finished = wait_job(client)
    assert finished["error"] is None
    assert finished["rows"] >= 1
    assert flex_of(client, day.year, day.month, person["id"]) == 10

    listed = client.get("/api/hr/closings")
    assert listed.status_code == 200
    assert any(row["year"] == day.year and row["month"] == day.month for row in listed.json()["months"])

    sheet = client.get(f"/api/hr/users/{person['id']}/days?month={day.year:04d}-{day.month:02d}")
    assert sheet.status_code == 200
    assert sheet.json()["closed"] is True

    blocked = put_day(client, person["id"], day, "08:00", "18:00")
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "closed_month"

    confirmed = put_day(client, person["id"], day, "08:00", "18:00", confirm=True)
    assert confirmed.status_code == 200, confirmed.text
    assert flex_of(client, day.year, day.month, person["id"]) == 12

    client.post("/api/auth/logout")
    login(client, "personal", "change-me")
    denied = client.get("/api/hr/closings")
    assert denied.status_code == 403
