from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import func, select

from app.database import SessionLocal
from app.dfcom import (
    FakeDfcom,
    booking_schema,
    decode_field,
    list_row_size,
    pack_list_field,
    pack_record,
    parse_record,
    personal_list_schema,
    set_client_factory,
    stempelung_schema,
)
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


def test_parse_booking_record_roundtrip():
    schema = booking_schema()
    when = datetime(2026, 9, 7, 8, 15, 0, tzinfo=ZoneInfo("Europe/Berlin"))
    raw = pack_record(schema, {"badge": "AABBCC", "fn": "1", "timestamp": when})
    parsed = parse_record(raw, {0: schema})
    assert parsed.table.lower() == "booking"
    assert parsed.fields["badge"] == "AABBCC"
    assert parsed.fields["fn"] == "1"
    assert parsed.fields["timestamp"].startswith("2026-09-07T08:15:00")


def test_stempelung_record_kennzeichen_roundtrip():
    schema = stempelung_schema()
    when = datetime(2026, 9, 7, 8, 15, 0, tzinfo=ZoneInfo("Europe/Berlin"))
    raw = pack_record(schema, {"Karte": "CHIP-9", "Kennzeichen": "1", "Datum/Zeit": when})
    parsed = parse_record(raw, {0: schema})
    assert parsed.table.lower() == "stempelung"
    assert parsed.fields["Karte"] == "CHIP-9"
    assert parsed.fields["Kennzeichen"] == "1"
    assert parsed.fields["Datum/Zeit"].startswith("2026-09-07T08:15:00")
    padded = pack_list_field("0", 2)
    assert padded == b"0\x00"


def _unpack_personal(blob: bytes) -> list[dict[str, str]]:
    schema = personal_list_schema()
    size = list_row_size(schema)
    rows: list[dict[str, str]] = []
    if size <= 0 or not blob:
        return rows
    for start in range(0, len(blob), size):
        chunk = blob[start : start + size]
        offset = 0
        row: dict[str, str] = {}
        for item in schema.fields:
            row[item.name] = decode_field(item.type, item.size, chunk[offset : offset + item.size])
            offset += item.size
        rows.append(row)
    return rows


def test_hr_cannot_change_dfcom(client):
    login(client, "personal")
    res = client.patch("/api/hr/dfcom", json={"poll_enabled": True})
    assert res.status_code == 403


def test_dry_run_reads_without_quit_or_punch(client):
    fake = FakeDfcom()
    schema = booking_schema()
    when = datetime(2026, 9, 7, 7, 30, 0, tzinfo=ZoneInfo("Europe/Berlin"))
    fake.records.append(pack_record(schema, {"badge": "CHIP-1", "fn": "1", "timestamp": when}))
    fake.records.append(pack_record(schema, {"badge": "CHIP-1", "fn": "2", "timestamp": when}))
    set_client_factory(lambda: fake)
    try:
        login(client)
        people = users_by_name(client)
        patched = client.patch(
            f"/api/hr/users/{people['mitarbeiter']['id']}/settings",
            json={"transponder_id": "CHIP-1"},
        )
        assert patched.status_code == 200, patched.text
        created = client.post(
            "/api/hr/dfcom/terminals",
            json={"name": "Halle", "host": "192.168.10.20", "port": 8000},
        )
        assert created.status_code == 200, created.text
        flags = client.patch("/api/hr/dfcom", json={"poll_enabled": True, "poll_dry_run": True})
        assert flags.status_code == 200, flags.text
        assert flags.json()["poll_dry_run"] is True
        before = punch_count()
        polled = client.post("/api/hr/dfcom/poll")
        assert polled.status_code == 200, polled.text
        body = polled.json()
        assert body["dry_run"] is True
        assert body["devices"][0]["read"] == 1
        assert body["devices"][0]["preview"] == 1
        assert body["devices"][0]["stored"] == 0
        assert body["devices"][0]["quit"] == 0
        assert fake.quit_count == 0
        assert fake.time_set == []
        assert punch_count() == before
    finally:
        set_client_factory(None)


