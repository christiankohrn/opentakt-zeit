from __future__ import annotations

from datetime import date
from pathlib import Path

from sqlalchemy import delete, select

from app.auth import as_local
from app.config import get_config
from app.database import SessionLocal
from app.import_punches import pnr_key
from app.models import Absence, Punch, User


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


def test_import_matches_a_leading_zero_in_the_map(client, monkeypatch):
    monkeypatch.setattr("app.routers.booking_import.get_config", lambda: _cfg("secret"))
    user_id = _user_id()
    path = Path(get_config().database_path).resolve().parent / "pnr-map.json"
    path.write_text(f'{{"01046": {user_id}}}\n', encoding="utf-8")
    _cleanup()
    headers = {"Authorization": "Bearer secret"}
    try:
        response = client.post(
            "/api/import/punches",
            json={"punches": [{"pnr": "01046", "event_id": "t-imp-zero", "kind": "in", "at": "2026-10-06T05:49:00"}]},
            headers=headers,
        )
        assert response.status_code == 200, response.text
        assert response.json()["stored"] == 1
        assert response.json()["unknown_pnr"] == 0
    finally:
        _cleanup()


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


def _login_admin(client):
    res = client.post("/api/auth/login", json={"username": "admin", "password": "change-me"})
    assert res.status_code == 200, res.text


def test_import_token_rotation_is_masked_and_hashed(client):
    from app.models import AuditEvent, OrgSettings

    _login_admin(client)
    status = client.get("/api/hr/import")
    assert status.status_code == 200, status.text
    assert status.json()["configured"] is False
    rotated = client.post("/api/hr/import/token")
    assert rotated.status_code == 200, rotated.text
    plaintext = rotated.json()["token"]
    assert len(plaintext) >= 20
    masked = client.get("/api/hr/import")
    assert masked.json()["token"] == ""
    assert masked.json()["configured"] is True
    assert masked.json()["source"] == "db"
    db = SessionLocal()
    try:
        stored = db.get(OrgSettings, 1).import_token
        assert len(stored) == 64 and stored != plaintext
        rotation = db.scalar(select(AuditEvent).where(AuditEvent.action == "import.token").order_by(AuditEvent.id.desc()))
        assert rotation is not None and rotation.payload == "neu"
    finally:
        db.close()
    _map(_user_id())
    _cleanup()
    try:
        ok = client.post(
            "/api/import/punches",
            json={"punches": [{"pnr": "9001", "event_id": "t-imp-rot-1", "kind": "in", "at": "2024-03-01T08:15:00"}]},
            headers={"Authorization": f"Bearer {plaintext}"},
        )
        assert ok.status_code == 200, ok.text
        assert ok.json()["stored"] == 1
    finally:
        _cleanup()
    cleared = client.patch("/api/hr/import", json={"token": ""})
    assert cleared.json()["configured"] is False
    assert client.post("/api/import/punches", json={"punches": []}).status_code == 503


def test_import_batches_and_denials_are_audited(client, monkeypatch):
    import json as jsonlib

    from app.models import AuditEvent

    monkeypatch.setattr("app.routers.booking_import.get_config", lambda: _cfg("secret"))
    headers = {"Authorization": "Bearer secret"}
    _map(_user_id())
    _cleanup()
    try:
        stored = client.post(
            "/api/import/punches",
            json={"punches": [{"pnr": "9001", "event_id": "t-imp-audit-1", "kind": "in", "at": "2024-03-01T08:15:00"}]},
            headers=headers,
        )
        assert stored.json()["stored"] == 1
        db = SessionLocal()
        try:
            row = db.scalar(
                select(AuditEvent).where(AuditEvent.action == "import.punches").order_by(AuditEvent.id.desc())
            )
            assert row is not None
            assert jsonlib.loads(row.payload)["stored"] == 1
            before = row.id
        finally:
            db.close()
        dupe = client.post(
            "/api/import/punches",
            json={"punches": [{"pnr": "9001", "event_id": "t-imp-audit-1", "kind": "in", "at": "2024-03-01T08:15:00"}]},
            headers=headers,
        )
        assert dupe.json()["duplicate"] == 1
        db = SessionLocal()
        try:
            after = db.scalar(select(AuditEvent).where(AuditEvent.action == "import.punches").order_by(AuditEvent.id.desc()))
            assert after.id == before
        finally:
            db.close()
    finally:
        _cleanup()
    denied = client.post("/api/import/punches", json={"punches": []}, headers={"Authorization": "Bearer wrong"})
    assert denied.status_code == 401
    db = SessionLocal()
    try:
        row = db.scalar(select(AuditEvent).where(AuditEvent.action == "import.denied").order_by(AuditEvent.id.desc()))
        assert row is not None and row.entity_id == "punches"
    finally:
        db.close()


