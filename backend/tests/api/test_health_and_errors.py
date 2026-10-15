from fastapi.testclient import TestClient

from finassist.api.app import create_app

from finassist.settings import Settings

client = TestClient(create_app(Settings(_env_file=None, model_provider="fake")))


def test_health():
    r = client.get("/v1/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert r.headers.get("X-Request-Id")


def test_unknown_route_uses_error_envelope():
    r = client.get("/v1/does-not-exist")
    assert r.status_code == 404
    err = r.json()["error"]
    assert err["code"] == "NOT_FOUND"
    assert set(err) == {"code", "message", "fields", "retryable", "request_id", "details"}
