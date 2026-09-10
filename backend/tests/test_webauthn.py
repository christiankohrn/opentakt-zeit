from __future__ import annotations

import hashlib
import json
import os
import struct

import cbor2
import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from webauthn.helpers import bytes_to_base64url


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

# The test config uses public_url http://test.local with environment "test"
# (not dev), so the relying party is deterministic.
RP_ID = "test.local"
ORIGIN = "http://test.local"


class SoftAuthenticator:
    """Minimal FIDO2 authenticator (ES256/P-256) for exercising the RP end to end."""

    def __init__(self) -> None:
        self._key = ec.generate_private_key(ec.SECP256R1())
        self.credential_id = os.urandom(32)
        self.sign_count = 0

    def _cose_key(self) -> bytes:
        nums = self._key.public_key().public_numbers()
        x = nums.x.to_bytes(32, "big")
        y = nums.y.to_bytes(32, "big")
        # COSE_Key: kty=EC2(2), alg=ES256(-7), crv=P-256(1), x, y
        return cbor2.dumps({1: 2, 3: -7, -1: 1, -2: x, -3: y})

    def _auth_data(self, *, attested: bool, flags_extra: int = 0) -> bytes:
        rp_id_hash = hashlib.sha256(RP_ID.encode()).digest()
        flags = 0x01 | flags_extra  # user present
        if attested:
            flags |= 0x40  # attested credential data included
        data = rp_id_hash + bytes([flags]) + struct.pack(">I", self.sign_count)
        if attested:
            aaguid = b"\x00" * 16
            cred_len = struct.pack(">H", len(self.credential_id))
            data += aaguid + cred_len + self.credential_id + self._cose_key()
        return data

    def create(self, challenge_b64url: str) -> dict:
        client_data = json.dumps(
            {"type": "webauthn.create", "challenge": challenge_b64url, "origin": ORIGIN, "crossOrigin": False}
        ).encode()
        auth_data = self._auth_data(attested=True)
        attestation_object = cbor2.dumps({"fmt": "none", "attStmt": {}, "authData": auth_data})
        return {
            "id": bytes_to_base64url(self.credential_id),
            "rawId": bytes_to_base64url(self.credential_id),
            "type": "public-key",
            "response": {
                "clientDataJSON": bytes_to_base64url(client_data),
                "attestationObject": bytes_to_base64url(attestation_object),
                "transports": ["internal"],
            },
            "clientExtensionResults": {},
            "authenticatorAttachment": "platform",
        }

    def get(self, challenge_b64url: str, user_id: bytes = b"1") -> dict:
        self.sign_count += 1
        client_data = json.dumps(
            {"type": "webauthn.get", "challenge": challenge_b64url, "origin": ORIGIN, "crossOrigin": False}
        ).encode()
        auth_data = self._auth_data(attested=False)
        signed = auth_data + hashlib.sha256(client_data).digest()
        signature = self._key.sign(signed, ec.ECDSA(hashes.SHA256()))
        return {
            "id": bytes_to_base64url(self.credential_id),
            "rawId": bytes_to_base64url(self.credential_id),
            "type": "public-key",
            "response": {
                "clientDataJSON": bytes_to_base64url(client_data),
                "authenticatorData": bytes_to_base64url(auth_data),
                "signature": bytes_to_base64url(signature),
                "userHandle": bytes_to_base64url(user_id),
            },
            "clientExtensionResults": {},
        }


def login(client, username="admin", password="change-me"):
    res = client.post("/api/auth/login", json={"username": username, "password": password})
    assert res.status_code == 200 and "mfa_required" not in res.json(), res.text
    return res


def register_passkey(client, name="Mein Laptop") -> SoftAuthenticator:
    options = client.post("/api/me/passkeys/register/options")
    assert options.status_code == 200, options.text
    challenge = options.json()["challenge"]
    device = SoftAuthenticator()
    verify = client.post(
        "/api/me/passkeys/register/verify",
        json={"credential": device.create(challenge), "name": name},
    )
    assert verify.status_code == 200, verify.text
    assert verify.json()["name"] == name
    return device


def test_register_passkey_and_list(client):
    login(client)
    register_passkey(client)
    passkeys = client.get("/api/me/passkeys").json()
    assert len(passkeys) == 1
    assert passkeys[0]["name"] == "Mein Laptop"
    sec = client.get("/api/me/security").json()
    assert len(sec["passkeys"]) == 1


def test_passwordless_login_with_passkey(client):
    me = login(client)
    assert me.status_code == 200
    device = register_passkey(client)
    client.post("/api/auth/logout")
    assert client.get("/api/auth/me").status_code == 401

    options = client.post("/api/auth/passkey/options", json={"username": "admin"})
    assert options.status_code == 200, options.text
    challenge = options.json()["challenge"]

    verify = client.post("/api/auth/passkey/verify", json={"credential": device.get(challenge)})
    assert verify.status_code == 200, verify.text
    assert verify.json()["username"] == "admin"
    assert client.get("/api/auth/me").status_code == 200


def test_passkey_verify_requires_options_first(client):
    login(client)
    device = register_passkey(client)
    client.post("/api/auth/logout")
    # Skip the options call → no challenge in session.
    res = client.post("/api/auth/passkey/verify", json={"credential": device.get("AAAA")})
    assert res.status_code == 401


def test_unknown_passkey_rejected(client):
    login(client)
    register_passkey(client)
    client.post("/api/auth/logout")
    client.post("/api/auth/passkey/options", json={"username": "admin"})
    stranger = SoftAuthenticator()
    res = client.post("/api/auth/passkey/verify", json={"credential": stranger.get("AAAA")})
    assert res.status_code == 401


def test_rename_and_delete_passkey(client):
    login(client)
    register_passkey(client)
    pk = client.get("/api/me/passkeys").json()[0]
    renamed = client.patch(f"/api/me/passkeys/{pk['id']}", json={"name": "Yubikey"})
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["name"] == "Yubikey"
    deleted = client.delete(f"/api/me/passkeys/{pk['id']}")
    assert deleted.status_code == 200
    assert client.get("/api/me/passkeys").json() == []