def test_live_poll_stores_and_confirms(client):
    fake = FakeDfcom()
    schema = booking_schema()
    start = datetime(2026, 9, 7, 8, 0, 0, tzinfo=ZoneInfo("Europe/Berlin"))
    end = datetime(2026, 9, 7, 16, 30, 0, tzinfo=ZoneInfo("Europe/Berlin"))
    fake.records.append(pack_record(schema, {"badge": "CHIP-2", "fn": "1", "timestamp": start}))
    fake.records.append(pack_record(schema, {"badge": "CHIP-2", "fn": "2", "timestamp": end}))
    set_client_factory(lambda: fake)
    try:
        login(client)
        people = users_by_name(client)
        client.patch(f"/api/hr/users/{people['mitarbeiter']['id']}/settings", json={"transponder_id": "CHIP-2"})
        client.post("/api/hr/dfcom/terminals", json={"name": "Tor", "host": "10.0.0.8", "port": 8000})
        client.patch("/api/hr/dfcom", json={"poll_enabled": True, "poll_dry_run": False})
        before = punch_count()
        first = client.post("/api/hr/dfcom/poll")
        assert first.status_code == 200, first.text
        assert first.json()["devices"][0]["stored"] == 2
        assert first.json()["devices"][0]["quit"] == 2
        assert fake.quit_count == 2
        assert fake.time_set
        assert punch_count() == before + 2
        second = client.post("/api/hr/dfcom/poll")
        assert second.json()["devices"][0]["stored"] == 0
        assert punch_count() == before + 2
    finally:
        set_client_factory(None)


def test_unknown_badge_is_confirmed_live_but_not_stored(client):
    fake = FakeDfcom()
    schema = booking_schema()
    when = datetime(2026, 9, 7, 9, 0, 0, tzinfo=ZoneInfo("Europe/Berlin"))
    fake.records.append(pack_record(schema, {"badge": "UNKNOWN", "fn": "1", "timestamp": when}))
    set_client_factory(lambda: fake)
    try:
        login(client)
        client.post("/api/hr/dfcom/terminals", json={"name": "Lager", "host": "10.1.2.3"})
        client.patch("/api/hr/dfcom", json={"poll_dry_run": False, "poll_enabled": True})
        before = punch_count()
        res = client.post("/api/hr/dfcom/poll")
        assert res.status_code == 200, res.text
        device = res.json()["devices"][0]
        assert device["read"] == 1
        assert device["stored"] == 0
        assert device["quit"] == 1
        assert punch_count() == before
    finally:
        set_client_factory(None)


def test_retransmit_does_not_duplicate_punch(client):
    fake = FakeDfcom()
    schema = booking_schema()
    when = datetime(2026, 9, 7, 10, 0, 0, tzinfo=ZoneInfo("Europe/Berlin"))
    fake.records.append(pack_record(schema, {"badge": "CHIP-3", "fn": "1", "timestamp": when}))
    set_client_factory(lambda: fake)
    try:
        login(client)
        people = users_by_name(client)
        client.patch(f"/api/hr/users/{people['mitarbeiter']['id']}/settings", json={"transponder_id": "CHIP-3"})
        client.post("/api/hr/dfcom/terminals", json={"name": "Pforte", "host": "172.16.0.9"})
        client.patch("/api/hr/dfcom", json={"poll_enabled": True, "poll_dry_run": False})
        first = client.post("/api/hr/dfcom/poll")
        assert first.json()["devices"][0]["stored"] == 1
        before = punch_count()
        fake.index = 0
        fake.quit_count = 0
        second = client.post("/api/hr/dfcom/poll")
        assert second.status_code == 200, second.text
        assert second.json()["devices"][0]["stored"] == 0
        assert second.json()["devices"][0]["quit"] == 1
        assert punch_count() == before
    finally:
        set_client_factory(None)


