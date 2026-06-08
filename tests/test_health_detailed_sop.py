"""GET /api/health/detailed 含 SOP 與管線欄位。"""

from fastapi.testclient import TestClient

from src.api.app import app


def test_health_detailed_includes_sop_and_pipeline():
    client = TestClient(app)
    r = client.get("/api/health/detailed")
    assert r.status_code == 200
    data = r.json()
    assert "sop" in data
    assert data["sop"]["verdict"] in ("ok", "attention", "critical")
    assert "verdict_zh" in data["sop"]
    assert isinstance(data["sop"].get("checks"), list)
    assert "sop_checked_at" in data
    assert "pipeline_metrics" in data
