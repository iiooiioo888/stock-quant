"""
Prometheus 指標（可選依賴 prometheus_client）。
"""
from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Optional

_PROMETHEUS = False
REQUEST_LATENCY = None
CACHE_HITS = None
CACHE_MISSES = None
API_REQUESTS = None

try:
    from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

    REQUEST_LATENCY = Histogram(
        "sq_api_request_seconds",
        "API 請求耗時",
        ["method", "endpoint"],
        buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60),
    )
    CACHE_HITS = Counter("sq_cache_hits_total", "緩存命中", ["layer"])
    CACHE_MISSES = Counter("sq_cache_misses_total", "緩存未命中", ["layer"])
    API_REQUESTS = Counter("sq_api_requests_total", "API 請求數", ["method", "endpoint", "status"])
    PIPELINE_CACHE_DEFER = Counter(
        "sq_pipeline_cache_defer_total", "數據管線延遲清快取標記次數",
    )
    PIPELINE_CACHE_FLUSH = Counter(
        "sq_pipeline_cache_flush_total", "數據管線批量清快取執行次數",
    )
    PIPELINE_KLINE_FETCH = Counter(
        "sq_pipeline_kline_fetch_total", "K 線拉取次數", ["source"],
    )
    PIPELINE_FINANCIALS = Counter(
        "sq_pipeline_financials_total", "財報獲取路徑", ["outcome"],
    )
    _PROMETHEUS = True
except ImportError:
    PIPELINE_CACHE_DEFER = None
    PIPELINE_CACHE_FLUSH = None
    PIPELINE_KLINE_FETCH = None
    PIPELINE_FINANCIALS = None
    CONTENT_TYPE_LATEST = "text/plain"


def prometheus_enabled() -> bool:
    return _PROMETHEUS


def observe_request(method: str, endpoint: str, status: int, duration_sec: float) -> None:
    if not _PROMETHEUS:
        return
    ep = _normalize_endpoint(endpoint)
    REQUEST_LATENCY.labels(method=method, endpoint=ep).observe(duration_sec)
    API_REQUESTS.labels(method=method, endpoint=ep, status=str(status)).inc()


def record_cache_hit(layer: str = "l1") -> None:
    if _PROMETHEUS and CACHE_HITS:
        CACHE_HITS.labels(layer=layer).inc()


def record_cache_miss(layer: str = "l1") -> None:
    if _PROMETHEUS and CACHE_MISSES:
        CACHE_MISSES.labels(layer=layer).inc()


def record_pipeline_cache_defer() -> None:
    if _PROMETHEUS and PIPELINE_CACHE_DEFER:
        PIPELINE_CACHE_DEFER.inc()


def record_pipeline_cache_flush() -> None:
    if _PROMETHEUS and PIPELINE_CACHE_FLUSH:
        PIPELINE_CACHE_FLUSH.inc()


def record_pipeline_kline_fetch(source: str) -> None:
    if _PROMETHEUS and PIPELINE_KLINE_FETCH:
        PIPELINE_KLINE_FETCH.labels(source=source or "unknown").inc()


def record_pipeline_financials(outcome: str) -> None:
    if _PROMETHEUS and PIPELINE_FINANCIALS:
        PIPELINE_FINANCIALS.labels(outcome=outcome or "unknown").inc()


def metrics_payload() -> tuple[bytes, str]:
    if not _PROMETHEUS:
        return b"# prometheus_client not installed\n", "text/plain; charset=utf-8"
    return generate_latest(), CONTENT_TYPE_LATEST


def _normalize_endpoint(path: str) -> str:
    if not path:
        return "/"
    parts = path.strip("/").split("/")
    if len(parts) >= 3 and parts[0] == "api":
        if parts[1] == "tasks" and len(parts) >= 3:
            return "/api/tasks/{id}"
        if parts[1] == "backtest" and parts[2] == "result":
            return "/api/backtest/result/{id}"
    return path.split("?")[0][:80]


@contextmanager
def timed_request(method: str, path: str):
    t0 = time.perf_counter()
    status = 500
    try:
        yield
        status = 200
    finally:
        observe_request(method, path, status, time.perf_counter() - t0)
