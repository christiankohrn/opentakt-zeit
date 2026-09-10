from __future__ import annotations

import pyotp
import pytest


@pytest.fixture(autouse=True)
def _reset_security(client):
    """Baseline the shared seed DB so 2FA/passkey state never leaks across tests."""
    from app.database import SessionLocal
    from app.models import TotpBackupCode, User, WebAuthnCredential

    def wipe():
        db = SessionLocal()
        try:
            db.query(TotpBackupCode).delete()
            db.query(WebAuthnCredential).delete()
            for u in db.query(User).all():
                u.totp_secret = None
                u.totp_enabled = False
                u.totp_confirmed_at = None
            db.commit()
        finally:
            db.close()

    wipe()
    yield
    wipe()


def login(client, username="admin", password="change-me"):
    return client.post("/api/auth/login", json={"username": username, "password": password})


def enable_totp(client) -> tuple[str, list[str]]:
    setup = client.post("/api/me/totp/setup")
    assert setup.status_code == 200, setup.text
    secret = setup.json()["secret"]
    assert setup.json()["otpauth_uri"].startswith("otpauth://totp/")
    assert setup.json()["qr_svg"].startswith("data:image/svg+xml")
    code = pyotp.TOTP(secret).now()
    enabled = client.post("/api/me/totp/enable", json={"code": code})
    assert enabled.status_code == 200, enabled.text
    codes = enabled.json()["backup_codes"]
    assert len(codes) == 10
    return secret, codes


def test_setup_requires_login(client):
    assert client.post("/api/me/totp/setup").status_code == 401


def test_enable_and_login_with_totp(client):
    res = login(client)
    assert res.status_code == 200
    assert "mfa_required" not in res.json()  # no 2FA yet

    secret, codes = enable_totp(client)
    status = client.get("/api/me/security").json()
    assert status["totp_enabled"] is True
    assert status["backup_codes_remaining"] == 10

    client.post("/api/auth/logout")

    # Password alone no longer completes the login.
    challenge = login(client)
    assert challenge.status_code == 200, challenge.text
    body = challenge.json()
    assert body["mfa_required"] is True
    assert "totp" in body["methods"]
    # Not yet authenticated.
    assert client.get("/api/auth/me").status_code == 401

    wrong = client.post("/api/auth/mfa", json={"code": "000000"})
    assert wrong.status_code == 401

    good = client.post("/api/auth/mfa", json={"code": pyotp.TOTP(secret).now()})
    assert good.status_code == 200, good.text
    assert good.json()["username"] == "admin"
    assert client.get("/api/auth/me").status_code == 200


def test_login_with_backup_code_consumes_it(client):
    login(client)
    _secret, codes = enable_totp(client)
    client.post("/api/auth/logout")

    login(client)
    first = client.post("/api/auth/mfa", json={"code": codes[0]})
    assert first.status_code == 200, first.text

    remaining = client.get("/api/me/security").json()["backup_codes_remaining"]
    assert remaining == 9

    # The same backup code cannot be reused.
    client.post("/api/auth/logout")
    login(client)
    reuse = client.post("/api/auth/mfa", json={"code": codes[0]})
    assert reuse.status_code == 401


def test_mfa_without_pending_login_is_rejected(client):
    login(client)
    enable_totp(client)
    client.post("/api/auth/logout")
    # No password step performed first.
    assert client.post("/api/auth/mfa", json={"code": "123456"}).status_code == 401


def test_disable_requires_password_and_code(client):
    login(client)
    secret, _codes = enable_totp(client)

    bad_pw = client.post("/api/me/totp/disable", json={"password": "nope", "code": pyotp.TOTP(secret).now()})
    assert bad_pw.status_code == 400

    bad_code = client.post("/api/me/totp/disable", json={"password": "change-me", "code": "000000"})
    assert bad_code.status_code == 400

    ok = client.post("/api/me/totp/disable", json={"password": "change-me", "code": pyotp.TOTP(secret).now()})
    assert ok.status_code == 200, ok.text
    assert client.get("/api/me/security").json()["totp_enabled"] is False

    # Password-only login works again.
    client.post("/api/auth/logout")
    again = login(client)
    assert again.status_code == 200
    assert again.json()["username"] == "admin"
