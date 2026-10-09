from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import delete

from app.auth import local_day_bounds
from app.closings import close_one, month_end
from app.database import SessionLocal
from app.models import AccountEntry, MonthClosing, Punch, User
from tests.test_closings import flex_of, login, put_day, users_by_name


def _ended_weekday() -> date:
    today = date.today()
    end = today.replace(day=1) - timedelta(days=1)
    day = end
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


def _count_weekdays(start: date, end: date) -> int:
    return sum(1 for n in range((end - start).days + 1) if (start + timedelta(days=n)).weekday() < 5)


def _reset_user(user_id: int, days: list[date]) -> None:
    db = SessionLocal()
    try:
        user = db.get(User, user_id)
        if user is not None:
            user.hired_on = None
            user.opening_balance_hours = 0
            user.opening_balance_on = None
            user.flex_cap_hours = None
            user.skip_flex_on_close = False
        db.execute(delete(MonthClosing).where(MonthClosing.user_id == user_id))
        db.execute(
            delete(AccountEntry).where(
                AccountEntry.user_id == user_id,
                AccountEntry.reason.like("Automatische Kappung%"),
            )
        )
        db.execute(
            delete(AccountEntry).where(
                AccountEntry.user_id == user_id,
                AccountEntry.reason.like("Vortrag aus Kappung%"),
            )
        )
        for day in days:
            start, end = local_day_bounds(day)
            db.execute(
                delete(Punch).where(
                    Punch.user_id == user_id,
                    Punch.server_time >= start,
                    Punch.server_time < end,
                )
            )
        db.commit()
    finally:
        db.close()


def _time_entries(client, user_id: int, year: int) -> list[dict]:
    res = client.get(f"/api/hr/users/{user_id}/ledger?year={year}")
    assert res.status_code == 200, res.text
    return res.json()["time_entries"]


def _cap_entries(client, user_id: int, year: int) -> list[dict]:
    return [e for e in _time_entries(client, user_id, year) if e["reason"].startswith("Automatische Kappung")]


def _vortrag_entries(client, user_id: int, year: int) -> list[dict]:
    return [e for e in _time_entries(client, user_id, year) if e["reason"].startswith("Vortrag aus Kappung")]


def _close_month(year: int, month: int, user_id: int) -> int:
    """Schließt nur diese eine Person ab, damit andere Suite-Benutzer unberührt bleiben."""
    db = SessionLocal()
    try:
        user = db.get(User, user_id)
        assert user is not None
        written = close_one(db, user, year, month, user_id)
        db.commit()
        return written
    finally:
        db.close()


def test_close_books_cap_correction(client):
    login(client)
    person = users_by_name(client)["mitarbeiter"]
    day = _ended_weekday()
    try:
        account = client.patch(
            f"/api/hr/users/{person['id']}/account",
            json={
                "hired_on": day.replace(day=1).isoformat(),
                "opening_balance_hours": 40,
                "opening_balance_on": day.isoformat(),
                "flex_cap_hours": 30,
            },
        )
        assert account.status_code == 200, account.text
        assert account.json()["flex_cap_hours"] == 30

        stored = put_day(client, person["id"], day, "08:00", "16:00")
        assert stored.status_code == 200, stored.text

        _close_month(day.year, day.month, person["id"])
        assert flex_of(client, day.year, day.month, person["id"]) == pytest.approx(30.0)

        last_day = month_end(day.year, day.month)
        first_next = last_day + timedelta(days=1)
        entries = _cap_entries(client, person["id"], day.year)
        assert len(entries) == 1
        assert entries[0]["day"] == last_day.isoformat()
        assert entries[0]["amount"] == pytest.approx(-9.5)
        carried = _vortrag_entries(client, person["id"], first_next.year)
        assert len(carried) == 1
        assert carried[0]["day"] == first_next.isoformat()
        assert carried[0]["amount"] == pytest.approx(9.5)

        # Erneuter Abschluss legt keine zweite Korrektur an.
        assert _close_month(day.year, day.month, person["id"]) == 0
        assert len(_cap_entries(client, person["id"], day.year)) == 1
        assert len(_vortrag_entries(client, person["id"], first_next.year)) == 1
    finally:
        _reset_user(person["id"], [day])


def test_close_keeps_balance_below_cap(client):
    login(client)
    person = users_by_name(client)["mitarbeiter"]
    day = _ended_weekday()
    try:
        account = client.patch(
            f"/api/hr/users/{person['id']}/account",
            json={
                "hired_on": day.replace(day=1).isoformat(),
                "opening_balance_hours": 10,
                "opening_balance_on": day.isoformat(),
                "flex_cap_hours": 30,
            },
        )
        assert account.status_code == 200, account.text

        stored = put_day(client, person["id"], day, "08:00", "16:00")
        assert stored.status_code == 200, stored.text

        _close_month(day.year, day.month, person["id"])
        assert flex_of(client, day.year, day.month, person["id"]) == pytest.approx(9.5)
        assert _cap_entries(client, person["id"], day.year) == []
        assert _vortrag_entries(client, person["id"], day.year) == []
    finally:
        _reset_user(person["id"], [day])


