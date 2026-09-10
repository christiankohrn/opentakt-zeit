from __future__ import annotations

from sqlalchemy import func, select

from app.database import SessionLocal
from app.esp_display import render_line
from app.models import Punch


def login(client, username="admin", password="change-me"):
    res = client.post("/api/auth/login", json={"username": username, "password": password})
    assert res.status_code == 200, res.text
    return res.json()


def users_by_name(client) -> dict:
    res = client.get("/api/hr/users")
    assert res.status_code == 200, res.text
    return {u["username"]: u for u in res.json()}


def punch_count() -> int:
    db = SessionLocal()
    try:
        return int(db.scalar(select(func.count()).select_from(Punch)) or 0)
    finally:
        db.close()


def test_render_line_clips_and_fills_placeholders():
    text = render_line("{first_name} {kind} {flex_month}", {"first_name": "Alexander", "kind": "Kommen", "flex_month": "+12,5h"})
    assert len(text) <= 21
    assert "Alexander" in text


def test_hr_cannot_change_esp_display(client):
    login(client, "personal")
    res = client.patch("/api/hr/esp-terminal", json={"ok_line1": "Hallo"})
    assert res.status_code == 403


def test_esp_punch_requires_secret(client, monkeypatch):
    from app.config import get_config

    cfg = get_config()
    monkeypatch.setattr("app.routers.esp_terminal.get_config", lambda: cfg.model_copy(update={"esp_terminal_secret": ""}))
    res = client.post(
        "/api/terminals/esp/punch",
        json={"badge": "X", "event_id": "abcdefgh"},
        headers={"X-Terminal-Key": "nope"},
    )
    assert res.status_code == 503


def test_esp_punch_rejects_bad_key(client):
    res = client.post(
        "/api/terminals/esp/punch",
        json={"badge": "X", "event_id": "abcdefgh"},
        headers={"X-Terminal-Key": "wrong-secret-key!!"},
    )
    assert res.status_code == 401


def test_esp_punch_unknown_badge(client):
    res = client.post(
        "/api/terminals/esp/punch",
        json={"badge": "NOSUCHCHIP", "event_id": "event-unknown-1"},
        headers={"Authorization": "Bearer test-esp-secret"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["ok"] is False
    assert "Unbekannt" in body["line1"]


def test_esp_punch_auto_kommen_gehen_and_templates(client):
    login(client)
    people = users_by_name(client)
    patched = client.patch(f"/api/hr/users/{people['erika']['id']}/settings", json={"transponder_id": "ESPCHIP"})
    assert patched.status_code == 200, patched.text
    flags = client.patch("/api/hr/esp-terminal", json={"ok_line1": "{first_name}", "ok_line2": "{kind}"})
    assert flags.status_code == 200, flags.text
    assert flags.json()["ok_line2"] == "{kind}"
    before = punch_count()
    first = client.post(
        "/api/terminals/esp/punch",
        json={"badge": "ESPCHIP", "event_id": "esp-event-in-01", "device_id": "dev1"},
        headers={"X-Terminal-Key": "test-esp-secret"},
    )
    assert first.status_code == 200, first.text
    assert first.json()["ok"] is True
    assert first.json()["kind"] in {"in", "out"}
    assert first.json()["line2"] in {"Kommen", "Gehen"}
    second = client.post(
        "/api/terminals/esp/punch",
        json={"badge": "ESPCHIP", "event_id": "esp-event-out-01"},
        headers={"X-Terminal-Key": "test-esp-secret"},
    )
    assert second.status_code == 200, second.text
    assert second.json()["kind"] in {"in", "out"}
    assert second.json()["kind"] != first.json()["kind"]
    assert second.json()["line2"] in {"Kommen", "Gehen"}
    dup = client.post(
        "/api/terminals/esp/punch",
        json={"badge": "ESPCHIP", "event_id": "esp-event-out-01"},
        headers={"X-Terminal-Key": "test-esp-secret"},
    )
    assert dup.status_code == 200, dup.text
    assert dup.json()["ok"] is True
    assert punch_count() == before + 2
