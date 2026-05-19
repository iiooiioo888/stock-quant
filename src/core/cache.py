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
    """

    def __init__(self):
        self._redis_client = None
        self._lru = LRUCache(max_size=2048)
        self._redis_available = False
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
        # 嘗試 Redis
        if self._redis_available:
            try:
                raw = self._redis_client.get(key)
                if raw is not None:
                    return json.loads(raw)
                return None
            except Exception as e:
                logger.debug(f"Redis GET 失敗: {e}，回退 LRU")
                self._redis_available = False

        # 回退到 LRU
        return self._lru.get(key)

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
        stats = {
            "backend": "redis" if self._redis_available else "lru",
            "lru_size": self._lru.size(),
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
