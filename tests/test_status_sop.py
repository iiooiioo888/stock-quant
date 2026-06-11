"""GET /api/status 內嵌 SOP 摘要。"""

from fastapi.testclient import TestClient

from src.api.app import app


def test_status_includes_sop_summary():
    client = TestClient(app)
    r = client.get("/api/status")
    assert r.status_code == 200
    data = r.json()
    assert "sop" in data
    assert data["sop"].get("verdict") in ("ok", "attention", "critical", None)
    if data["sop"].get("verdict"):
        assert data["sop"].get("verdict_zh")
