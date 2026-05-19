"""
輕量 API 響應緩存 — 減少重複的 DB 統計與列表查詢
"""
import time
from typing import Any, Callable, Optional

from src.utils.logger import logger

_store: dict[str, tuple[float, Any]] = {}
_DEFAULT_TTL = 5


def get_cached(key: str) -> Optional[Any]:
    entry = _store.get(key)
    if not entry:
        return None
    expire_at, value = entry
    if expire_at and time.time() > expire_at:
        _store.pop(key, None)
        return None
    return value


def set_cached(key: str, value: Any, ttl: int = _DEFAULT_TTL) -> None:
    expire_at = time.time() + ttl if ttl > 0 else 0
    _store[key] = (expire_at, value)


def invalidate_prefix(prefix: str) -> None:
    keys = [k for k in _store if k.startswith(prefix)]
    for k in keys:
        _store.pop(k, None)
    if keys:
        logger.debug(f"API 緩存失效: {prefix}* ({len(keys)} 項)")


def clear_all() -> None:
    _store.clear()


def cached_response(key: str, ttl: int, builder: Callable[[], Any]) -> Any:
    """讀取緩存或執行 builder 並寫入"""
    hit = get_cached(key)
    if hit is not None:
        return hit
    value = builder()
    set_cached(key, value, ttl)
    return value
