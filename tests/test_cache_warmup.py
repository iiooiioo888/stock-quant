"""緩存預熱與分層讀取"""
import pytest


def test_cache_l1_read_through_on_set():
    from src.core.cache import CacheManager

    cm = CacheManager()
    cm._redis_available = False
    cm.set("sq:test:readthrough", {"ok": 1}, ttl=60)
    assert cm.get("sq:test:readthrough") == {"ok": 1}
    assert cm._hits_l1 >= 1


def test_count_backtest_history(client):
    r = client.get("/api/backtest/history?limit=1")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= len(body["results"])
