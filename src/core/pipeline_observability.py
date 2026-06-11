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
_rate_limit_429: dict[str, int] = defaultdict(int)
_fetch_latency_ms: dict[str, list[float]] = defaultdict(list)
_LATENCY_SAMPLES_MAX = 200
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


def record_rate_limit_429(source: str) -> None:
    """記錄資料源 HTTP 429 次數。"""
    key = (source or "unknown").strip() or "unknown"
    with _lock:
        _inc(_rate_limit_429, key)


def record_fetch_latency(source: str, latency_ms: float) -> None:
    """記錄單次拉取延遲（毫秒），各源保留最近 N 筆樣本。"""
    key = (source or "unknown").strip() or "unknown"
    if latency_ms < 0:
        return
    with _lock:
        samples = _fetch_latency_ms[key]
        samples.append(float(latency_ms))
        if len(samples) > _LATENCY_SAMPLES_MAX:
            del samples[: len(samples) - _LATENCY_SAMPLES_MAX]


def _latency_summary(samples: list[float]) -> dict[str, float]:
    if not samples:
        return {}
    ordered = sorted(samples)
    n = len(ordered)
    return {
        "count": n,
        "avg_ms": round(sum(ordered) / n, 2),
        "p50_ms": round(ordered[n // 2], 2),
        "p95_ms": round(ordered[min(n - 1, int(n * 0.95))], 2),
        "max_ms": round(ordered[-1], 2),
    }


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
        metrics = {
            "uptime_sec": int(time.time() - _started_at),
            "cache": {
                "defer_total": _cache_defer,
                "flush_total": _cache_flush,
                "pending_deferred": get_deferred_cache_clear_count(),
            },
            "kline": {
                "persist_rows_total": _kline_persist_rows,
                "fetch_by_source": dict(sorted(_kline_fetch.items())),
                "rate_limit_429_by_source": dict(sorted(_rate_limit_429.items())),
                "latency_by_source": {
                    k: _latency_summary(v) for k, v in sorted(_fetch_latency_ms.items())
                },
            },
            "financials": {
                "get_fundamentals": dict(sorted(_financials.items())),
                "resolve_financials": dict(sorted(_financials_resolve.items())),
            },
        }

    # 熔斷器狀態（無需鎖，內部自行同步）
    try:
        from src.core.circuit_breaker import get_all_breakers

        breakers = get_all_breakers()
        tripped = {k: v for k, v in breakers.items() if v.get("is_open")}
        metrics["circuit_breakers"] = {
            "total": len(breakers),
            "tripped": len(tripped),
            "sources": breakers,
        }
    except Exception:
        metrics["circuit_breakers"] = {"total": 0, "tripped": 0, "sources": {}}

    return metrics


def reset_pipeline_metrics() -> None:
    """測試用：重置計數器。"""
    global _cache_defer, _cache_flush, _kline_persist_rows, _started_at
    with _lock:
        _cache_defer = 0
        _cache_flush = 0
        _kline_persist_rows = 0
        _kline_fetch.clear()
        _rate_limit_429.clear()
        _fetch_latency_ms.clear()
        _financials.clear()
        _financials_resolve.clear()
        _started_at = time.time()