def test_import_stores_sick_days_once(client, monkeypatch):
    monkeypatch.setattr("app.routers.booking_import.get_config", lambda: _cfg("secret"))
    user_id = _user_id()
    _map(user_id)
    headers = {"Authorization": "Bearer secret"}
    db = SessionLocal()
    try:
        db.execute(delete(Absence).where(Absence.user_id == user_id, Absence.day.in_([date(2026, 10, 5), date(2026, 10, 6)])))
        admin = db.scalar(select(User).where(User.role == "admin"))
        assert admin is not None
        db.add(Absence(user_id=user_id, day=date(2026, 10, 6), kind="vacation", note="Urlaub", created_by_id=admin.id))
        db.commit()
    finally:
        db.close()
    body = {"days": [{"pnr": "09001", "day": "2026-10-05", "kind": "sick"}, {"pnr": "09001", "day": "2026-10-06", "kind": "sick"}]}
    try:
        first = client.post("/api/import/absences", json=body, headers=headers)
        assert first.status_code == 200, first.text
        assert first.json()["stored"] == 1
        assert first.json()["skipped"] == 1
        second = client.post("/api/import/absences", json=body, headers=headers)
        assert second.json()["stored"] == 0
        assert second.json()["duplicate"] == 1
        assert second.json()["skipped"] == 1
        db = SessionLocal()
        try:
            sick = db.scalar(select(Absence).where(Absence.user_id == user_id, Absence.day == date(2026, 10, 5)))
            kept = db.scalar(select(Absence).where(Absence.user_id == user_id, Absence.day == date(2026, 10, 6)))
            assert sick is not None and sick.kind == "sick" and sick.note is None
            assert kept is not None and kept.kind == "vacation"
        finally:
            db.close()
    finally:
        db = SessionLocal()
        try:
            db.execute(delete(Absence).where(Absence.user_id == user_id, Absence.day.in_([date(2026, 10, 5), date(2026, 10, 6)])))
            db.commit()
        finally:
            db.close()


def test_import_stores_school_vacation_and_comp_time(client, monkeypatch):
    monkeypatch.setattr("app.routers.booking_import.get_config", lambda: _cfg("secret"))
    user_id = _user_id()
    _map(user_id)
    headers = {"Authorization": "Bearer secret"}
    days = [
        date(2026, 10, 12),
        date(2026, 10, 13),
        date(2026, 10, 19),
        date(2026, 6, 29),
    ]
    db = SessionLocal()
    try:
        db.execute(delete(Absence).where(Absence.user_id == user_id, Absence.day.in_(days)))
        db.commit()
    finally:
        db.close()
    body = {
        "days": [
            {"pnr": "09001", "day": "2026-10-12", "kind": "school"},
            {"pnr": "09001", "day": "2026-10-13", "kind": "vacation"},
            {"pnr": "09001", "day": "2026-10-19", "kind": "comp_time"},
            {"pnr": "09001", "day": "2026-06-29", "kind": "special_leave"},
            {"pnr": "09001", "day": "2026-10-19", "kind": "sick"},
        ]
    }
    try:
        first = client.post("/api/import/absences", json=body, headers=headers)
        assert first.status_code == 200, first.text
        assert first.json()["stored"] == 4
        assert first.json()["skipped"] == 1
        db = SessionLocal()
        try:
            rows = {
                row.day: row.kind
                for row in db.scalars(select(Absence).where(Absence.user_id == user_id, Absence.day.in_(days)))
            }
            assert rows[date(2026, 10, 12)] == "school"
            assert rows[date(2026, 10, 13)] == "vacation"
            assert rows[date(2026, 10, 19)] == "comp_time"
            assert rows[date(2026, 6, 29)] == "special_leave"
        finally:
            db.close()
    finally:
        db = SessionLocal()
        try:
            db.execute(delete(Absence).where(Absence.user_id == user_id, Absence.day.in_(days)))
            db.commit()
        finally:
            db.close()


def test_import_failures_are_rate_limited(client, monkeypatch):
    from app.ratelimit import reset as reset_limits

    monkeypatch.setattr("app.routers.booking_import.get_config", lambda: _cfg("secret"))
    reset_limits()
    try:
        for _ in range(30):
            res = client.post("/api/import/punches", json={"punches": []}, headers={"Authorization": "Bearer wrong"})
            assert res.status_code == 401, res.text
        blocked = client.post("/api/import/punches", json={"punches": []}, headers={"Authorization": "Bearer wrong"})
        assert blocked.status_code == 429, blocked.text
    finally:
        reset_limits()
