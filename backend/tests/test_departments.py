from __future__ import annotations


def login(client, username="admin", password="change-me"):
    res = client.post("/api/auth/login", json={"username": username, "password": password})
    assert res.status_code == 200, res.text
    return res.json()


def users_by_name(client) -> dict:
    res = client.get("/api/hr/users")
    assert res.status_code == 200, res.text
    return {u["username"]: u for u in res.json()}


def depts_by_name(client) -> dict:
    res = client.get("/api/hr/departments")
    assert res.status_code == 200, res.text
    return {d["name"]: d for d in res.json()}


def test_employee_cannot_manage_departments(client):
    login(client)
    client.post("/api/auth/logout")
    login(client, "mitarbeiter", "change-me")
    listed = client.get("/api/hr/departments")
    assert listed.status_code == 403
    created = client.post("/api/hr/departments", json={"name": "IT"})
    assert created.status_code == 403


def test_seed_departments_and_assignments(client):
    login(client)
    depts = depts_by_name(client)
    assert "Produktion" in depts
    assert "Lager" in depts
    people = users_by_name(client)
    assert people["mitarbeiter"]["department_name"] == "Produktion"
    assert people["erika"]["department_name"] == "Lager"
    assert people["admin"]["department_id"] is None


def test_department_crud_and_user_assignment(client):
    login(client)
    created = client.post("/api/hr/departments", json={"name": "  Montage  "})
    assert created.status_code == 200, created.text
    dept = created.json()
    assert dept["name"] == "Montage"
    assert dept["user_count"] == 0

    dup = client.post("/api/hr/departments", json={"name": "montage"})
    assert dup.status_code == 409

    renamed = client.patch(f"/api/hr/departments/{dept['id']}", json={"name": "Montage Nord"})
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["name"] == "Montage Nord"

    people = users_by_name(client)
    target = people["mitarbeiter"]
    assigned = client.patch(
        f"/api/hr/users/{target['id']}/account",
        json={"department_id": dept["id"]},
    )
    assert assigned.status_code == 200, assigned.text
    assert assigned.json()["department_id"] == dept["id"]
    assert assigned.json()["department_name"] == "Montage Nord"

    listed = depts_by_name(client)
    assert listed["Montage Nord"]["user_count"] == 1

    blocked = client.delete(f"/api/hr/departments/{dept['id']}")
    assert blocked.status_code == 409

    cleared = client.patch(f"/api/hr/users/{target['id']}/account", json={"department_id": None})
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["department_id"] is None
    assert cleared.json()["department_name"] is None

    deleted = client.delete(f"/api/hr/departments/{dept['id']}")
    assert deleted.status_code == 200, deleted.text
    remaining = depts_by_name(client)
    assert "Montage Nord" not in remaining


def test_create_user_with_department(client):
    login(client)
    depts = depts_by_name(client)
    models = client.get("/api/hr/work-models").json()
    created = client.post(
        "/api/hr/users",
        json={
            "username": "dept-kai",
            "display_name": "Kai Abteilung",
            "role": "employee",
            "work_model_id": models[0]["id"],
            "department_id": depts["Produktion"]["id"],
            "web_login": False,
        },
    )
    assert created.status_code == 200, created.text
    assert created.json()["department_name"] == "Produktion"

    missing = client.post(
        "/api/hr/users",
        json={
            "username": "dept-missing",
            "display_name": "Ohne Abteilung",
            "role": "employee",
            "work_model_id": models[0]["id"],
            "department_id": 99999,
            "web_login": False,
        },
    )
    assert missing.status_code == 400


def test_report_user_ids_from_department(client):
    login(client)
    people = users_by_name(client)
    erika = people["erika"]
    hired = client.patch(f"/api/hr/users/{erika['id']}/account", json={"hired_on": "2026-01-01"})
    assert hired.status_code == 200, hired.text

    balances = client.get(f"/api/hr/reports/month-balances?month=2026-08&user_ids={erika['id']}")
    assert balances.status_code == 200, balances.text
    assert [row["user_id"] for row in balances.json()["people"]] == [erika["id"]]

    nights = client.get(f"/api/hr/reports/night-hours?month=2026-08&user_ids={erika['id']}")
    assert nights.status_code == 200, nights.text
    assert [row["user_id"] for row in nights.json()["people"]] == [erika["id"]]

    empty = client.get("/api/hr/reports/jubilees?year=2026&half=2&user_ids=")
    assert empty.status_code == 200
    assert empty.json()["events"] == []
