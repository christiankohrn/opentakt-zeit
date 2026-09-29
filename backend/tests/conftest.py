from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

_ROOT = Path(tempfile.mkdtemp(prefix="ze-mail-test-"))
_CFG = _ROOT / "config.toml"
_CFG.write_text(
    f"""
environment = "test"
secret_key = "test-secret-key-mail-suite"
timezone = "Europe/Berlin"
org_name = "Test GmbH"
public_url = "http://test.local"
database_path = "{(_ROOT / "app.db").as_posix()}"
listen_host = "127.0.0.1"
listen_port = 8000
esp_terminal_secret = "test-esp-secret"
""",
    encoding="utf-8",
)
os.environ["ZEITERFASSUNG_CONFIG"] = str(_CFG)

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def outbox(monkeypatch):
    box: list = []

    def fake(_smtp, msg):
        box.append(msg)

    monkeypatch.setattr("app.mail.deliver_message", fake)
    return box


@pytest.fixture(autouse=True)
def _standard_users():
    """Die Suite teilt sich eine Datenbank; der Seed legt nur noch den Admin an.

    Personal/Mitarbeiter für die Tests hier idempotent nachziehen und die
    erzwungene Passwortänderung des Seed-Admins zurücksetzen (der Zwang
    selbst ist in test_seed.py abgedeckt).
    """
    from sqlalchemy import select

    from app.auth import normalize_username
    from app.database import SessionLocal, ensure_schema
    from app.models import Department, User, WorkModel
    from app.security import hash_password
    from app.seed import seed_if_empty

    ensure_schema()
    db = SessionLocal()
    try:
        seed_if_empty(db)
        admin = db.scalar(select(User).where(User.username == normalize_username("admin")))
        assert admin is not None
        admin.must_change_password = False
        flextime = db.scalar(select(WorkModel).where(WorkModel.kind == "flextime"))
        shift = db.scalar(select(WorkModel).where(WorkModel.kind == "shift"))
        produktion = db.scalar(select(Department).where(Department.name == "Produktion"))
        lager = db.scalar(select(Department).where(Department.name == "Lager"))
        wanted = [
            ("personal", "Personal", "personal@localhost", "hr", flextime.id if flextime else None, None),
            ("mitarbeiter", "Max Mustermann", "mitarbeiter@localhost", "employee", flextime.id if flextime else None, produktion.id if produktion else None),
            ("erika", "Erika Schicht", "erika@localhost", "employee", shift.id if shift else None, lager.id if lager else None),
        ]
        for username, display, email, role, model_id, dept_id in wanted:
            if db.scalar(select(User).where(User.username == username)) is None:
                db.add(
                    User(
                        username=username,
                        display_name=display,
                        email=email,
                        password_hash=hash_password("change-me"),
                        role=role,
                        work_model_id=model_id,
                        department_id=dept_id,
                        auth_source="local",
                    )
                )
        db.commit()
    finally:
        db.close()
    yield
