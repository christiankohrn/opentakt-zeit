from fastapi.testclient import TestClient

from app.branding import PRODUCT_NAME
from app.main import app
from app.routers.health import APP_VERSION


def test_meta_is_public():
    with TestClient(app) as client:
        res = client.get("/api/meta")
        assert res.status_code == 200
        body = res.json()
        assert body["org_name"]
        assert body["version"] == APP_VERSION


def test_product_name():
    assert PRODUCT_NAME == "Opentakt Zeit"


def test_health_ok():
    with TestClient(app) as client:
        res = client.get("/api/health")
        assert res.status_code == 200
        assert res.json()["ok"] is True
