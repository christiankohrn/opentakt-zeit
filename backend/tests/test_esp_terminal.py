from __future__ import annotations

from datetime import date

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
    monkeypatch.setattr("app.esp_service.get_config", lambda: cfg.model_copy(update={"esp_terminal_secret": ""}))
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
    assert "Secret" in res.json()["detail"]


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


def test_admin_can_set_esp_secret(client):
    login(client)
    shown = client.get("/api/hr/esp-terminal")
    assert shown.status_code == 200, shown.text
    assert shown.json()["secret"] == "test-esp-secret"
    assert shown.json()["secret_source"] == "config"
    saved = client.patch("/api/hr/esp-terminal", json={"secret": "ui-esp-secret-value"})
    assert saved.status_code == 200, saved.text
    assert saved.json()["secret"] == "ui-esp-secret-value"
    assert saved.json()["secret_source"] == "db"
    old = client.post(
        "/api/terminals/esp/punch",
        json={"badge": "X", "event_id": "abcdefgh"},
        headers={"X-Terminal-Key": "test-esp-secret"},
    )
    assert old.status_code == 401
    new = client.post(
        "/api/terminals/esp/punch",
        json={"badge": "NOSUCHCHIP", "event_id": "event-ui-secret1"},
        headers={"X-Terminal-Key": "ui-esp-secret-value"},
    )
    assert new.status_code == 200, new.text
    generated = client.post("/api/hr/esp-terminal/secret")
    assert generated.status_code == 200
    fresh = generated.json()["secret"]
    assert len(fresh) >= 20
    assert fresh != "ui-esp-secret-value"
    reset = client.patch("/api/hr/esp-terminal", json={"secret": ""})
    assert reset.status_code == 200
    assert reset.json()["secret"] == "test-esp-secret"
    assert reset.json()["secret_source"] == "config"


def test_esp_device_named_and_punch_location(client):
    login(client)
    people = users_by_name(client)
    client.patch(f"/api/hr/users/{people['erika']['id']}/settings", json={"transponder_id": "ESPCHIP"})
    hello = client.post(
        "/api/terminals/esp/hello",
        json={"device_id": "aa:bb:cc:dd:ee:ff", "fw": 2, "ssid": "Office", "ip": "10.0.0.8"},
        headers={"X-Terminal-Key": "test-esp-secret"},
    )
    assert hello.status_code == 200, hello.text
    settings = client.get("/api/hr/esp-terminal")
    devices = settings.json()["devices"]
    assert len(devices) == 1
    assert devices[0]["device_id"] == "AABBCCDDEEFF"
    pk = devices[0]["id"]
    named = client.patch(f"/api/hr/esp-terminal/devices/{pk}", json={"name": "Eingang"})
    assert named.status_code == 200
    assert named.json()["name"] == "Eingang"
    punch = client.post(
        "/api/terminals/esp/punch",
        json={"badge": "ESPCHIP", "event_id": "esp-place-in-01", "device_id": "AABBCCDDEEFF", "fw": 2},
        headers={"X-Terminal-Key": "test-esp-secret"},
    )
    assert punch.status_code == 200, punch.text
    assert punch.json()["ok"] is True
    month = client.get(f"/api/hr/users/{people['erika']['id']}/days?month={date.today().strftime('%Y-%m')}")
    assert month.status_code == 200, month.text
    found = None
    for day in month.json()["days"]:
        for row in day["punches"]:
            if not row["voided"]:
                found = row
    assert found is not None
    assert found["device_id"] == "AABBCCDDEEFF"
    assert found["terminal_name"] == "Eingang"


def test_esp_hello_offers_firmware_and_wifi(client):
    login(client)
    hello = client.post(
        "/api/terminals/esp/hello",
        json={"device_id": "112233445566", "fw": 1},
        headers={"X-Terminal-Key": "test-esp-secret"},
    )
    assert hello.status_code == 200, hello.text
    assert hello.json()["firmware_url"] == ""
    settings = client.get("/api/hr/esp-terminal")
    pk = next(d["id"] for d in settings.json()["devices"] if d["device_id"] == "112233445566")
    client.patch(
        f"/api/hr/esp-terminal/devices/{pk}",
        json={"wifi_ssid": "Werkstatt", "wifi_pass": "secret-wlan"},
    )
    again = client.post(
        "/api/terminals/esp/hello",
        json={"device_id": "112233445566", "fw": 1},
        headers={"X-Terminal-Key": "test-esp-secret"},
    )
    assert again.json()["wifi_ssid"] == "Werkstatt"
    assert again.json()["wifi_pass"] == "secret-wlan"
    fake = b"\xe9" + b"\x00" * 64
    uploaded = client.post(
        "/api/hr/esp-terminal/firmware",
        data={"version": "3"},
        files={"file": ("firmware.bin", fake, "application/octet-stream")},
    )
    assert uploaded.status_code == 200, uploaded.text
    assert uploaded.json()["firmware_version"] == 3
    assert uploaded.json()["firmware_uploaded"] is True
    offer = client.post(
        "/api/terminals/esp/hello",
        json={"device_id": "112233445566", "fw": 1},
        headers={"X-Terminal-Key": "test-esp-secret"},
    )
    assert offer.json()["fw"] == 3
    assert offer.json()["firmware_url"].endswith("/api/terminals/esp/firmware.bin")
    dl = client.get("/api/terminals/esp/firmware.bin", headers={"X-Terminal-Key": "test-esp-secret"})
    assert dl.status_code == 200
    assert dl.content[:1] == b"\xe9"
    denied = client.get("/api/terminals/esp/firmware.bin")
    assert denied.status_code in {401, 503}


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
