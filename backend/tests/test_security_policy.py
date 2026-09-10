from __future__ import annotations

import pyotp
import pytest


@pytest.fixture(autouse=True)
def _reset(client):
    """Reset policies + 2FA/passkeys around each test (shared seed DB)."""
    from app.database import SessionLocal
    from app.models import TotpBackupCode, User, WebAuthnCredential
    from app.security_policy import set_policies

    def wipe():
        db = SessionLocal()
        try:
            db.query(TotpBackupCode).delete()
            db.query(WebAuthnCredential).delete()
            for u in db.query(User).all():
                u.totp_secret = None
                u.totp_enabled = False
                u.totp_confirmed_at = None
            set_policies(db, {r: "off" for r in ("employee", "supervisor", "hr", "admin")})
            db.commit()
        finally:
            db.close()

    wipe()
    yield
    wipe()


def login(client, username="admin", password="change-me"):
    res = client.post("/api/auth/login", json={"username": username, "password": password})
    assert res.status_code == 200, res.text
    return res


def enroll_totp(client):
    secret = client.post("/api/me/totp/setup").json()["secret"]
    client.post("/api/me/totp/enable", json={"code": pyotp.TOTP(secret).now()})
    return secret


def test_policy_defaults_off_and_admin_can_set(client):
    login(client)
    pol = client.get("/api/hr/security-policy")
    assert pol.status_code == 200, pol.text
    body = pol.json()
    assert body["policies"] == {"employee": "off", "supervisor": "off", "hr": "off", "admin": "off"}
    assert set(body["values"]) == {"off", "totp", "passkey", "any"}
    assert "employee" in body["roles"]

    upd = client.patch("/api/hr/security-policy", json={"policies": {"employee": "totp", "admin": "any"}})
    assert upd.status_code == 200, upd.text
    assert upd.json()["policies"]["employee"] == "totp"
    assert upd.json()["policies"]["admin"] == "any"


def test_hr_cannot_change_policy(client):
    login(client, "personal")  # role hr
    assert client.get("/api/hr/security-policy").status_code == 200  # may read
    denied = client.patch("/api/hr/security-policy", json={"policies": {"employee": "totp"}})
    assert denied.status_code == 403


def test_invalid_policy_value_rejected(client):
    login(client)
    bad = client.patch("/api/hr/security-policy", json={"policies": {"employee": "sms"}})
    assert bad.status_code == 400


def test_user_list_shows_totp_and_passkey_flags(client):
    login(client)
    enroll_totp(client)  # admin now has TOTP

    # Simulate a stored passkey for admin directly in the DB.
    from app.database import SessionLocal
    from app.models import User, WebAuthnCredential

    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.username == "admin").first()
        db.add(
            WebAuthnCredential(
                user_id=admin.id, credential_id="cred-demo-1", public_key="pk", sign_count=0, name="Testkey"
            )
        )
        db.commit()
    finally:
        db.close()

    users = {u["username"]: u for u in client.get("/api/hr/users").json()}
    assert users["admin"]["totp_enabled"] is True
    assert users["admin"]["passkey_count"] == 1
    assert users["mitarbeiter"]["totp_enabled"] is False
    assert users["mitarbeiter"]["passkey_count"] == 0


def test_enforcement_flag_until_enrolled(client):
    login(client)
    # Require a second factor for admins.
    client.patch("/api/hr/security-policy", json={"policies": {"admin": "totp"}})

    me = client.get("/api/auth/me").json()
    assert me["security_setup_required"] == "totp"

    enroll_totp(client)
    me2 = client.get("/api/auth/me").json()
    assert me2["security_setup_required"] is None
    assert me2["totp_enabled"] is True


def test_any_policy_satisfied_by_passkey(client):
    login(client)
    client.patch("/api/hr/security-policy", json={"policies": {"admin": "any"}})
    assert client.get("/api/auth/me").json()["security_setup_required"] == "any"

    from app.database import SessionLocal
    from app.models import User, WebAuthnCredential

    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.username == "admin").first()
        db.add(
            WebAuthnCredential(
                user_id=admin.id, credential_id="cred-any-1", public_key="pk", sign_count=0, name="Key"
            )
        )
        db.commit()
    finally:
        db.close()

    assert client.get("/api/auth/me").json()["security_setup_required"] is None
