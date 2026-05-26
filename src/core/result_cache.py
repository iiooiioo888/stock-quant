"""
計算結果緩存 — 回測 / 優化 / 組合等重型任務結果

- 默認使用 cache.CacheManager（本地 LRU，可選 Redis）
- 緩存 key 含參數哈希 + 數據版本（K 線最新日期），數據更新後自動失效
"""
from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Optional

from src.utils.logger import logger

# 與 cache.py 前綴區分
PREFIX_COMPUTE = "sq:compute:"

_NS_TTL_ATTR = {
    "backtest": "cache_backtest_ttl",
    "backtest_advanced": "cache_backtest_ttl",
    "backtest_multi": "cache_multi_strategy_ttl",
    "optimize": "cache_optimize_ttl",
    "portfolio": "cache_portfolio_ttl",
    "walkforward": "cache_walkforward_ttl",
    "heatmap": "cache_heatmap_ttl",
    "auto_optimize": "cache_optimize_ttl",
}


def is_cache_enabled() -> bool:
    try:
        from src.config import settings
        return bool(getattr(settings, "cache_enabled", True))
    except Exception:
        return True


def _ttl_for_namespace(namespace: str) -> int:
    from src.config import settings
    attr = _NS_TTL_ATTR.get(namespace, "cache_backtest_ttl")
    return int(getattr(settings, attr, 3600))


def _code_from_params(params: dict) -> Optional[str]:
    if not params:
        return None
    code = params.get("code")
    if code:
        return str(code)
    codes = params.get("codes")
    if isinstance(codes, list) and codes:
        return str(codes[0])
    allocations = params.get("allocations")
    if isinstance(allocations, list) and allocations:
        c = allocations[0].get("code") if isinstance(allocations[0], dict) else None
        if c:
            return str(c)
    return None


def get_data_version(code: Optional[str] = None) -> str:
    """用 K 線最新日期或 DB 修改時間作為版本號，數據變更後緩存失效"""
    try:
        if code:
            from src.core.db import get_latest_date
            latest = get_latest_date(code)
            if latest:
                return f"{code}:{latest}"
        from src.config import settings
        db_path = settings.db_path
        if os.path.exists(db_path):
            return f"db:{int(os.path.getmtime(db_path))}"
    except Exception:
        pass
    return "v0"


def _params_digest(params: dict) -> str:
    normalized = json.dumps(params, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.md5(normalized.encode()).hexdigest()[:16]


def make_compute_key(namespace: str, params: dict, code: Optional[str] = None) -> str:
    code = code or _code_from_params(params)
    version = get_data_version(code)
    digest = _params_digest(params)
    return f"{PREFIX_COMPUTE}{namespace}:{digest}:{version}"


def get_cached_compute(
    namespace: str,
    params: dict,
    code: Optional[str] = None,
) -> Optional[Any]:
    if not is_cache_enabled():
        return None
    from src.core.cache import get_cache
    key = make_compute_key(namespace, params, code=code)
    hit = get_cache().get(key)
    if hit is not None:
        logger.info(f"緩存命中: {namespace} ({key[-24:]})")
    return hit


def set_cached_compute(
    namespace: str,
    params: dict,
    result: Any,
    code: Optional[str] = None,
    ttl: Optional[int] = None,
) -> None:
    if not is_cache_enabled() or result is None:
        return
    from src.core.cache import get_cache
    from src.core.task_manager import _to_json_safe

    key = make_compute_key(namespace, params, code=code)
    ttl = ttl if ttl is not None else _ttl_for_namespace(namespace)
    safe = _to_json_safe(result)
    get_cache().set(key, safe, ttl=ttl)
    logger.debug(f"緩存寫入: {namespace} ttl={ttl}s")


def drop_cached_compute(
    namespace: str,
    params: dict,
    code: Optional[str] = None,
) -> bool:
    """刪除單條計算緩存（強制重算時使用）。"""
    if not is_cache_enabled():
        return False
    from src.core.cache import get_cache
    key = make_compute_key(namespace, params, code=code)
    get_cache().delete(key)
    logger.info(f"緩存已刪除: {namespace} ({key[-32:]})")
    return True


def invalidate_compute(code: Optional[str] = None) -> int:
    """
    清除計算緩存。code 不為空時僅清除含該代碼版本前綴的項（LRU 全掃；Redis 按前綴刪除）。
    """
    from src.core.cache import get_cache
    cache = get_cache()
    removed = 0

    if cache.is_redis_available:
        try:
            pattern = f"{PREFIX_COMPUTE}*"
            if code:
                pattern = f"{PREFIX_COMPUTE}*:{code}:*"
            cursor = 0
            while True:
                cursor, keys = cache._redis_client.scan(cursor, match=pattern, count=200)
                if keys:
                    cache._redis_client.delete(*keys)
                    removed += len(keys)
                if cursor == 0:
                    break
        except Exception as e:
            logger.debug(f"Redis 緩存清除失敗: {e}")

    # LRU：遍歷刪除
    lru = cache._lru
    prefix = PREFIX_COMPUTE
    to_del = []
    for k in list(lru._cache.keys()):
        if not k.startswith(prefix):
            continue
        if code is not None and code not in k:
            continue
        to_del.append(k)
    for k in to_del:
        lru.delete(k)
        removed += 1

    if removed:
        logger.info(f"計算緩存已清除: {removed} 項" + (f" (code={code})" if code else ""))
    return removed


def cache_stats() -> dict:
    from src.core.cache import get_cache
    base = get_cache().stats()
    base["enabled"] = is_cache_enabled()
    base["prefix"] = PREFIX_COMPUTE
    return base
