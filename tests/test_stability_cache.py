"""
緩存層穩定性測試 — LRUCache、CacheManager、並發讀寫

覆蓋：
  - LRU 基本讀寫
  - TTL 過期
  - 容量淘汰
  - 並發讀寫安全
  - CacheManager 降級路徑
  - 極端 key/value
"""
from __future__ import annotations

import threading
import time
import pytest

from src.core.cache import LRUCache, CacheManager


# ── LRUCache 基本操作 ──────────────────────────────────────────

class TestLRUCacheBasic:
    """LRU 緩存基本功能。"""

    @pytest.fixture
    def cache(self):
        return LRUCache(max_size=100)

    def test_set_and_get(self, cache):
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

    def test_get_missing_key(self, cache):
        assert cache.get("nonexistent") is None

    def test_overwrite_key(self, cache):
        cache.set("key1", "old")
        cache.set("key1", "new")
        assert cache.get("key1") == "new"

    def test_delete_key(self, cache):
        cache.set("key1", "value1")
        cache.delete("key1")
        assert cache.get("key1") is None

    def test_delete_nonexistent(self, cache):
        cache.delete("nonexistent")  # 不應崩潰

    def test_clear(self, cache):
        cache.set("a", 1)
        cache.set("b", 2)
        cache.clear()
        assert cache.size() == 0
        assert cache.get("a") is None

    def test_size(self, cache):
        assert cache.size() == 0
        cache.set("a", 1)
        assert cache.size() == 1
        cache.set("b", 2)
        assert cache.size() == 2

    def test_complex_values(self, cache):
        """存儲複雜對象。"""
        data = {"nested": [1, 2, {"deep": True}], "num": 3.14}
        cache.set("complex", data)
        assert cache.get("complex") == data

    def test_none_value(self, cache):
        """存儲 None 值。"""
        cache.set("null", None)
        assert cache.get("null") is None  # 與「不存在」無法區分，但不應崩潰

    def test_empty_string_key(self, cache):
        cache.set("", "empty_key")
        assert cache.get("") == "empty_key"


# ── TTL 過期 ────────────────────────────────────────────────────

class TestLRUCacheTTL:
    """TTL 過期機制。"""

    def test_ttl_expires(self):
        cache = LRUCache(max_size=100)
        cache.set("key", "value", ttl=1)
        assert cache.get("key") == "value"
        time.sleep(1.1)
        assert cache.get("key") is None

    def test_ttl_zero_never_expires(self):
        cache = LRUCache(max_size=100)
        cache.set("key", "value", ttl=0)
        time.sleep(0.1)
        assert cache.get("key") == "value"

    def test_ttl_update_refreshes(self):
        cache = LRUCache(max_size=100)
        cache.set("key", "old", ttl=1)
        time.sleep(0.5)
        cache.set("key", "new", ttl=2)  # 刷新 TTL
        time.sleep(0.6)
        assert cache.get("key") == "new"  # 應該還在


# ── 容量淘汰 ────────────────────────────────────────────────────

class TestLRUCacheEviction:
    """容量限制與 LRU 淘汰。"""

    def test_eviction_on_overflow(self):
        cache = LRUCache(max_size=3)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)
        cache.set("d", 4)  # 應淘汰 "a"
        assert cache.get("a") is None
        assert cache.get("d") == 4

    def test_access_refreshes_order(self):
        cache = LRUCache(max_size=3)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)
        cache.get("a")  # 刷新 "a"，使 "b" 成為最舊
        cache.set("d", 4)  # 應淘汰 "b"
        assert cache.get("a") == 1
        assert cache.get("b") is None

    def test_exact_capacity_no_eviction(self):
        cache = LRUCache(max_size=2)
        cache.set("a", 1)
        cache.set("b", 2)
        assert cache.size() == 2
        assert cache.get("a") == 1
        assert cache.get("b") == 2

    def test_many_insertions(self):
        cache = LRUCache(max_size=10)
        for i in range(100):
            cache.set(f"key_{i}", i)
        assert cache.size() == 10
        # 最新的 10 個應該在
        for i in range(90, 100):
            assert cache.get(f"key_{i}") == i


# ── 並發讀寫 ────────────────────────────────────────────────────

class TestLRUCacheConcurrency:
    """多線程並發讀寫安全。"""

    def test_concurrent_writes(self):
        cache = LRUCache(max_size=1000)
        errors = []

        def _write(start):
            try:
                for i in range(100):
                    cache.set(f"key_{start}_{i}", i)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=_write, args=(t,)) for t in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert len(errors) == 0
        assert cache.size() <= 1000

    def test_concurrent_reads_and_writes(self):
        cache = LRUCache(max_size=500)
        cache.set("shared", "initial")
        errors = []

        def _read():
            try:
                for _ in range(200):
                    cache.get("shared")
            except Exception as e:
                errors.append(e)

        def _write():
            try:
                for i in range(200):
                    cache.set(f"writer_{i}", i)
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=_read) for _ in range(4)
        ] + [
            threading.Thread(target=_write) for _ in range(4)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert len(errors) == 0

    def test_concurrent_delete_and_read(self):
        cache = LRUCache(max_size=100)
        for i in range(50):
            cache.set(f"key_{i}", i)
        errors = []

        def _delete():
            try:
                for i in range(50):
                    cache.delete(f"key_{i}")
            except Exception as e:
                errors.append(e)

        def _read():
            try:
                for i in range(50):
                    cache.get(f"key_{i}")
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=_delete)
        t2 = threading.Thread(target=_read)
        t1.start()
        t2.start()
        t1.join(timeout=5)
        t2.join(timeout=5)

        assert len(errors) == 0


# ── CacheManager ────────────────────────────────────────────────

class TestCacheManager:
    """CacheManager 統一接口（Redis 不可用時降級到 LRU）。"""

    @pytest.fixture
    def mgr(self):
        return CacheManager()

    def test_set_and_get(self, mgr):
        mgr.set("test_key", {"data": 123}, ttl=60)
        assert mgr.get("test_key") == {"data": 123}

    def test_delete(self, mgr):
        mgr.set("to_delete", "value")
        mgr.delete("to_delete")
        assert mgr.get("to_delete") is None

    def test_clear(self, mgr):
        mgr.set("a", 1)
        mgr.set("b", 2)
        mgr.clear()
        assert mgr.get("a") is None

    def test_stats(self, mgr):
        stats = mgr.stats()
        assert "backend" in stats
        assert "lru_size" in stats

    def test_large_value(self, mgr):
        """大 value 不崩潰。"""
        big = "x" * 100000
        mgr.set("big", big)
        assert mgr.get("big") == big
