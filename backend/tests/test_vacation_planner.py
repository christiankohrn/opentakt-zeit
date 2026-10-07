from __future__ import annotations

from test_reports import create_person, login


def _planner(client, query: str):
    res = client.get(f"/api/hr/reports/vacation-planner?{query}")
    assert res.status_code == 200, res.text
    return res.json()


def _book(client, user_id: int, kind: str, start: str, end: str):
    res = client.post(
        f"/api/hr/users/{user_id}/absences",
        json={"kind": kind, "start": start, "end": end},
    )
    assert res.status_code == 200, res.text


def test_employee_cannot_read_planner(client):
    login(client)
    create_person(client, "plan-emp", "Plan Emp", web_login=True, password="Geheim-99x")
    client.post("/api/auth/logout")
    login(client, "plan-emp", "Geheim-99x")
    res = client.get("/api/hr/reports/vacation-planner?year=2026")
    assert res.status_code == 403


def test_planner_days_all_kinds_and_quota(client):
    login(client)
    person = create_person(
        client, "plan-eva", "Plan, Eva", hired_on="2025-01-01", vacation_days_year=30
    )
    # 2026-02-02/03 = Mo/Di, 2026-03-07/08 = Sa/So (Wochenende zählt nicht).
    _book(client, person["id"], "vacation", "2026-02-02", "2026-02-03")
    _book(client, person["id"], "vacation", "2026-03-07", "2026-03-08")
    _book(client, person["id"], "sick", "2026-02-10", "2026-02-11")
    _book(client, person["id"], "holiday", "2026-05-15", "2026-05-15")
    _book(client, person["id"], "vacation", "2026-11-16", "2026-11-16")
    correction = client.post(
        f"/api/hr/users/{person['id']}/ledger",
        json={"kind": "vacation", "day": "2026-01-15", "amount": -2, "reason": "Korrektur"},
    )
    assert correction.status_code == 200, correction.text

    body = _planner(
        client,
        f"from=2026-02-01&to=2026-02-28&as_of=2026-06-30&user_ids={person['id']}",
    )
    assert body["from"] == "2026-02-01"
    assert body["to"] == "2026-02-28"
    assert body["year"] == 2026
    assert body["as_of"] == "2026-06-30"
    (row,) = body["people"]
    assert row["display_name"] == "Plan, Eva"
    assert row["vacation_allowance"] == 30
    # Genommen: 2 (Feb) + 0 (März-Wochenende) = 2; geplant: 1 (Nov).
    assert row["vacation_taken"] == 2
    assert row["vacation_planned"] == 1
    assert row["vacation_remaining"] == 25  # 30 - 2 - 1 - 2
    kinds = {(day["day"], day["kind"]) for day in row["days"]}
    assert ("2026-02-02", "vacation") in kinds
    assert ("2026-02-03", "vacation") in kinds
    assert ("2026-02-10", "sick") in kinds
    assert ("2026-02-11", "sick") in kinds
    # März-Urlaub liegt außerhalb des Zeitraums und erscheint nicht.
    assert all(day["day"].startswith("2026-02") for day in row["days"])

    full = _planner(client, f"year=2026&as_of=2026-06-30&user_ids={person['id']}")
    (year_row,) = full["people"]
    assert ("2026-05-15", "holiday") in {(d["day"], d["kind"]) for d in year_row["days"]}
    assert ("2026-11-16", "vacation") in {(d["day"], d["kind"]) for d in year_row["days"]}
    assert year_row["vacation_taken"] == 2
    assert year_row["vacation_planned"] == 1


def test_planner_user_filter_and_calendar(client):
    login(client)
    eva = create_person(client, "plan-eva2", "Plan2, Eva", hired_on="2025-01-01")
    ben = create_person(client, "plan-ben2", "Plan2, Ben", hired_on="2025-01-01")
    _book(client, eva["id"], "vacation", "2026-04-06", "2026-04-06")
    _book(client, ben["id"], "sick", "2026-04-07", "2026-04-07")
    off = client.post(
        "/api/hr/calendar",
        json={"day": "2026-04-08", "kind": "company_off", "name": "Brückentag Firma"},
    )
    assert off.status_code == 200, off.text

    body = _planner(client, f"from=2026-04-01&to=2026-04-30&user_ids={eva['id']}")
    assert [row["display_name"] for row in body["people"]] == ["Plan2, Eva"]
    assert body["people"][0]["days"] == [{"day": "2026-04-06", "kind": "vacation"}]
    calendar = {(day["day"], day["kind"]) for day in body["calendar"]}
    assert ("2026-04-08", "company_off") in calendar

    empty = _planner(client, "from=2026-04-01&to=2026-04-30&user_ids=")
    assert empty["people"] == []

    year_body = _planner(client, f"year=2026&user_ids={eva['id']},{ben['id']}")
    assert len(year_body["people"]) == 2
    law_days = {(day["day"], day["kind"]) for day in year_body["calendar"]}
    assert ("2026-01-01", "holiday") in law_days


def test_planner_rejects_oversize_range(client):
    login(client)
    res = client.get("/api/hr/reports/vacation-planner?from=2026-01-01&to=2027-12-31")
    assert res.status_code == 400
    missing = client.get("/api/hr/reports/vacation-planner")
    assert missing.status_code == 400
