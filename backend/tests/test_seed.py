from __future__ import annotations

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database import Base
from app.models import User  # noqa: F401
from app.seed import seed_if_empty


def test_seed_creates_only_admin_with_forced_password_change():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        seed_if_empty(db)
        users = list(db.scalars(select(User)))
    assert [u.username for u in users] == ["admin"]
    assert users[0].role == "admin"
    assert users[0].must_change_password is True


def test_forced_password_change_flow(client):
    admin = client.post("/api/auth/login", json={"username": "admin", "password": "change-me"})
    assert admin.status_code == 200, admin.text
    models = client.get("/api/hr/work-models").json()
    created = client.post(
        "/api/hr/users",
        json={
            "username": "wechsel-test",
            "display_name": "Wechsel Test",
            "role": "employee",
            "password": "Wechsel-Start-99",
            "work_model_id": models[0]["id"],
            "web_login": True,
        },
    )
    assert created.status_code == 200, created.text

    from app.database import SessionLocal

    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.username == "wechsel-test"))
        assert user is not None
        user.must_change_password = True
        db.commit()
    finally:
        db.close()

    client.post("/api/auth/logout")
    login = client.post("/api/auth/login", json={"username": "wechsel-test", "password": "Wechsel-Start-99"})
    assert login.status_code == 200, login.text
    assert login.json()["security_setup_required"] == "password"

    blocked = client.get("/api/me/status")
    assert blocked.status_code == 403
    assert "Passwort" in blocked.json()["detail"]
    me = client.get("/api/auth/me")
    assert me.status_code == 200, me.text

    changed = client.post(
        "/api/me/password",
        json={"current_password": "Wechsel-Start-99", "new_password": "Wechsel-Neu-99"},
    )
    assert changed.status_code == 200, changed.text
    assert client.get("/api/me/status").status_code == 200
    assert client.get("/api/auth/me").json()["security_setup_required"] is None
