"""
Redis 緩存層 — 支持 Redis 和本地 LRU 回退
提供統一的 get/set 接口，Redis 不可用時自動降級到內存 LRU 緩存
"""
import json
import time
from functools import lru_cache
from collections import OrderedDict
from typing import Optional, Any
from src.config import settings
from src.utils.logger import logger


class LRUCache:
    """
    本地 LRU 緩存（Redis 不可用時的回退方案）
    基於 OrderedDict 實現，支持 TTL 過期
    """

    def __init__(self, max_size: int = 1024):
        self._cache: OrderedDict[str, tuple[Any, float]] = OrderedDict()
        self._max_size = max_size

    def get(self, key: str) -> Optional[Any]:
        """獲取緩存值，過期則返回 None"""
        if key not in self._cache:
            return None
        value, expire_at = self._cache[key]
        if expire_at and time.time() > expire_at:
            # 已過期，刪除
            del self._cache[key]
            return None
        # 移到末尾（最近使用）
        self._cache.move_to_end(key)
        return value

    def set(self, key: str, value: Any, ttl: int = 300):
        """設置緩存值，ttl 為過期秒數（0 表示永不過期）"""
        if key in self._cache:
            self._cache.move_to_end(key)
        expire_at = time.time() + ttl if ttl > 0 else 0
        self._cache[key] = (value, expire_at)
        # 超出容量時淘汰最舊的
        while len(self._cache) > self._max_size:
            self._cache.popitem(last=False)

    def delete(self, key: str):
        """刪除緩存項"""
        self._cache.pop(key, None)

    def clear(self):
        """清空緩存"""
        self._cache.clear()

    def size(self) -> int:
        """當前緩存項數量"""
        return len(self._cache)


class CacheManager:
    """
    統一緩存管理器。
    優先使用 Redis，不可用時自動降級到本地 LRU。
    Redis 命中時回填 L1，避免 Redis 短暫不可用後 L1 全冷。
    """

    def __init__(self):
        self._redis_client = None
        lru_max = int(getattr(settings, "cache_lru_max_size", 2048))
        self._lru = LRUCache(max_size=max(128, lru_max))
        self._redis_available = False
        self._hits_l1 = 0
        self._hits_l2 = 0
        self._misses = 0
        self._init_redis()

    def _init_redis(self):
        """嘗試初始化 Redis 連接"""
        if not settings.redis_enabled:
            logger.info("📦 緩存: Redis 未啟用，使用本地 LRU 緩存")
            return

        try:
            import redis
            self._redis_client = redis.from_url(
                settings.redis_url,
                decode_responses=True,
                socket_connect_timeout=3,
                socket_timeout=3,
            )
            # 測試連接
            self._redis_client.ping()
            self._redis_available = True
            logger.info(f"📦 緩存: Redis 已連接 ({settings.redis_url})")
        except ImportError:
            logger.warning("📦 緩存: redis-py 未安裝，使用本地 LRU 緩存")
        except Exception as e:
            logger.warning(f"📦 緩存: Redis 連接失敗 ({e})，使用本地 LRU 緩存")

    @property
    def is_redis_available(self) -> bool:
        """Redis 是否可用"""
        return self._redis_available

    def get(self, key: str) -> Optional[Any]:
        """
        獲取緩存值。
        優先嘗試 Redis，失敗則回退到 LRU。
        """
        l1 = self._lru.get(key)
        if l1 is not None:
            self._hits_l1 += 1
            try:
                from src.utils.metrics import record_cache_hit
                record_cache_hit("l1")
            except Exception:
                pass
            return l1

        if self._redis_available:
            try:
                raw = self._redis_client.get(key)
                if raw is not None:
                    value = json.loads(raw)
                    self._hits_l2 += 1
                    self._lru.set(key, value, ttl=0)
                    try:
                        from src.utils.metrics import record_cache_hit
                        record_cache_hit("l2")
                    except Exception:
                        pass
                    return value
            except Exception as e:
                logger.debug(f"Redis GET 失敗: {e}，回退 LRU")
                self._redis_available = False

        self._misses += 1
        try:
            from src.utils.metrics import record_cache_miss
            record_cache_miss("l1")
        except Exception:
            pass
        return None

    def set(self, key: str, value: Any, ttl: int = 300):
        """
        設置緩存值。
        同時寫入 Redis 和 LRU（保證一致性）。
        """
        serialized = json.dumps(value, ensure_ascii=False, default=str)

        # 寫入 Redis
        if self._redis_available:
            try:
                if ttl > 0:
                    self._redis_client.setex(key, ttl, serialized)
                else:
                    self._redis_client.set(key, serialized)
            except Exception as e:
                logger.debug(f"Redis SET 失敗: {e}")
                self._redis_available = False

        # 同時寫入 LRU（雙寫保證）
        self._lru.set(key, value, ttl)

    def delete(self, key: str):
        """刪除緩存項"""
        if self._redis_available:
            try:
                self._redis_client.delete(key)
            except Exception:
                pass
        self._lru.delete(key)

    def clear(self):
        """清空所有緩存"""
        if self._redis_available:
            try:
                self._redis_client.flushdb()
            except Exception:
                pass
        self._lru.clear()

    def stats(self) -> dict:
        """獲取緩存統計信息"""
        total_hits = self._hits_l1 + self._hits_l2
        lookups = total_hits + self._misses
        stats = {
            "backend": "redis" if self._redis_available else "lru",
            "lru_size": self._lru.size(),
            "hits_l1": self._hits_l1,
            "hits_l2": self._hits_l2,
            "misses": self._misses,
            "hit_rate": round(total_hits / lookups, 4) if lookups else None,
        }
        if self._redis_available:
            try:
                info = self._redis_client.info("memory")
                stats["redis_memory_used"] = info.get("used_memory_human", "N/A")
                stats["redis_keys"] = self._redis_client.dbsize()
            except Exception:
                pass
        return stats


