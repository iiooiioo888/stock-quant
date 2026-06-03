"""
Redis 滑動窗口限流器 — 替代 app.py 的進程內存限流。

當 Redis 不可用時自動降級到進程內存（與現有行為一致）。
跨實例共享限流狀態，支持多 worker 部署。
"""
from __future__ import annotations

import time
from typing import Optional

from src.utils.logger import logger

_PREFIX = "rl:"
_redis_client = None
_available = False
_initialized = False


def _get_redis():
    global _redis_client, _available, _initialized
    if _initialized:
        return _redis_client
    _initialized = True
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
        _available = True
        logger.info("✅ Rate Limiter: Redis 已連接")
        return _redis_client
    except Exception:
        _redis_client = None
        _available = False
        return None


def is_available() -> bool:
    _get_redis()
    return _available


# ---------------------------------------------------------------------------
# Redis 滑動窗口（Sorted Set）
# ---------------------------------------------------------------------------

# Lua script: 原子性清理過期 + 計數 + 插入
_SLIDING_WINDOW_LUA = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local window_start = now - window

-- 移除窗口外的記錄
redis.call('ZREMRANGEBYSCORE', key, '-inf', window_start)

-- 計算當前窗口內的請求數
local count = redis.call('ZCARD', key)

if count < limit then
    -- 允許：添加當前請求
    redis.call('ZADD', key, now, now .. ':' .. math.random(1000000))
    redis.call('EXPIRE', key, window + 1)
    return {1, 0}
else
    -- 拒絕：計算 retry_after
    local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
    local retry_after = 1
    if #oldest >= 2 then
        retry_after = math.ceil(tonumber(oldest[2]) - window_start + 0.5)
        if retry_after < 1 then retry_after = 1 end
    end
    return {0, retry_after}
end
"""

_script_sha: Optional[str] = None


def _load_script(r) -> str:
    global _script_sha
    if _script_sha:
        try:
            # 檢查 script 是否仍在 cache
            r.script_exists(_script_sha)
            return _script_sha
        except Exception:
            _script_sha = None
    try:
        _script_sha = r.script_load(_SLIDING_WINDOW_LUA)
        return _script_sha
    except Exception:
        return ""


def check_rate_limit(
    client_ip: str,
    limit: int,
    window_sec: int = 60,
    namespace: str = "",
) -> tuple[bool, int]:
    """
    滑動窗口限流檢查。
    
    Args:
        client_ip: 客戶端 IP
        limit: 窗口內最大請求數
        window_sec: 窗口大小（秒）
        namespace: 可選命名空間（如 "auth"）
    
    Returns:
        (allowed: bool, retry_after: int)
    """
    r = _get_redis()
    if not r:
        # 降級：使用進程內存限流
        return _memory_check(client_ip, limit, window_sec, namespace)

    key = f"{_PREFIX}{namespace}:{client_ip}" if namespace else f"{_PREFIX}{client_ip}"
    now = time.time()

    try:
        sha = _load_script(r)
        if sha:
            result = r.evalsha(sha, 1, key, str(now), str(window_sec), str(limit))
            allowed = bool(result[0])
            retry_after = int(result[1])
            return allowed, max(retry_after, 0)
        else:
            # script load 失敗，用 EVAL 代替
            result = r.eval(_SLIDING_WINDOW_LUA, 1, key, str(now), str(window_sec), str(limit))
            return bool(result[0]), max(int(result[1]), 0)
    except Exception as e:
        logger.debug(f"Redis rate limit 失敗，降級到內存: {e}")
        return _memory_check(client_ip, limit, window_sec, namespace)


def get_usage(client_ip: str, window_sec: int = 60, namespace: str = "") -> int:
    """查詢 IP 在當前窗口的請求數。"""
    r = _get_redis()
    if not r:
        return 0
    key = f"{_PREFIX}{namespace}:{client_ip}" if namespace else f"{_PREFIX}{client_ip}"
    try:
        now = time.time()
        window_start = now - window_sec
        r.zremrangebyscore(key, "-inf", window_start)
        return r.zcard(key)
    except Exception:
        return 0


def reset(client_ip: str, namespace: str = "") -> None:
    """清除指定 IP 的限流記錄（測試用）。"""
    r = _get_redis()
    if not r:
        return
    key = f"{_PREFIX}{namespace}:{client_ip}" if namespace else f"{_PREFIX}{client_ip}"
    try:
        r.delete(key)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 進程內存降級（兼容現有行為）
# ---------------------------------------------------------------------------

class _MemoryRateLimiter:
    """有界滑動窗口限流器（進程內存）。"""

    _MAX_IPS = 10000
    _EVICT_BATCH = 2000
    _CLEANUP_INTERVAL = 300

    def __init__(self):
        self._store: dict[str, list[float]] = {}
        self._last_seen: dict[str, float] = {}
        self._last_full_cleanup = time.time()

    def check(self, client_ip: str, limit: int, window_sec: int = 60) -> tuple[bool, int]:
        now = time.time()
        window_start = now - window_sec

        if now - self._last_full_cleanup > self._CLEANUP_INTERVAL:
            self._full_cleanup(now)
            self._last_full_cleanup = now

        if len(self._store) >= self._MAX_IPS:
            self._evict_oldest()

        timestamps = self._store.get(client_ip, [])
        timestamps = [t for t in timestamps if t > window_start]

        if len(timestamps) >= limit:
            retry_after = int(timestamps[0] - window_start) + 1
            self._store[client_ip] = timestamps
            self._last_seen[client_ip] = now
            return False, max(retry_after, 1)

        timestamps.append(now)
        self._store[client_ip] = timestamps
        self._last_seen[client_ip] = now
        return True, 0

    def _evict_oldest(self):
        if len(self._last_seen) < self._EVICT_BATCH:
            return
        sorted_ips = sorted(self._last_seen, key=lambda ip: self._last_seen[ip])
        for ip in sorted_ips[: self._EVICT_BATCH]:
            self._store.pop(ip, None)
            self._last_seen.pop(ip, None)

    def _full_cleanup(self, now: float):
        cutoff = now - 120
        stale_ips = [ip for ip, ts in self._last_seen.items() if ts < cutoff]
        for ip in stale_ips:
            self._store.pop(ip, None)
            self._last_seen.pop(ip, None)


_memory_limiters: dict[str, _MemoryRateLimiter] = {}


def _memory_check(client_ip: str, limit: int, window_sec: int, namespace: str) -> tuple[bool, int]:
    key = namespace or "default"
    if key not in _memory_limiters:
        _memory_limiters[key] = _MemoryRateLimiter()
    return _memory_limiters[key].check(client_ip, limit, window_sec)


def stats() -> dict:
    """返回限流器統計。"""
    r = _get_redis()
    if not r:
        return {"backend": "memory", "available": False}
    try:
        count = 0
        cursor = 0
        while True:
            cursor, keys = r.scan(cursor, match=f"{_PREFIX}*", count=100)
            count += len(keys)
            if cursor == 0:
                break
        return {"backend": "redis", "available": True, "tracked_keys": count}
    except Exception as e:
        return {"backend": "redis", "available": False, "error": str(e)}
