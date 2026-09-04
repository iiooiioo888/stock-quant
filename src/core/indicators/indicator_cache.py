"""進程內 LRU 指標緩存 — 多策略共用同一條 K 線時避免重複計算 RSI/MACD/SMA。"""

from __future__ import annotations

import hashlib
import threading
from collections import OrderedDict
from typing import Any, Callable

import numpy as np

_LOCK = threading.Lock()
_MAX = 256
_STORE: OrderedDict[str, Any] = OrderedDict()
_HITS = 0
_MISSES = 0


def _digest(arr: np.ndarray, extra: tuple) -> str:
    a = np.ascontiguousarray(arr, dtype=np.float64)
    h = hashlib.blake2b(digest_size=12)
    h.update(str(a.shape).encode())
    h.update(a.tobytes())
    h.update(repr(extra).encode())
    return h.hexdigest()


def cache_get_or_set(key: str, factory: Callable[[], Any]) -> Any:
    global _HITS, _MISSES
    with _LOCK:
        if key in _STORE:
            _STORE.move_to_end(key)
            val = _STORE[key]
            _HITS += 1
            return _clone(val)
        _MISSES += 1
    val = factory()
    with _LOCK:
        _STORE[key] = val
        _STORE.move_to_end(key)
        while len(_STORE) > _MAX:
            _STORE.popitem(last=False)
    return _clone(val)


def _clone(val: Any) -> Any:
    if isinstance(val, np.ndarray):
        return val.copy()
    if isinstance(val, tuple):
        return tuple(_clone(x) for x in val)
    return val


def cached_series(name: str, close: np.ndarray, factory: Callable[[], np.ndarray], **params) -> np.ndarray:
    key = f"{name}:{_digest(close, tuple(sorted(params.items())))}"
    return cache_get_or_set(key, factory)


def cached_tuple(name: str, close: np.ndarray, factory: Callable[[], tuple], **params) -> tuple:
    key = f"{name}:{_digest(close, tuple(sorted(params.items())))}"
    return cache_get_or_set(key, factory)


def cache_stats() -> dict:
    with _LOCK:
        total = _HITS + _MISSES
        hit_rate = (_HITS / total) if total else 0.0
        return {
            "size": len(_STORE),
            "max": _MAX,
            "hits": _HITS,
            "misses": _MISSES,
            "hit_rate": round(hit_rate, 4),
        }


def cache_clear() -> None:
    global _HITS, _MISSES
    with _LOCK:
        _STORE.clear()
        _HITS = 0
        _MISSES = 0


def chunked_apply(
    close: np.ndarray,
    fn: Callable[[np.ndarray], np.ndarray],
    *,
    chunk_size: int = 8000,
    overlap: int = 250,
) -> np.ndarray:
    """超長序列分塊計算，塊間重疊 overlap 根以銜接指標暖機。"""
    n = len(close)
    if n <= chunk_size:
        return fn(close)
    overlap = max(int(overlap), 1)
    out = np.empty(n, dtype=np.float64)
    out[:] = np.nan
    start = 0
    while start < n:
        end = min(n, start + chunk_size)
        left = 0 if start == 0 else start - overlap
        piece = fn(close[left:end])
        skip = start - left
        out[start:end] = piece[skip : skip + (end - start)]
        if end >= n:
            break
        start = end
    return out