def test_stempelung_poll_stores_kommen_and_gehen(client):
    fake = FakeDfcom(schemas={0: stempelung_schema()})
    schema = stempelung_schema()
    start = datetime(2026, 9, 7, 8, 0, 0, tzinfo=ZoneInfo("Europe/Berlin"))
    end = datetime(2026, 9, 7, 16, 30, 0, tzinfo=ZoneInfo("Europe/Berlin"))
    fake.records.append(pack_record(schema, {"Karte": "CHIP-S", "Kennzeichen": "0", "Datum/Zeit": start}))
    fake.records.append(pack_record(schema, {"Karte": "CHIP-S", "Kennzeichen": "1", "Datum/Zeit": end}))
    set_client_factory(lambda: fake)
    try:
        login(client)
        people = users_by_name(client)
        client.patch(f"/api/hr/users/{people['erika']['id']}/settings", json={"transponder_id": "CHIP-S"})
        client.post("/api/hr/dfcom/terminals", json={"name": "Halle", "host": "10.8.0.4"})
        client.patch("/api/hr/dfcom", json={"poll_enabled": True, "poll_dry_run": False})
        res = client.post("/api/hr/dfcom/poll")
        assert res.status_code == 200, res.text
        assert res.json()["devices"][0]["stored"] == 2
        db = SessionLocal()
        try:
            uid = people["erika"]["id"]
            kinds = [p.kind for p in db.scalars(select(Punch).where(Punch.user_id == uid).order_by(Punch.id)).all()]
        finally:
            db.close()
        assert kinds[-2:] == ["in", "out"]
    finally:
        set_client_factory(None)


def test_dry_run_does_not_write_personal_list(client):
    fake = FakeDfcom()
    fake.list_schemas = {0: personal_list_schema()}
    schema = booking_schema()
    when = datetime(2026, 9, 7, 7, 30, 0, tzinfo=ZoneInfo("Europe/Berlin"))
    fake.records.append(pack_record(schema, {"badge": "CHIP-L", "fn": "1", "timestamp": when}))
    set_client_factory(lambda: fake)
    try:
        login(client)
        people = users_by_name(client)
        client.patch(f"/api/hr/users/{people['mitarbeiter']['id']}/settings", json={"transponder_id": "CHIP-L"})
        client.post("/api/hr/dfcom/terminals", json={"name": "Tor", "host": "10.8.0.5"})
        client.patch("/api/hr/dfcom", json={"poll_enabled": True, "poll_dry_run": True})
        res = client.post("/api/hr/dfcom/poll")
        assert res.status_code == 200, res.text
        assert res.json()["devices"][0]["lists_written"] == 0
        assert fake.written_lists == []
        blocked = client.post("/api/hr/dfcom/lists")
        assert blocked.status_code == 200, blocked.text
        assert "Testbetrieb" in blocked.json()["error"]
        assert fake.written_lists == []
    finally:
        set_client_factory(None)


def test_personal_list_written_when_hash_changes(client):
    fake = FakeDfcom()
    fake.list_schemas = {0: personal_list_schema()}
    schema = booking_schema()
    when = datetime(2026, 9, 7, 8, 0, 0, tzinfo=ZoneInfo("Europe/Berlin"))
    fake.records.append(pack_record(schema, {"badge": "CHIP99", "fn": "1", "timestamp": when}))
    set_client_factory(lambda: fake)
    try:
        login(client)
        people = users_by_name(client)
        client.patch(f"/api/hr/users/{people['mitarbeiter']['id']}/settings", json={"transponder_id": "CHIP99"})
        client.post("/api/hr/dfcom/terminals", json={"name": "Pforte", "host": "10.8.0.6"})
        flags = client.patch("/api/hr/dfcom", json={"poll_enabled": True, "poll_dry_run": False, "sync_lists": True})
        assert flags.status_code == 200, flags.text
        assert flags.json()["sync_lists"] is True
        first = client.post("/api/hr/dfcom/poll")
        assert first.status_code == 200, first.text
        devices = first.json()["devices"]
        assert devices
        assert all(item["lists_written"] == 1 for item in devices)
        assert len(fake.written_lists) == len(devices)
        rows = _unpack_personal(fake.written_lists[-1]["blob"])
        match = next((row for row in rows if row["KARTE"] == "CHIP99"), None)
        assert match is not None
        assert match["NAME"]
        second = client.post("/api/hr/dfcom/poll")
        assert all(item["lists_written"] == 0 for item in second.json()["devices"])
        assert len(fake.written_lists) == len(devices)
        forced = client.post("/api/hr/dfcom/lists")
        assert forced.status_code == 200, forced.text
        assert all(item["lists_written"] == 1 for item in forced.json()["devices"])
        assert len(fake.written_lists) == 2 * len(devices)
    finally:
        set_client_factory(None)
