"""
數據管線觀測指標 — 進程內計數器（MCP / 健康檢查 / 可選 Prometheus）。

追蹤：快取延遲清理、K 線寫入、行情拉取來源、財報命中路徑。
"""
from __future__ import annotations

import time
from collections import defaultdict
from threading import Lock
from typing import Any

_lock = Lock()
_started_at = time.time()

_cache_defer: int = 0
_cache_flush: int = 0
_kline_persist_rows: int = 0
_kline_fetch: dict[str, int] = defaultdict(int)
_financials: dict[str, int] = defaultdict(int)
_financials_resolve: dict[str, int] = defaultdict(int)


def _inc(counter: dict[str, int], key: str, n: int = 1) -> None:
    counter[key] = counter.get(key, 0) + n


def record_cache_defer(n: int = 1) -> None:
    global _cache_defer
    with _lock:
        _cache_defer += max(1, n)
    try:
        from src.utils.metrics import record_pipeline_cache_defer

        for _ in range(max(1, n)):
            record_pipeline_cache_defer()
    except Exception:
        pass


def record_cache_flush(batch_n: int = 1) -> None:
    global _cache_flush
    with _lock:
        _cache_flush += 1
    try:
        from src.utils.metrics import record_pipeline_cache_flush

        record_pipeline_cache_flush()
    except Exception:
        pass


def record_kline_persist(rows: int) -> None:
    global _kline_persist_rows
    if rows <= 0:
        return
    with _lock:
        _kline_persist_rows += rows


def record_kline_fetch(source: str) -> None:
    key = (source or "unknown").strip() or "unknown"
    with _lock:
        _inc(_kline_fetch, key)
    try:
        from src.utils.metrics import record_pipeline_kline_fetch

        record_pipeline_kline_fetch(key)
    except Exception:
        pass


def record_financials(outcome: str) -> None:
    """outcome: db_hit | online_fetch | stale_fallback | empty"""
    key = (outcome or "unknown").strip() or "unknown"
    with _lock:
        _inc(_financials, key)
    try:
        from src.utils.metrics import record_pipeline_financials

        record_pipeline_financials(key)
    except Exception:
        pass


def record_financials_resolve(path: str) -> None:
    """path: db_fresh | fetched | universe_fallback | empty"""
    key = (path or "unknown").strip() or "unknown"
    with _lock:
        _inc(_financials_resolve, key)


def get_pipeline_metrics() -> dict[str, Any]:
    """返回當前進程管線指標快照。"""
    from src.core.data_pipeline import get_deferred_cache_clear_count

    with _lock:
        return {
            "uptime_sec": int(time.time() - _started_at),
            "cache": {
                "defer_total": _cache_defer,
                "flush_total": _cache_flush,
                "pending_deferred": get_deferred_cache_clear_count(),
            },
            "kline": {
                "persist_rows_total": _kline_persist_rows,
                "fetch_by_source": dict(sorted(_kline_fetch.items())),
            },
            "financials": {
                "get_fundamentals": dict(sorted(_financials.items())),
                "resolve_financials": dict(sorted(_financials_resolve.items())),
            },
        }


def reset_pipeline_metrics() -> None:
    """測試用：重置計數器。"""
    global _cache_defer, _cache_flush, _kline_persist_rows, _started_at
    with _lock:
        _cache_defer = 0
        _cache_flush = 0
        _kline_persist_rows = 0
        _kline_fetch.clear()
        _financials.clear()
        _financials_resolve.clear()
        _started_at = time.time()
