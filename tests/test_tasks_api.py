"""
任務 API 測試 — 列表、詳情、刪除
"""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def auth_headers(client):
    """註冊並登錄，返回 Authorization header"""
    import uuid
    pw = "test_tasks_api_pw_2026"
    username = f"tasktester_{uuid.uuid4().hex[:8]}"
    client.post("/api/auth/register", json={"username": username, "password": pw})
    resp = client.post("/api/auth/login", json={"username": username, "password": pw})
    assert resp.status_code == 200
    token = resp.json().get("token")
    assert token
    return {"Authorization": f"Bearer {token}"}


class TestTasksAPI:
    def test_list_tasks(self, client, auth_headers):
        resp = client.get("/api/tasks", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "tasks" in data
        assert "stats" in data

    def test_task_queue(self, client, auth_headers):
        resp = client.get("/api/tasks/queue", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "current" in data or "next" in data or "recent" in data

    def test_create_and_delete_task(self, client, auth_headers):
        from src.core.task_manager import create_task, delete_task, get_task, update_task

        task = create_task("backtest", {"code": "000001", "strategy": "dual_ma"}, title="pytest task")
        task_id = task["task_id"]

        resp = client.get(f"/api/tasks/{task_id}", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["task"]["task_id"] == task_id

        resp = client.get(f"/api/tasks/{task_id}/full", headers=auth_headers)
        assert resp.status_code == 200

        update_task(task_id, status="completed", progress=100)
        resp = client.delete(f"/api/tasks/{task_id}", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json().get("success") is True
        assert get_task(task_id) is None

    def test_delete_running_task_fails(self, client, auth_headers):
        from src.core.task_manager import create_task, update_task

        task = create_task("optimize", {"code": "000001"}, title="running task")
        task_id = task["task_id"]
        update_task(task_id, status="running", progress=10)

        resp = client.delete(f"/api/tasks/{task_id}", headers=auth_headers)
        assert resp.status_code == 404
