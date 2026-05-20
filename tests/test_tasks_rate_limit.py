"""任務 API 不應被全局限流誤傷"""
import pytest


def test_tasks_not_rate_limited_heavily(client):
    """連續輪詢任務列表不應觸發 429（任務端點已排除限流）"""
    for _ in range(30):
        resp = client.get("/api/tasks?limit=5")
        assert resp.status_code == 200, resp.text
