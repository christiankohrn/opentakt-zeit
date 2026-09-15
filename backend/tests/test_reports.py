from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.database import SessionLocal
from app.models import Punch
from app.reports import jubilees_report, month_balances_report
from app.timecalc import work_intervals


def login(client, username="admin", password="change-me"):
    res = client.post("/api/auth/login", json={"username": username, "password": password})
    assert res.status_code == 200, res.text
    return res.json()


def users_by_name(client) -> dict:
    res = client.get("/api/hr/users")
    assert res.status_code == 200, res.text
    return {u["username"]: u for u in res.json()}


def model_id(client) -> int:
    models = client.get("/api/hr/work-models").json()
    return models[0]["id"]


def create_person(client, username: str, display_name: str, **extra):
    body = {
        "username": username,
        "display_name": display_name,
        "role": "employee",
        "work_model_id": model_id(client),
        "web_login": False,
        **extra,
    }
    res = client.post("/api/hr/users", json=body)
    assert res.status_code == 200, res.text
    return res.json()


def test_employee_cannot_read_reports(client):
    login(client)
    create_person(
        client,
        "report-emp",
        "Report Emp",
        web_login=True,
        password="Geheim-99x",
    )
    client.post("/api/auth/logout")
    login(client, "report-emp", "Geheim-99x")
    res = client.get("/api/hr/reports/sick-days?year=2026")
    assert res.status_code == 403


def test_sick_days_includes_zeros_and_skips_unemployed(client):
    login(client)
    sick = create_person(client, "krank-anna", "Anna Krank", hired_on="2025-01-01")
    zero = create_person(client, "gesund-ben", "Ben Gesund", hired_on="2025-01-01")
    create_person(client, "alina-alt", "Alina Alt", hired_on="2020-01-01", left_on="2025-06-01")
    create_person(client, "zara-neu", "Zara Zukunft", hired_on="2027-01-01")
    added = client.post(
        f"/api/hr/users/{sick['id']}/absences",
        json={"kind": "sick", "start": "2026-03-02", "end": "2026-03-04"},
    )
    assert added.status_code == 200, added.text
    res = client.get("/api/hr/reports/sick-days?year=2026")
    assert res.status_code == 200, res.text
    by_name = {row["display_name"]: row["sick_days"] for row in res.json()["people"]}
    assert by_name["Anna Krank"] == 3
    assert by_name["Ben Gesund"] == 0
    assert "Alina Alt" not in by_name
    assert "Zara Zukunft" not in by_name
    csv_res = client.get("/api/hr/reports/sick-days.csv?year=2026")
    assert csv_res.status_code == 200
    text = csv_res.text
    assert "Krankheitstage" in text
    assert "Anna Krank;3" in text
    assert zero["id"]


def test_month_balances_count_future_vacation(client):
    login(client)
    person = create_person(client, "urlaub-clara", "Clara Urlaub", hired_on="2025-01-01")
    booked = client.post(
        f"/api/hr/users/{person['id']}/absences",
        json={"kind": "vacation", "start": "2026-09-28", "end": "2026-09-28"},
    )
    assert booked.status_code == 200, booked.text
    sick = client.post(
        f"/api/hr/users/{person['id']}/absences",
        json={"kind": "sick", "start": "2026-09-03", "end": "2026-09-03"},
    )
    assert sick.status_code == 200, sick.text
    db = SessionLocal()
    try:
        rows = month_balances_report(db, "2026-09", today=date(2026, 9, 15))
    finally:
        db.close()
    clara = next(row for row in rows if row["user_id"] == person["id"])
    assert clara["vacation_days"] == 1
    assert clara["sick_days"] == 1
    http = client.get("/api/hr/reports/month-balances?month=2026-09")
    assert http.status_code == 200
    found = next(row for row in http.json()["people"] if row["user_id"] == person["id"])
    assert found["vacation_days"] == 1


