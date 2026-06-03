"""GET /api/health/sop 端點。"""
from fastapi.testclient import TestClient

from src.api.app import app


def test_health_sop_shape():
    client = TestClient(app)
    r = client.get("/api/health/sop")
    assert r.status_code == 200
    data = r.json()
    assert "sop" in data
    assert data["sop"]["verdict"] in ("ok", "attention", "critical")
    assert "verdict_zh" in data["sop"]
    assert isinstance(data["sop"]["checks"], list)
    assert "pipeline_metrics" in data
    assert "index_audit" in data
    assert "checked_at" in data
