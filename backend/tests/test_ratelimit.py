from __future__ import annotations

import pytest

from app.ratelimit import reset as reset_limits


@pytest.fixture(autouse=True)
def _clean_limits():
    reset_limits()
    yield
    reset_limits()


def test_login_blocks_after_repeated_failures(client):
    for _ in range(10):
        res = client.post("/api/auth/login", json={"username": "admin", "password": "falsch-99"})
        assert res.status_code == 401, res.text
    blocked = client.post("/api/auth/login", json={"username": "admin", "password": "change-me"})
    assert blocked.status_code == 429, blocked.text
    assert "retry-after" in {k.lower() for k in blocked.headers}


def test_login_success_resets_failure_budget(client):
    for _ in range(9):
        res = client.post("/api/auth/login", json={"username": "admin", "password": "falsch-99"})
        assert res.status_code == 401, res.text
    ok = client.post("/api/auth/login", json={"username": "admin", "password": "change-me"})
    assert ok.status_code == 200, ok.text
    for _ in range(9):
        res = client.post("/api/auth/login", json={"username": "admin", "password": "falsch-99"})
        assert res.status_code == 401, res.text


def test_forgot_is_rate_limited(client):
    for _ in range(10):
        res = client.post("/api/auth/forgot", json={"username_or_email": "gibt-es-nicht"})
        assert res.status_code == 200, res.text
    blocked = client.post("/api/auth/forgot", json={"username_or_email": "gibt-es-nicht"})
    assert blocked.status_code == 429, blocked.text


def test_password_token_info_is_rate_limited(client):
    for _ in range(30):
        res = client.get("/api/auth/password-token", params={"token": "kein-echtes-token"})
        assert res.status_code == 400, res.text
    blocked = client.get("/api/auth/password-token", params={"token": "kein-echtes-token"})
    assert blocked.status_code == 429, blocked.text
