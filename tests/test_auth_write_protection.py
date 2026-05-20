"""演示模式：讀開放、寫入需登錄"""
import pytest


@pytest.fixture
def auth_headers(client):
    import uuid
    pw = "write_prot_pw_2026"
    username = f"writeprot_{uuid.uuid4().hex[:8]}"
    client.post("/api/auth/register", json={"username": username, "password": pw})
    resp = client.post("/api/auth/login", json={"username": username, "password": pw})
    token = resp.json().get("token", "")
    return {"Authorization": f"Bearer {token}"}


class TestAuthWriteProtection:
    def test_tasks_get_without_auth(self, client):
        resp = client.get("/api/tasks?limit=5")
        assert resp.status_code == 200
        assert "tasks" in resp.json()

    def test_tasks_cancel_without_auth(self, client):
        resp = client.post("/api/tasks/nonexistent-task-id/cancel")
        assert resp.status_code == 401

    def test_stocks_download_without_auth(self, client):
        resp = client.post("/api/stocks/download", json={"codes": ["000001"]})
        assert resp.status_code == 401

    def test_tasks_cancel_with_auth(self, client, auth_headers):
        resp = client.post(
            "/api/tasks/nonexistent-task-id/cancel",
            headers=auth_headers,
        )
        assert resp.status_code in (404, 400, 422)

    def test_strategies_params_get_without_auth(self, client):
        resp = client.get("/api/strategies/params")
        assert resp.status_code == 200
        assert "strategies" in resp.json()
