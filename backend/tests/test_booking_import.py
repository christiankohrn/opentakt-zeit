from __future__ import annotations

from pathlib import Path

from sqlalchemy import delete, select

from app.auth import as_local
from app.config import get_config
from app.database import SessionLocal
from app.import_punches import pnr_key
from app.models import Punch, User


def _user_id() -> int:
    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.username == "mitarbeiter"))
        assert user is not None
        return user.id
    finally:
        db.close()


def _map(user_id: int) -> Path:
    path = Path(get_config().database_path).resolve().parent / "pnr-map.json"
    path.write_text(f'{{"9001": {user_id}}}\n', encoding="utf-8")
    return path


def _cleanup() -> None:
    db = SessionLocal()
    try:
        db.execute(delete(Punch).where(Punch.client_event_id.like("t-imp-%")))
        db.commit()
    finally:
        db.close()


def _cfg(token: str):
    return get_config().model_copy(update={"import_token": token})


def test_pnr_key_strips_padding():
    assert pnr_key("01088") == "1088"
    assert pnr_key("1088.000") == "1088"
    assert pnr_key("P0071") == "p0071"


def test_import_disabled_without_token(client):
    response = client.post("/api/import/punches", json={"punches": []})
    assert response.status_code == 503


def test_import_rejects_missing_token(client, monkeypatch):
    monkeypatch.setattr("app.routers.booking_import.get_config", lambda: _cfg("secret"))
    response = client.post("/api/import/punches", json={"punches": []}, headers={"Authorization": "Bearer wrong"})
    assert response.status_code == 401


def test_import_stores_old_time_and_ignores_duplicates(client, monkeypatch):
    monkeypatch.setattr("app.routers.booking_import.get_config", lambda: _cfg("secret"))
    user_id = _user_id()
    _map(user_id)
    _cleanup()
    body = {
        "punches": [
            {
                "pnr": "09001.000",
                "event_id": "t-imp-b",
                "kind": "in",
                "at": "2024-03-01T08:15:00",
            }
        ]
    }
    headers = {"Authorization": "Bearer secret"}
    try:
        first = client.post("/api/import/punches", json=body, headers=headers)
        assert first.status_code == 200
        assert first.json()["stored"] == 1
        second = client.post("/api/import/punches", json=body, headers=headers)
        assert second.json()["duplicate"] == 1
        assert second.json()["stored"] == 0
        db = SessionLocal()
        try:
            punch = db.scalar(select(Punch).where(Punch.client_event_id == "t-imp-b"))
            assert punch is not None
            assert punch.source == "import"
            assert punch.terminal_name == "Import"
            local = as_local(punch.server_time)
            assert local.date().isoformat() == "2024-03-01"
            assert (local.hour, local.minute) == (8, 15)
        finally:
            db.close()
        moved = {
            "punches": [
                {
                    "pnr": "9001",
                    "event_id": "t-imp-b",
                    "kind": "in",
                    "at": "2024-03-01T08:20:00",
                }
            ]
        }
        updated = client.post("/api/import/punches", json=moved, headers=headers)
        assert updated.json()["updated"] == 1
        unknown = client.post(
            "/api/import/punches",
            json={"punches": [{"pnr": "999999", "event_id": "t-imp-x", "kind": "out", "at": "2024-03-01T16:00:00"}]},
            headers=headers,
        )
        assert unknown.json()["unknown_pnr"] == 1
    finally:
        _cleanup()


def test_import_voids_and_keeps_manual_corrections(client, monkeypatch):
    monkeypatch.setattr("app.routers.booking_import.get_config", lambda: _cfg("secret"))
    user_id = _user_id()
    _map(user_id)
    _cleanup()
    headers = {"Authorization": "Bearer secret"}
    try:
        created = client.post(
            "/api/import/punches",
            json={"punches": [{"pnr": "9001", "event_id": "t-imp-e", "kind": "out", "at": "2024-03-01T16:00:00"}]},
            headers=headers,
        )
        assert created.json()["stored"] == 1
        voided = client.post(
            "/api/import/punches",
            json={"punches": [{"pnr": "9001", "event_id": "t-imp-e", "void": True}]},
            headers=headers,
        )
        assert voided.json()["voided"] == 1
        db = SessionLocal()
        try:
            punch = db.scalar(select(Punch).where(Punch.client_event_id == "t-imp-e"))
            assert punch is not None and punch.voided_at is not None
            punch.voided_by_id = user_id
            db.commit()
        finally:
            db.close()
        blocked = client.post(
            "/api/import/punches",
            json={"punches": [{"pnr": "9001", "event_id": "t-imp-e", "kind": "out", "at": "2024-03-01T16:30:00"}]},
            headers=headers,
        )
        assert blocked.json()["manuell"] == 1
        db = SessionLocal()
        try:
            punch = db.scalar(select(Punch).where(Punch.client_event_id == "t-imp-e"))
            assert punch is not None
            assert as_local(punch.server_time).minute == 0
        finally:
            db.close()
    finally:
        _cleanup()


def test_import_requires_map(client, monkeypatch):
    monkeypatch.setattr("app.routers.booking_import.get_config", lambda: _cfg("secret"))
    path = Path(get_config().database_path).resolve().parent / "pnr-map.json"
    if path.exists():
        path.unlink()
    response = client.post(
        "/api/import/punches",
        json={"punches": [{"pnr": "1", "event_id": "t-imp-z", "kind": "in", "at": "2024-03-01T08:00:00"}]},
        headers={"Authorization": "Bearer secret"},
    )
    assert response.status_code == 409
