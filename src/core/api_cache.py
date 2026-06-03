"""
輕量 API 響應緩存 — Redis-first + 進程內存降級

優先使用 Redis（跨實例共享），不可用時降級到進程內存。
"""
import json
import time
from typing import Any, Callable, Optional

from src.utils.logger import logger

_DEFAULT_TTL = 5
_CACHE_PREFIX = "ac:"

# 分類 TTL 常量（秒）— 根據數據時效性分級
TTL_REALTIME = 5          # 實時行情、盯盤
TTL_REALTIME_QUOTE = 10   # 個股報價
TTL_CAPITAL_FLOW = 120    # 資金流向（實時性要求高，原 300s → 120s）
TTL_SECTOR_HEATMAP = 120  # 板塊熱力圖
TTL_DASHBOARD = 30        # 儀表盤數據
TTL_CONFIG = 60           # 配置信息
TTL_FUNDAMENTALS = 3600   # 基本面（日內穩定）
TTL_BACKTEST_RESULT = 3600    # 回測結果
TTL_OPTIMIZE_RESULT = 7200    # 優化結果
TTL_STRATEGY_LIST = 300       # 策略列表
TTL_STATIC_REFERENCE = 86400  # 靜態參考數據（指數成分等）

# ---------------------------------------------------------------------------
# 進程內存後備
# ---------------------------------------------------------------------------
_mem_store: dict[str, tuple[float, Any]] = {}

# ---------------------------------------------------------------------------
# Redis 懶初始化
# ---------------------------------------------------------------------------
_redis_client = None
_redis_available = False
_redis_initialized = False


def _get_redis():
    global _redis_client, _redis_available, _redis_initialized
    if _redis_initialized:
        return _redis_client
    _redis_initialized = True
    try:
        from src.config import settings
        if not getattr(settings, "redis_enabled", False):
            return None
        import redis as redis_lib
        url = getattr(settings, "redis_url", "redis://localhost:6379/0")
        pwd = getattr(settings, "redis_password", "")
        _redis_client = redis_lib.from_url(
            url,
            password=pwd or None,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        _redis_client.ping()
        _redis_available = True
        logger.info("✅ API 緩存: Redis 已連接")
        return _redis_client
    except Exception:
        _redis_client = None
        _redis_available = False
        return None


# ---------------------------------------------------------------------------
# 公開接口
# ---------------------------------------------------------------------------

def get_cached(key: str) -> Optional[Any]:
    """讀取緩存；Redis 優先，降級到內存。"""
    # 1. Redis
    r = _get_redis()
    if r:
        try:
            raw = r.get(f"{_CACHE_PREFIX}{key}")
            if raw is not None:
                return json.loads(raw)
        except Exception:
            pass

    # 2. 內存降級
    entry = _mem_store.get(key)
    if not entry:
        return None
    expire_at, value = entry
    if expire_at and time.time() > expire_at:
        _mem_store.pop(key, None)
        return None
    return value


def set_cached(key: str, value: Any, ttl: int = _DEFAULT_TTL) -> None:
    """寫入緩存；Redis 優先，同時寫內存備份。"""
    # 1. Redis
    r = _get_redis()
    if r:
        try:
            serialized = json.dumps(value, ensure_ascii=False, default=str)
            if ttl > 0:
                r.setex(f"{_CACHE_PREFIX}{key}", ttl, serialized)
            else:
                r.set(f"{_CACHE_PREFIX}{key}", serialized)
        except Exception:
            pass

    # 2. 內存備份
    expire_at = time.time() + ttl if ttl > 0 else 0
    _mem_store[key] = (expire_at, value)


def invalidate_prefix(prefix: str) -> None:
    """清除匹配前綴的所有緩存。"""
    # 1. Redis
    r = _get_redis()
    redis_count = 0
    if r:
        try:
            pattern = f"{_CACHE_PREFIX}{prefix}*"
            cursor = 0
            while True:
                cursor, keys = r.scan(cursor, match=pattern, count=100)
                if keys:
                    r.delete(*keys)
                    redis_count += len(keys)
                if cursor == 0:
                    break
        except Exception:
            pass

    # 2. 內存
    mem_keys = [k for k in _mem_store if k.startswith(prefix)]
    for k in mem_keys:
        _mem_store.pop(k, None)

    total = redis_count + len(mem_keys)
    if total:
        logger.debug(f"API 緩存失效: {prefix}* (Redis={redis_count}, 內存={len(mem_keys)})")


def clear_all() -> None:
    """清除全部 API 緩存。"""
    # 1. Redis
    r = _get_redis()
    if r:
        try:
            pattern = f"{_CACHE_PREFIX}*"
            cursor = 0
            while True:
                cursor, keys = r.scan(cursor, match=pattern, count=100)
                if keys:
                    r.delete(*keys)
                if cursor == 0:
                    break
        except Exception:
            pass

    # 2. 內存
    _mem_store.clear()


def cached_response(key: str, ttl: int, builder: Callable[[], Any]) -> Any:
    """讀取緩存或執行 builder 並寫入"""
    hit = get_cached(key)
    if hit is not None:
        return hit
    value = builder()
    set_cached(key, value, ttl)
    return value


def cache_stats() -> dict:
    """返回 API 緩存統計。"""
    r = _get_redis()
    redis_count = 0
    if r:
        try:
            cursor = 0
            while True:
                cursor, keys = r.scan(cursor, match=f"{_CACHE_PREFIX}*", count=100)
                redis_count += len(keys)
                if cursor == 0:
                    break
        except Exception:
            pass
    return {
        "redis_available": bool(r),
        "redis_entries": redis_count,
        "memory_entries": len(_mem_store),
    }