def test_close_without_cap_keeps_balance(client):
    login(client)
    person = users_by_name(client)["mitarbeiter"]
    day = _ended_weekday()
    try:
        account = client.patch(
            f"/api/hr/users/{person['id']}/account",
            json={
                "hired_on": day.replace(day=1).isoformat(),
                "opening_balance_hours": 40,
                "opening_balance_on": day.isoformat(),
                "flex_cap_hours": None,
            },
        )
        assert account.status_code == 200, account.text
        assert account.json()["flex_cap_hours"] is None

        stored = put_day(client, person["id"], day, "08:00", "16:00")
        assert stored.status_code == 200, stored.text

        _close_month(day.year, day.month, person["id"])
        assert flex_of(client, day.year, day.month, person["id"]) == pytest.approx(39.5)
        assert _cap_entries(client, person["id"], day.year) == []
        assert _vortrag_entries(client, person["id"], day.year) == []
    finally:
        _reset_user(person["id"], [day])


def test_cap_rejects_negative(client):
    login(client)
    person = users_by_name(client)["mitarbeiter"]
    res = client.patch(f"/api/hr/users/{person['id']}/account", json={"flex_cap_hours": -5})
    assert res.status_code == 422


def test_cap_applies_to_each_closed_month(client):
    login(client)
    person = users_by_name(client)["mitarbeiter"]
    day_m = _ended_weekday()
    first_m = day_m.replace(day=1)
    last_p = first_m - timedelta(days=1)
    day_p = last_p
    while day_p.weekday() >= 5:
        day_p -= timedelta(days=1)
    try:
        account = client.patch(
            f"/api/hr/users/{person['id']}/account",
            json={
                "hired_on": last_p.replace(day=1).isoformat(),
                "opening_balance_hours": 50,
                "opening_balance_on": day_p.isoformat(),
                "flex_cap_hours": 30,
            },
        )
        assert account.status_code == 200, account.text

        for day in (day_p, day_m):
            stored = put_day(client, person["id"], day, "08:00", "16:00")
            assert stored.status_code == 200, stored.text

        _close_month(day_m.year, day_m.month, person["id"])
        assert flex_of(client, last_p.year, last_p.month, person["id"]) == pytest.approx(30.0)
        # Startsaldo plus gearbeitete Tage (je -0,5) und je -8 für die übrigen
        # Wochentage ohne Stempel. Korrektur und Vortrag des Vormonats heben
        # sich hier auf, der Folgemonat rechnet mit dem ungekürzten Verlauf.
        expected_m = 50.0 - 1.0 - 8.0 * (_count_weekdays(first_m, month_end(day_m.year, day_m.month)) - 1)
        assert flex_of(client, day_m.year, day_m.month, person["id"]) == pytest.approx(expected_m)

        years = {day_p.year, day_m.year}
        entries = [e for year in years for e in _cap_entries(client, person["id"], year)]
        assert len(entries) == 1
        assert entries[0]["day"] == month_end(last_p.year, last_p.month).isoformat()
        assert entries[0]["amount"] == pytest.approx(-19.5)
        carried = [e for year in years for e in _vortrag_entries(client, person["id"], year)]
        assert len(carried) == 1
        assert carried[0]["day"] == first_m.isoformat()
        assert carried[0]["amount"] == pytest.approx(19.5)
    finally:
        _reset_user(person["id"], [day_p, day_m])


def test_close_stores_zero_when_time_account_is_skipped(client):
    login(client)
    person = users_by_name(client)["mitarbeiter"]
    day = _ended_weekday()
    try:
        account = client.patch(
            f"/api/hr/users/{person['id']}/account",
            json={
                "hired_on": day.replace(day=1).isoformat(),
                "opening_balance_hours": 10,
                "opening_balance_on": day.isoformat(),
                "flex_cap_hours": 30,
                "skip_flex_on_close": True,
            },
        )
        assert account.status_code == 200, account.text
        assert account.json()["skip_flex_on_close"] is True

        stored = put_day(client, person["id"], day, "08:00", "16:00")
        assert stored.status_code == 200, stored.text

        _close_month(day.year, day.month, person["id"])
        assert flex_of(client, day.year, day.month, person["id"]) == 0
        assert _time_entries(client, person["id"], day.year) == []
        assert _time_entries(client, person["id"], day.year + 1) == []
    finally:
        _reset_user(person["id"], [day])
