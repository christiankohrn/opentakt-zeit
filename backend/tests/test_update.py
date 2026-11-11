from __future__ import annotations

import json


def login(client, username="admin", password="change-me"):
    res = client.post("/api/auth/login", json={"username": username, "password": password})
    assert res.status_code == 200, res.text
    return res.json()


def test_update_status_requires_admin(client):
    anon = client.get("/api/hr/update/status")
    assert anon.status_code == 401
    login(client, "personal")
    assert client.get("/api/hr/update/status").status_code == 403
    assert client.post("/api/hr/update/check").status_code == 403
    assert client.post("/api/hr/update/apply").status_code == 403


def test_update_status_reports_installed_version(client):
    from app.routers.health import APP_VERSION

    login(client)
    res = client.get("/api/hr/update/status")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["installed"]["version"] == APP_VERSION
    assert body["supported"] is False
    assert body["unsupported_reason"]
    assert body["source"]["branch"] == "main"
    assert "github.com" in body["source"]["url"]


def test_update_check_stores_remote_state(client, monkeypatch):
    import app.update_service as svc

    login(client)

    head = {
        "sha": "feedface" * 5,
        "html_url": "https://github.com/x/y/commit/feedface",
        "commit": {"message": "Neu: Update-Knopf\n\nDetails", "committer": {"date": "2026-11-10T10:00:00Z"}},
    }
    compare = {"status": "behind", "behind_by": 3, "ahead_by": 0}

    def fake_fetch(url, cfg):
        if url.endswith("/commits/main"):
            return head
        assert "/compare/" in url
        return compare

    monkeypatch.setattr(svc, "fetch_json", fake_fetch)
    monkeypatch.setattr(svc, "local_install_info", lambda: {"version": "0.1.0", "commit": "a" * 40})

    res = client.post("/api/hr/update/check")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["remote"]["commit"] == head["sha"]
    assert body["remote"]["message"] == "Neu: Update-Knopf"
    assert body["comparison"] == "behind"
    assert body["behind_by"] == 3
    assert body["last_check"]

    cached = client.get("/api/hr/update/status").json()
    assert cached["remote"]["commit"] == head["sha"]
    assert cached["comparison"] == "behind"


def test_update_check_without_local_commit_is_unknown(client, monkeypatch):
    import app.update_service as svc

    login(client)
    head = {
        "sha": "b" * 40,
        "html_url": "https://github.com/x/y/commit/b",
        "commit": {"message": "Irgendwas", "committer": {"date": "2026-11-10T10:00:00Z"}},
    }
    calls = []

    def fake_fetch(url, cfg):
        calls.append(url)
        return head

    monkeypatch.setattr(svc, "fetch_json", fake_fetch)
    monkeypatch.setattr(svc, "local_install_info", lambda: {"version": "0.1.0", "commit": None})

    body = client.post("/api/hr/update/check").json()
    assert body["comparison"] == "unknown"
    assert body["remote"]["commit"] == "b" * 40
    assert len(calls) == 1


def test_update_check_github_failure_is_502(client, monkeypatch):
    import app.update_service as svc

    login(client)

    def boom(url, cfg):
        raise svc.UpdateCheckError("GitHub ist nicht erreichbar. Netzwerk prüfen.")

    monkeypatch.setattr(svc, "fetch_json", boom)
    res = client.post("/api/hr/update/check")
    assert res.status_code == 502
    assert "GitHub" in res.json()["detail"]


def test_update_apply_blocked_without_server_layout(client):
    login(client)
    res = client.post("/api/hr/update/apply")
    assert res.status_code == 409
    assert "Server" in res.json()["detail"]


def test_update_apply_writes_request_and_guards_rerun(client, monkeypatch):
    import app.update_service as svc
    from app.config import get_config

    login(client)
    monkeypatch.setattr(svc, "update_supported", lambda cfg: (True, None))
    monkeypatch.setattr(svc, "local_install_info", lambda: {"version": "0.1.0", "commit": "c" * 40})

    res = client.post("/api/hr/update/apply")
    assert res.status_code == 202, res.text
    assert res.json()["update"]["state"] == "running"

    data_dir = svc.data_dir(get_config())
    request_file = data_dir / "update.request"
    assert request_file.is_file()
    payload = json.loads(request_file.read_text(encoding="utf-8"))
    assert payload["requested_by"] == "admin"

    again = client.post("/api/hr/update/apply")
    assert again.status_code == 409

    request_file.unlink()
    (data_dir / "update-status.json").unlink(missing_ok=True)
