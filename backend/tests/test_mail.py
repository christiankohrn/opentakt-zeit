from __future__ import annotations

import re

from app.mail import hash_token, lookup_mail_token, valid_email


def token_from(msg) -> str:
    body = msg.get_content()
    match = re.search(r"token=([A-Za-z0-9_\-]+)", body)
    assert match, body
    return match.group(1)


def login(client, username="admin", password="change-me"):
    res = client.post("/api/auth/login", json={"username": username, "password": password})
    assert res.status_code == 200, res.text
    return res.json()


def enable_smtp(client):
    login(client)
    res = client.patch(
        "/api/hr/smtp",
        json={
            "enabled": True,
            "host": "smtp.test",
            "port": 587,
            "username": "zeit",
            "password": "smtp-secret",
            "from_addr": "zeit@example.com",
            "use_tls": True,
            "use_ssl": False,
        },
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["ready"] is True
    assert data["password_set"] is True
    assert "smtp-secret" not in res.text
    return data


def test_valid_email():
    assert valid_email("a@example.com")
    assert valid_email("Admin@LocalHost")
    assert not valid_email("no-at")
    assert not valid_email("a@")
    assert hash_token("abc") != "abc"


def test_hr_cannot_change_smtp(client):
    login(client, "personal")
    res = client.patch("/api/hr/smtp", json={"enabled": True, "host": "x", "from_addr": "a@b.de"})
    assert res.status_code == 403


def test_invite_and_set_password(client, outbox):
    enable_smtp(client)
    models = client.get("/api/hr/work-models").json()
    res = client.post(
        "/api/hr/users",
        json={
            "username": "lisa",
            "display_name": "Lisa Neu",
            "email": "lisa@example.com",
            "role": "employee",
            "work_model_id": models[0]["id"],
            "web_login": True,
            "send_access_mail": True,
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["mail_sent"] is True
    assert body["email"] == "lisa@example.com"
    assert len(outbox) == 1
    assert "Opentakt Zeit" in outbox[0]["Subject"]
    token = token_from(outbox[0])
    info = client.get("/api/auth/password-token", params={"token": token})
    assert info.status_code == 200
    assert info.json()["username"] == "lisa"
    assert info.json()["purpose"] == "invite"
    set_pw = client.post("/api/auth/password-token", json={"token": token, "password": "Lisa-Test-99"})
    assert set_pw.status_code == 200, set_pw.text
    again = client.post("/api/auth/password-token", json={"token": token, "password": "Lisa-Test-00"})
    assert again.status_code == 400
    login(client, "lisa", "Lisa-Test-99")


def test_forgot_reset_flow(client, outbox):
    enable_smtp(client)
    client.post("/api/auth/logout")
    res = client.post("/api/auth/forgot", json={"username_or_email": "mitarbeiter"})
    assert res.status_code == 200
    unknown = client.post("/api/auth/forgot", json={"username_or_email": "gibt-es-nicht"})
    assert unknown.status_code == 200
    assert len(outbox) == 1
    token = token_from(outbox[0])
    res = client.post("/api/auth/password-token", json={"token": token, "password": "Neu-Pass-26"})
    assert res.status_code == 200, res.text
    bad = client.post("/api/auth/login", json={"username": "mitarbeiter", "password": "change-me"})
    assert bad.status_code == 401
    login(client, "mitarbeiter", "Neu-Pass-26")


def test_create_without_mailserver_rejected(client):
    login(client)
    client.patch(
        "/api/hr/smtp",
        json={"enabled": False, "host": "", "from_addr": ""},
    )
    models = client.get("/api/hr/work-models").json()
    res = client.post(
        "/api/hr/users",
        json={
            "username": "ohne-mailserver",
            "display_name": "Ohne Mail",
            "email": "ohne@example.com",
            "role": "employee",
            "work_model_id": models[0]["id"],
            "web_login": True,
            "send_access_mail": True,
        },
    )
    assert res.status_code == 400
    assert "Mailserver" in res.text


def test_smtp_test_mail(client, outbox):
    enable_smtp(client)
    res = client.post("/api/hr/smtp/test", json={"to": "chef@example.com"})
    assert res.status_code == 200, res.text
    assert outbox[-1]["To"] == "chef@example.com"
    assert "Testmail" in outbox[-1]["Subject"]
    assert "Opentakt Zeit" in outbox[-1].get_content()


def test_lookup_unknown_token(client):
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        assert lookup_mail_token(db, "nope") is None
    finally:
        db.close()
    res = client.get("/api/auth/password-token", params={"token": "not-a-real-token-value"})
    assert res.status_code == 400
