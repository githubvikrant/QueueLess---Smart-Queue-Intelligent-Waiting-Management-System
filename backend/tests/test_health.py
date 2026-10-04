from fastapi.testclient import TestClient
from app.main import api


def test_health():
    client = TestClient(api)
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"