# 全局單例
_cache: Optional[CacheManager] = None


def get_cache() -> CacheManager:
    """獲取全局緩存管理器（懶初始化）"""
    global _cache
    if _cache is None:
        _cache = CacheManager()
    return _cache


# ============================================================
# 業務緩存快捷方法
# ============================================================

# 緩存 key 前綴

CACHE_INVALIDATION_RULES = {
    "kline:*": {"trigger": "data_update", "scope": "code_specific"},
    "backtest:*": {"trigger": "strategy_change", "scope": "param_hash"},
    "optimize:*": {"trigger": "market_regime_change", "scope": "global"},
    "sq:compute:*": {"trigger": "data_update", "scope": "code_specific"},
}


def invalidate_by_rule(trigger: str, code: str | None = None) -> int:
    """按規則觸發失效（L1 + Redis 前綴）。"""
    removed = 0
    cache = get_cache()
    prefixes = [
        k.replace("*", "")
        for k, rule in CACHE_INVALIDATION_RULES.items()
        if rule.get("trigger") == trigger
    ]
    for prefix in prefixes:
        if code and rule_scope_is_code_specific(prefix):
            pattern = f"{prefix}*{code}*"
        else:
            pattern = f"{prefix}*"
        if cache.is_redis_available:
            try:
                cursor = 0
                while True:
                    cursor, keys = cache._redis_client.scan(cursor, match=pattern, count=200)
                    if keys:
                        cache._redis_client.delete(*keys)
                        removed += len(keys)
                    if cursor == 0:
                        break
            except Exception:
                pass
        for k in list(cache._lru._cache.keys()):
            if k.startswith(prefix.rstrip(":")) and (code is None or code in k):
                cache._lru.delete(k)
                removed += 1
    return removed


def rule_scope_is_code_specific(prefix: str) -> bool:
    for k, rule in CACHE_INVALIDATION_RULES.items():
        if k.startswith(prefix):
            return rule.get("scope") == "code_specific"
    return False

PREFIX_KLINE = "sq:kline:"
PREFIX_REALTIME = "sq:rt:"
PREFIX_BACKTEST = "sq:bt:"

# TTL 常量（秒）
TTL_KLINE_DAY = 86400       # 日 K 數據：1 天
TTL_REALTIME = 10            # 實時行情：10 秒
TTL_BACKTEST = 3600          # 回測結果：1 小時


def get_cached_kline(code: str) -> Optional[list]:
    """獲取緩存的日 K 數據"""
    cache = get_cache()
    return cache.get(f"{PREFIX_KLINE}{code}")


def set_cached_kline(code: str, data: list):
    """緩存日 K 數據（TTL: 1 天）"""
    cache = get_cache()
    cache.set(f"{PREFIX_KLINE}{code}", data, ttl=TTL_KLINE_DAY)


def get_cached_realtime(code: str) -> Optional[dict]:
    """獲取緩存的實時行情"""
    cache = get_cache()
    return cache.get(f"{PREFIX_REALTIME}{code}")


def set_cached_realtime(code: str, data: dict):
    """緩存實時行情（TTL: 10 秒）"""
    cache = get_cache()
    cache.set(f"{PREFIX_REALTIME}{code}", data, ttl=TTL_REALTIME)


def get_cached_backtest(key: str) -> Optional[dict]:
    """獲取緩存的回測結果"""
    cache = get_cache()
    return cache.get(f"{PREFIX_BACKTEST}{key}")


def set_cached_backtest(key: str, data: dict):
    """緩存回測結果（TTL: 1 小時）"""
    cache = get_cache()
    cache.set(f"{PREFIX_BACKTEST}{key}", data, ttl=TTL_BACKTEST)
