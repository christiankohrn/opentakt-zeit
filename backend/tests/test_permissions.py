from __future__ import annotations


def login(client, username="admin", password="change-me"):
    res = client.post("/api/auth/login", json={"username": username, "password": password})
    assert res.status_code == 200, res.text
    return res.json()


def users_by_name(client) -> dict:
    res = client.get("/api/hr/users")
    assert res.status_code == 200, res.text
    return {u["username"]: u for u in res.json()}


def test_hr_cannot_self_promote_to_admin(client):
    me = login(client, "personal")
    assert me["role"] == "hr"
    res = client.patch(f"/api/hr/users/{me['id']}/account", json={"role": "admin"})
    assert res.status_code == 403
    assert "Rollen" in res.json()["detail"]
    again = client.get("/api/auth/me")
    assert again.status_code == 200
    assert again.json()["role"] == "hr"
    smtp = client.get("/api/hr/smtp")
    assert smtp.status_code == 403
    settings = client.get("/api/hr/users")
    assert settings.status_code == 200
    mine = next(u for u in settings.json() if u["id"] == me["id"])
    assert mine["role"] == "hr"


def test_hr_cannot_change_role_password_active_or_web_login(client):
    login(client, "personal")
    people = users_by_name(client)
    target = people["mitarbeiter"]
    role = client.patch(f"/api/hr/users/{target['id']}/account", json={"role": "admin"})
    assert role.status_code == 403
    active = client.patch(f"/api/hr/users/{target['id']}/account", json={"active": False})
    assert active.status_code == 403
    password = client.patch(f"/api/hr/users/{target['id']}/account", json={"password": "Geheim-99"})
    assert password.status_code == 403
    web = client.patch(f"/api/hr/users/{target['id']}/settings", json={"web_login": False})
    assert web.status_code == 403
    login(client, "admin")
    check = users_by_name(client)["mitarbeiter"]
    assert check["role"] == "employee"
    assert check["active"] is True
    assert check["web_login"] is True


def test_hr_can_update_personnel_fields_and_create_employee(client):
    login(client, "personal")
    people = users_by_name(client)
    target = people["mitarbeiter"]
    res = client.patch(
        f"/api/hr/users/{target['id']}/account",
        json={"display_name": "Max Personal", "email": "max@example.com"},
    )
    assert res.status_code == 200, res.text
    assert res.json()["display_name"] == "Max Personal"
    assert res.json()["role"] == "employee"
    models = client.get("/api/hr/work-models").json()
    created = client.post(
        "/api/hr/users",
        json={
            "username": "neu-hr",
            "display_name": "Neue Person",
            "role": "employee",
            "work_model_id": models[0]["id"],
            "web_login": False,
        },
    )
    assert created.status_code == 200, created.text
    assert created.json()["role"] == "employee"
    assert created.json()["web_login"] is False
    assert created.json()["active"] is True


def test_hr_cannot_create_admin_or_enable_web_login(client):
    login(client, "personal")
    models = client.get("/api/hr/work-models").json()
    as_admin = client.post(
        "/api/hr/users",
        json={
            "username": "fake-admin",
            "display_name": "Fake Admin",
            "role": "admin",
            "password": "Geheim-99",
            "work_model_id": models[0]["id"],
            "web_login": True,
        },
    )
    assert as_admin.status_code == 403
    with_web = client.post(
        "/api/hr/users",
        json={
            "username": "web-hr",
            "display_name": "Web HR",
            "role": "employee",
            "work_model_id": models[0]["id"],
            "web_login": True,
        },
    )
    assert with_web.status_code == 403
    with_pw = client.post(
        "/api/hr/users",
        json={
            "username": "pw-hr",
            "display_name": "PW HR",
            "role": "employee",
            "password": "Geheim-99",
            "work_model_id": models[0]["id"],
            "web_login": False,
        },
    )
    assert with_pw.status_code == 403


def test_hr_cannot_patch_legacy_user_role(client):
    login(client, "personal")
    people = users_by_name(client)
    target = people["mitarbeiter"]
    res = client.patch(
        f"/api/hr/users/{target['id']}",
        json={
            "username": target["username"],
            "display_name": target["display_name"],
            "role": "admin",
            "active": True,
            "web_login": True,
        },
    )
    assert res.status_code == 403


def test_last_admin_cannot_demote_or_deactivate_self(client):
    me = login(client)
    assert me["role"] == "admin"
    others = [
        u
        for u in client.get("/api/hr/users").json()
        if u["role"] == "admin" and u["active"] and u["id"] != me["id"]
    ]
    for other in others:
        res = client.patch(f"/api/hr/users/{other['id']}/account", json={"role": "hr"})
        assert res.status_code == 200, res.text
    demote = client.patch(f"/api/hr/users/{me['id']}/account", json={"role": "hr"})
    assert demote.status_code == 400
    assert "letzte Administrator" in demote.json()["detail"]
    deactivate = client.patch(f"/api/hr/users/{me['id']}/account", json={"active": False})
    assert deactivate.status_code == 400
    still = client.get("/api/auth/me")
    assert still.json()["role"] == "admin"
    assert still.json()["active"] is True


def test_admin_can_demote_when_another_admin_exists(client):
    login(client)
    models = client.get("/api/hr/work-models").json()
    created = client.post(
        "/api/hr/users",
        json={
            "username": "zweit-admin",
            "display_name": "Zweiter Admin",
            "role": "admin",
            "password": "Zweit-Admin-99",
            "work_model_id": models[0]["id"],
            "web_login": True,
        },
    )
    assert created.status_code == 200, created.text
    demote = client.patch(f"/api/hr/users/{created.json()['id']}/account", json={"role": "hr"})
    assert demote.status_code == 200, demote.text
    assert demote.json()["role"] == "hr"
    smtp = client.get("/api/hr/smtp")
    assert smtp.status_code == 200
    client.post("/api/auth/logout")
    other = login(client, "zweit-admin", "Zweit-Admin-99")
    assert other["role"] == "hr"
    assert client.get("/api/hr/smtp").status_code == 403


def test_employee_cannot_use_hr_user_api(client):
    login(client, "erika")
    res = client.get("/api/hr/users")
    assert res.status_code == 403
    patch = client.patch("/api/hr/users/1/account", json={"role": "admin"})
    assert patch.status_code == 403


def test_hr_cannot_change_bundesland_admin_can(client):
    login(client, "personal")
    denied = client.patch("/api/hr/settings", json={"bundesland": "BY"})
    assert denied.status_code == 403
    login(client)
    allowed = client.patch("/api/hr/settings", json={"bundesland": "BY"})
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["bundesland"] == "BY"


def test_admin_can_change_role_and_web_login(client):
    login(client)
    models = client.get("/api/hr/work-models").json()
    created = client.post(
        "/api/hr/users",
        json={
            "username": "rolle-ziel",
            "display_name": "Rolle Ziel",
            "role": "employee",
            "password": "Rolle-Ziel-99",
            "work_model_id": models[0]["id"],
            "web_login": True,
        },
    )
    assert created.status_code == 200, created.text
    user_id = created.json()["id"]
    res = client.patch(f"/api/hr/users/{user_id}/settings", json={"web_login": False})
    assert res.status_code == 200, res.text
    assert res.json()["web_login"] is False
    promote = client.patch(f"/api/hr/users/{user_id}/account", json={"role": "supervisor"})
    assert promote.status_code == 200, promote.text
    assert promote.json()["role"] == "supervisor"
    assert promote.json()["web_login"] is True
