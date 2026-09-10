from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

_ROOT = Path(tempfile.mkdtemp(prefix="ze-mail-test-"))
_CFG = _ROOT / "config.toml"
_CFG.write_text(
    f"""
environment = "test"
secret_key = "test-secret-key-mail-suite"
timezone = "Europe/Berlin"
org_name = "Test GmbH"
public_url = "http://test.local"
database_path = "{(_ROOT / "app.db").as_posix()}"
listen_host = "127.0.0.1"
listen_port = 8000
esp_terminal_secret = "test-esp-secret"
""",
    encoding="utf-8",
)
os.environ["ZEITERFASSUNG_CONFIG"] = str(_CFG)

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def outbox(monkeypatch):
    box: list = []

    def fake(_smtp, msg):
        box.append(msg)

    monkeypatch.setattr("app.mail.deliver_message", fake)
    return box
