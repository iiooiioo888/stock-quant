"""
API 測試 — 測試健康檢查端點和基本 API 流程
使用 FastAPI TestClient，無需啟動服務
"""

import pytest
from unittest.mock import patch, MagicMock


class TestHealthEndpoint:
    """健康檢查端點測試"""

    def test_health_basic(self, client):
        """測試基本健康檢查"""
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "version" in data
        assert "uptime" in data

    def test_health_has_db_info(self, client):
        """測試健康檢查包含數據庫信息"""
        resp = client.get("/api/health")
        data = resp.json()
        assert "database" in data


class TestStatusEndpoint:
    """系統狀態端點測試"""

    def test_status_returns_config(self, client):
        """測試狀態返回配置信息"""
        resp = client.get("/api/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "version" in data
        assert "uptime_seconds" in data
        assert "watchlist" in data


class TestConfigEndpoint:
    """配置端點測試"""

    def test_get_config(self, client):
        """測試獲取配置"""
        resp = client.get("/api/config")
        assert resp.status_code == 200
        data = resp.json()
        assert "watchlist" in data
        assert "strategy_params" in data
        assert "alert_rules" in data


@pytest.fixture
def auth_headers(client):
    import uuid

    pw = "api_test_pw_2026"
    username = f"apitest_{uuid.uuid4().hex[:8]}"
    client.post("/api/auth/register", json={"username": username, "password": pw})
    resp = client.post("/api/auth/login", json={"username": username, "password": pw})
    token = resp.json().get("token", "")
    return {"Authorization": f"Bearer {token}"}


class TestBacktestEndpoint:
    """回測端點測試"""

    def test_backtest_invalid_strategy(self, client, auth_headers):
        """測試無效策略名稱"""
        resp = client.post(
            "/api/backtest?code=TEST&strategy=invalid_strategy",
            headers=auth_headers,
        )
        assert resp.status_code == 400

    def test_backtest_multi_invalid(self, client, auth_headers, monkeypatch):
        """測試多策略回測（無效代碼應快速失敗，不刷 error 日誌）"""
        from src.core import backtest as bt

        def _fail_fast(*args, **kwargs):
            raise ValueError("股票 INVALID 無歷史數據")

        monkeypatch.setattr(bt, "run_backtest", _fail_fast)
        resp = client.post("/api/backtest/multi?code=INVALID", headers=auth_headers)
        assert resp.status_code in [200, 400, 500]


class TestAlertsEndpoint:
    """預警端點測試"""

    def test_list_alerts(self, client):
        """測試獲取預警列表（演示模式可讀）"""
        resp = client.get("/api/alerts")
        assert resp.status_code == 200
        data = resp.json()
        assert "alerts" in data

    def test_get_alert_rules(self, client):
        """測試獲取預警規則"""
        resp = client.get("/api/alerts/rules")
        assert resp.status_code == 200
        data = resp.json()
        assert "rules" in data


class TestStrategyEndpoints:
    """策略端點測試"""

    def test_list_strategies(self, client):
        """測試列出策略"""
        resp = client.get("/api/strategies/list")
        assert resp.status_code == 200
        data = resp.json()
        assert "builtin" in data
        assert "user" in data
        assert data["total"] >= 19


class TestCacheIntegration:
    """緩存集成測試"""

    def test_cache_lru_fallback(self):
        """測試 LRU 回退（不依賴 Redis）"""
        from src.core.cache import LRUCache

        cache = LRUCache(max_size=10)
        cache.set("key1", {"data": "test"}, ttl=60)
        result = cache.get("key1")
        assert result == {"data": "test"}

    def test_cache_lru_expiry(self):
        """測試 LRU 緩存過期"""
        import time
        from src.core.cache import LRUCache

        cache = LRUCache(max_size=10)
        cache.set("key1", "value1", ttl=1)
        assert cache.get("key1") == "value1"
        time.sleep(1.1)
        assert cache.get("key1") is None

    def test_cache_lru_eviction(self):
        """測試 LRU 緩存淘汰"""
        from src.core.cache import LRUCache

        cache = LRUCache(max_size=3)
        cache.set("a", 1, ttl=60)
        cache.set("b", 2, ttl=60)
        cache.set("c", 3, ttl=60)
        cache.set("d", 4, ttl=60)  # 應淘汰 "a"
        assert cache.get("a") is None
        assert cache.get("d") == 4

    def test_cache_manager_without_redis(self):
        """測試 CacheManager（無 Redis 模式）"""
        from src.core.cache import CacheManager

        mgr = CacheManager()
        # 無 Redis 時應回退到 LRU
        mgr.set("test_key", {"value": 42}, ttl=60)
        result = mgr.get("test_key")
        assert result == {"value": 42}

    def test_cache_stats(self):
        """測試緩存統計"""
        from src.core.cache import CacheManager

        mgr = CacheManager()
        stats = mgr.stats()
        assert "backend" in stats
        assert "lru_size" in stats
