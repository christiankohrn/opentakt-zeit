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
    assert flex_of(client, day.year, day.month, person["id"]) == 9.5

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
    assert flex_of(client, day.year, day.month, person["id"]) == 11.25

    client.post("/api/auth/logout")
    login(client, "personal", "change-me")
    denied = client.get("/api/hr/closings")
    assert denied.status_code == 403


def test_ledger_from_limits_close_and_import(client, monkeypatch):
    from pathlib import Path

    from sqlalchemy import select

    from app.config import get_config
    from app.database import SessionLocal
    from app.models import MonthClosing

    login(client)
    person = users_by_name(client)["mitarbeiter"]
    day = ended_weekday()
    settings = client.get("/api/hr/settings")
    assert settings.status_code == 200, settings.text
    land = settings.json()["bundesland"]
    try:
        hired = client.patch(f"/api/hr/users/{person['id']}/account", json={"hired_on": "2010-01-01"})
        assert hired.status_code == 200, hired.text
        db = SessionLocal()
        try:
            db.add(MonthClosing(user_id=person["id"], year=2010, month=1, flex_hours=99))
            db.commit()
        finally:
            db.close()
        blocked = client.patch("/api/hr/settings", json={"bundesland": land, "ledger_from": day.isoformat()})
        assert blocked.status_code == 409
        assert blocked.json()["detail"]["code"] == "closed_month"
        saved = client.patch(
            "/api/hr/settings",
            json={"bundesland": land, "ledger_from": day.isoformat(), "confirm_closed": True},
        )
        assert saved.status_code == 200, saved.text
        assert saved.json()["ledger_from"] == day.isoformat()
        db = SessionLocal()
        try:
            old = db.scalar(select(MonthClosing).where(MonthClosing.user_id == person["id"], MonthClosing.year == 2010))
            assert old is None
        finally:
            db.close()

        stored = put_day(client, person["id"], day, "08:00", "16:00")
        assert stored.status_code == 200, stored.text
        closed = client.post("/api/hr/closings", json={"year": day.year, "month": day.month})
        assert closed.status_code == 200, closed.text
        finished = wait_job(client)
        assert finished["error"] is None
        listed = client.get("/api/hr/closings")
        assert listed.status_code == 200, listed.text
        months = listed.json()["months"]
        assert any(row["year"] == day.year and row["month"] == day.month for row in months)
        assert all((row["year"], row["month"]) >= (day.year, day.month) for row in months)
        assert flex_of(client, day.year, day.month, person["id"]) == -0.5

        monkeypatch.setattr(
            "app.routers.booking_import.get_config",
            lambda: get_config().model_copy(update={"import_token": "secret"}),
        )
        path = Path(get_config().database_path).resolve().parent / "pnr-map.json"
        path.write_text(f'{{"9001": {person["id"]}}}\n', encoding="utf-8")
        headers = {"Authorization": "Bearer secret"}
        early = client.post(
            "/api/import/punches",
            json={"punches": [{"pnr": "9001", "event_id": "t-ledger-early", "kind": "in", "at": "2010-06-01T08:00:00"}]},
            headers=headers,
        )
        assert early.status_code == 200, early.text
        assert early.json()["before_ledger"] == 1
        assert early.json()["stored"] == 0
        openings = client.post(
            "/api/import/openings",
            json={"people": [{"pnr": "09001", "hours": 4.5, "on": day.isoformat()}]},
            headers=headers,
        )
        assert openings.status_code == 200, openings.text
        assert openings.json()["updated"] == 1
        again = users_by_name(client)["mitarbeiter"]
        assert again["opening_balance_hours"] == 4.5
        assert again["opening_balance_on"] == day.isoformat()
        assert flex_of(client, day.year, day.month, person["id"]) == 4.0
    finally:
        _reset_person(person["id"], day)
        client.patch("/api/hr/settings", json={"bundesland": land, "ledger_from": None, "confirm_closed": True})