def test_jubilees_birthday_and_ten_year(client):
    login(client)
    person = create_person(
        client,
        "jubi-dana",
        "Dana Jubiläum",
        hired_on="2016-09-01",
        birthday="1990-03-12",
    )
    none = create_person(client, "ohne-geburt", "Otto Ohne", hired_on="2016-09-01")
    hj1 = client.get("/api/hr/reports/jubilees?year=2026&half=1")
    assert hj1.status_code == 200, hj1.text
    events = hj1.json()["events"]
    birthday = next(row for row in events if row["user_id"] == person["id"] and row["kind"] == "birthday")
    assert birthday["date"] == "2026-03-12"
    assert birthday["years"] == 36
    assert not any(row["user_id"] == none["id"] and row["kind"] == "birthday" for row in events)

    hj2 = client.get("/api/hr/reports/jubilees?year=2026&half=2")
    assert hj2.status_code == 200, hj2.text
    later = hj2.json()["events"]
    assert not any(row["user_id"] == person["id"] and row["kind"] == "birthday" for row in later)
    ten = next(row for row in later if row["user_id"] == person["id"] and row["kind"] == "jubilee_10")
    assert ten["date"] == "2026-09-01"
    assert ten["years"] == 10
    hire = next(row for row in later if row["user_id"] == person["id"] and row["kind"] == "hire")
    assert hire["date"] == "2026-09-01"
    assert hire["years"] == 10
    db = SessionLocal()
    try:
        rows = jubilees_report(db, 2026, 2)
    finally:
        db.close()
    assert any(row["kind"] == "jubilee_10" and row["user_id"] == person["id"] for row in rows)


def test_night_hours_overnight_shift(client):
    login(client)
    people = users_by_name(client)
    erika = people["erika"]
    hired = client.patch(f"/api/hr/users/{erika['id']}/account", json={"hired_on": "2026-01-01"})
    assert hired.status_code == 200, hired.text
    first = client.put(
        f"/api/hr/users/{erika['id']}/days/2026-08-07",
        json={"reason": "Nachtschicht anlegen", "punches": [{"kind": "in", "time": "22:00"}]},
    )
    assert first.status_code == 200, first.text
    second = client.put(
        f"/api/hr/users/{erika['id']}/days/2026-08-08",
        json={"reason": "Nachtschicht anlegen", "punches": [{"kind": "out", "time": "06:00"}]},
    )
    assert second.status_code == 200, second.text
    res = client.get("/api/hr/reports/night-hours?month=2026-08")
    assert res.status_code == 200, res.text
    row = next(item for item in res.json()["people"] if item["user_id"] == erika["id"])
    assert abs(row["hours_20_24"] - 2.0) < 0.05
    assert abs(row["hours_0_4"] - 4.0) < 0.05
    assert abs(row["hours_4_6"] - 2.0) < 0.05
    assert abs(row["hours_1_plus_3"] - 4.0) < 0.05
    csv_res = client.get("/api/hr/reports/night-hours.csv?month=2026-08")
    assert csv_res.status_code == 200
    assert "20-24" in csv_res.text


def test_work_intervals_split_overnight():
    punches = [
        Punch(
            user_id=1,
            kind="in",
            server_time=datetime(2026, 8, 7, 22, 0, tzinfo=ZoneInfo("Europe/Berlin")).astimezone(ZoneInfo("UTC")),
            source="test",
        ),
        Punch(
            user_id=1,
            kind="out",
            server_time=datetime(2026, 8, 8, 6, 0, tzinfo=ZoneInfo("Europe/Berlin")).astimezone(ZoneInfo("UTC")),
            source="test",
        ),
    ]
    now = datetime(2026, 8, 9, tzinfo=ZoneInfo("UTC"))
    night = work_intervals(punches, date(2026, 8, 7), now=now)
    morning = work_intervals(punches, date(2026, 8, 8), now=now)
    night_hours = sum((b - a).total_seconds() for a, b in night) / 3600
    morning_hours = sum((b - a).total_seconds() for a, b in morning) / 3600
    assert abs(night_hours - 2.0) < 0.05
    assert abs(morning_hours - 6.0) < 0.05
