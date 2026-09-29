from __future__ import annotations

from sqlalchemy import select

from app.database import SessionLocal
from app.models import Punch, User
from app.punches import record_punch


def _person(client, username: str) -> User:
    models = client.get("/api/hr/work-models").json()
    res = client.post(
        "/api/hr/users",
        json={
            "username": username,
            "display_name": username,
            "role": "employee",
            "work_model_id": models[0]["id"],
            "web_login": False,
        },
    )
    assert res.status_code == 200, res.text
    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.id == res.json()["id"]))
        assert user is not None
        db.expunge(user)
        return user
    finally:
        db.close()


def login(client, username="admin", password="change-me"):
    res = client.post("/api/auth/login", json={"username": username, "password": password})
    assert res.status_code == 200, res.text


def test_same_event_id_returns_same_punch(client):
    login(client)
    user = _person(client, "stempel-eva")
    db = SessionLocal()
    try:
        user = db.merge(user)
        first = record_punch(db, user, "in", source="test", client_event_id="race-eva-1", enforce_state=False)
        second = record_punch(db, user, "in", source="test", client_event_id="race-eva-1", enforce_state=False)
        assert first.id == second.id
        rows = list(
            db.scalars(select(Punch).where(Punch.user_id == user.id, Punch.client_event_id == "race-eva-1"))
        )
        assert len(rows) == 1
    finally:
        db.close()


def test_concurrent_same_event_returns_winner_instead_of_500(client, monkeypatch):
    login(client)
    user = _person(client, "stempel-finn")
    db = SessionLocal()
    try:
        user = db.merge(user)
        winner = record_punch(db, user, "in", source="test", client_event_id="race-finn-1", enforce_state=False)
        real_scalar = db.scalar
        calls = {"n": 0}

        def racy_lookup(statement, *args, **kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                return None  # loser looked before the winner committed
            return real_scalar(statement, *args, **kwargs)

        monkeypatch.setattr(db, "scalar", racy_lookup)
        losers_view = record_punch(
            db, user, "in", source="test", client_event_id="race-finn-1", enforce_state=False
        )
        assert losers_view.id == winner.id
    finally:
        db.close()
