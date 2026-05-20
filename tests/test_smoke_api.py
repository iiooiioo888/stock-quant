"""
API 煙霧測試 — CI 內快速驗證核心端點（等同 test_all.sh 子集）
"""
import pytest


@pytest.fixture
def auth_headers(client):
    import uuid
    pw = "smoke_test_pw_2026"
    username = f"smokeuser_{uuid.uuid4().hex[:8]}"
    client.post("/api/auth/register", json={"username": username, "password": pw})
    resp = client.post("/api/auth/login", json={"username": username, "password": pw})
    token = resp.json().get("token", "")
    return {"Authorization": f"Bearer {token}"}


class TestSmokeAPI:
    def test_health_and_status(self, client):
        assert client.get("/api/health").status_code == 200
        assert client.get("/api/status").status_code == 200

    def test_config_and_strategies(self, client):
        assert client.get("/api/config").status_code == 200
        data = client.get("/api/strategies/list").json()
        assert data.get("total", 0) >= 19

    def test_auth_me(self, client, auth_headers):
        assert client.get("/api/auth/me", headers=auth_headers).status_code == 200

    def test_tasks_list(self, client, auth_headers):
        assert client.get("/api/tasks", headers=auth_headers).status_code == 200

    def test_stock_universe_stats(self, client):
        assert client.get("/api/stock-universe/stats").status_code == 200

    def test_tasks_list_without_auth(self, client):
        """任務中心應在未登錄時可讀（本地/演示模式）"""
        resp = client.get("/api/tasks?limit=10")
        assert resp.status_code == 200
        data = resp.json()
        assert "tasks" in data
        assert "queue" in data

    def test_static_index(self, client):
        assert client.get("/").status_code == 200
        assert client.get("/static/js/app.js").status_code == 200

    def test_ws_auth_flag_in_health(self, client):
        data = client.get("/api/health").json()
        assert "ws_auth_required" in data

    def test_indices_charts(self, client):
        resp = client.get("/api/indices/charts?days=60")
        assert resp.status_code == 200
        data = resp.json()
        assert "indices" in data
        assert isinstance(data["indices"], list)

    @pytest.mark.parametrize(
        "path,keys",
        [
            ("/api/data/capital-flow?code=000001&days=5", ("flows",)),
            ("/api/data/market-flow", ("flows",)),
            ("/api/signals/current", ("signals",)),
            ("/api/scheduler/jobs", ("jobs",)),
            ("/api/strategies/params", ("strategies",)),
        ],
    )
    def test_demo_read_endpoints(self, client, path, keys):
        resp = client.get(path)
        assert resp.status_code == 200, resp.text[:200]
        data = resp.json()
        for key in keys:
            assert key in data, f"missing {key} in {path}"
