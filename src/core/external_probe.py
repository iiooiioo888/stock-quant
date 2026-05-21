"""
對外接口探活 — 主動 HTTP/業務探測 + 數據源註冊表快照。

供「接口檢查」頁與 GET/POST /api/external/check 使用。
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Callable, Optional

import requests

from src.config import settings
from src.core.data_sources import get_all_sources, health_check
from src.utils.logger import logger

PROBE_TIMEOUT = 12
_last_result: Optional[dict] = None


def _now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _probe_row(
    probe_id: str,
    name: str,
    category: str,
    ok: bool,
    latency_ms: float,
    message: str,
    *,
    status_code: int = None,
    endpoint: str = "",
    detail: dict = None,
) -> dict:
    return {
        "id": probe_id,
        "name": name,
        "category": category,
        "ok": ok,
        "latency_ms": round(latency_ms, 1),
        "status_code": status_code,
        "message": message,
        "endpoint": endpoint,
        "detail": detail or {},
        "checked_at": _now_iso(),
    }


def _timed_probe(fn: Callable[[], dict]) -> dict:
    t0 = time.perf_counter()
    try:
        return fn()
    except Exception as e:
        elapsed = (time.perf_counter() - t0) * 1000
        return _probe_row(
            "unknown", "unknown", "error", False, elapsed, str(e)[:300],
        )


def _http_get_probe(
    probe_id: str,
    name: str,
    category: str,
    url: str,
    *,
    expect_json: bool = True,
    ok_status: tuple = (200,),
) -> dict:
    t0 = time.perf_counter()
    try:
        resp = requests.get(url, timeout=PROBE_TIMEOUT, headers={
            "User-Agent": "stock-quant/external-probe",
            "Accept": "application/json" if expect_json else "*/*",
        })
        elapsed = (time.perf_counter() - t0) * 1000
        ok = resp.status_code in ok_status
        msg = "OK" if ok else f"HTTP {resp.status_code}"
        if ok and expect_json:
            try:
                resp.json()
            except Exception:
                ok = False
                msg = "響應非 JSON"
        return _probe_row(
            probe_id, name, category, ok, elapsed, msg,
            status_code=resp.status_code, endpoint=url,
        )
    except Exception as e:
        elapsed = (time.perf_counter() - t0) * 1000
        return _probe_row(
            probe_id, name, category, False, elapsed, str(e)[:300], endpoint=url,
        )


def probe_registry() -> dict:
    """數據源註冊表（無外網請求）。"""
    t0 = time.perf_counter()
    reg = health_check()
    all_src = get_all_sources()
    cats_ok = sum(1 for v in reg.values() if v.get("status") == "ok")
    cats_total = len(reg)
    elapsed = (time.perf_counter() - t0) * 1000
    ok = cats_ok > 0
    return _probe_row(
        "registry",
        "數據源註冊表",
        "system",
        ok,
        elapsed,
        f"{cats_ok}/{cats_total} 類別可用",
        detail={"health": reg, "sources": all_src},
    )


def probe_polymarket_gamma() -> dict:
    if not settings.polymarket_enabled:
        return _probe_row(
            "polymarket_gamma", "Polymarket Gamma", "polymarket",
            False, 0, "已關閉 SQ_POLYMARKET_ENABLED",
        )
    base = settings.polymarket_gamma_base.rstrip("/")
    return _http_get_probe(
        "polymarket_gamma", "Polymarket Gamma", "polymarket",
        f"{base}/markets?limit=1",
    )


def probe_polymarket_clob() -> dict:
    if not settings.polymarket_enabled:
        return _probe_row(
            "polymarket_clob", "Polymarket CLOB", "polymarket",
            False, 0, "已關閉 SQ_POLYMARKET_ENABLED",
        )
    base = settings.polymarket_clob_base.rstrip("/")
    return _http_get_probe(
        "polymarket_clob", "Polymarket CLOB", "polymarket",
        f"{base}/",
        expect_json=False,
        ok_status=(200, 404),
    )


def probe_polymarket_service() -> dict:
    if not settings.polymarket_enabled:
        return _probe_row(
            "polymarket_service", "Polymarket 業務層", "polymarket",
            False, 0, "已關閉",
        )
    t0 = time.perf_counter()
    try:
        from src.core.polymarket.service import get_polymarket_service
        data = get_polymarket_service().list_markets(limit=1, use_cache=False)
        n = len(data.get("markets") or [])
        elapsed = (time.perf_counter() - t0) * 1000
        ok = n > 0
        return _probe_row(
            "polymarket_service", "Polymarket 業務層", "polymarket",
            ok, elapsed, f"返回 {n} 條市場" if ok else "市場列表為空",
            detail={"source": data.get("source")},
        )
    except Exception as e:
        elapsed = (time.perf_counter() - t0) * 1000
        return _probe_row(
            "polymarket_service", "Polymarket 業務層", "polymarket",
            False, elapsed, str(e)[:300],
        )


def probe_eastmoney_sector() -> dict:
    t0 = time.perf_counter()
    try:
        from src.core.sector import get_sector_list
        rows = get_sector_list("industry") or []
        elapsed = (time.perf_counter() - t0) * 1000
        ok = len(rows) > 0
        return _probe_row(
            "eastmoney_sector", "東財板塊列表", "a_share",
            ok, elapsed, f"{len(rows)} 條" if ok else "無數據",
        )
    except Exception as e:
        elapsed = (time.perf_counter() - t0) * 1000
        return _probe_row(
            "eastmoney_sector", "東財板塊列表", "a_share",
            False, elapsed, str(e)[:300],
        )


def probe_eastmoney_sector_fund() -> dict:
    t0 = time.perf_counter()
    try:
        from src.core.sector import get_sector_capital_flow
        rows = get_sector_capital_flow(sector_type="industry") or []
        elapsed = (time.perf_counter() - t0) * 1000
        degraded = any(r.get("degraded") for r in rows[:5])
        ok = len(rows) > 0
        msg = f"{len(rows)} 條"
        if degraded:
            msg += "（降級：無主力淨額）"
        return _probe_row(
            "eastmoney_sector_fund", "東財板塊資金", "a_share",
            ok, elapsed, msg,
            detail={"degraded": degraded},
        )
    except Exception as e:
        elapsed = (time.perf_counter() - t0) * 1000
        return _probe_row(
            "eastmoney_sector_fund", "東財板塊資金", "a_share",
            False, elapsed, str(e)[:300],
        )


def probe_yahoo_a_share() -> dict:
    t0 = time.perf_counter()
    try:
        from src.core.yahoo_finance import fetch_a_share_realtime
        row = fetch_a_share_realtime("000001")
        elapsed = (time.perf_counter() - t0) * 1000
        ok = bool(row and row.get("price"))
        return _probe_row(
            "yahoo_a_share", "Yahoo A股行情", "a_share",
            ok, elapsed,
            f"000001 現價 {row.get('price')}" if ok else "無報價",
        )
    except Exception as e:
        elapsed = (time.perf_counter() - t0) * 1000
        return _probe_row(
            "yahoo_a_share", "Yahoo A股行情", "a_share",
            False, elapsed, str(e)[:300],
        )


def probe_binance() -> dict:
    return _http_get_probe(
        "binance", "Binance 現貨", "crypto",
        "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT",
    )


def probe_frankfurter() -> dict:
    return _http_get_probe(
        "frankfurter", "Frankfurter 外匯", "forex",
        "https://api.frankfurter.app/latest?from=USD&to=CNY",
    )


def probe_redis() -> dict:
    t0 = time.perf_counter()
    if not settings.redis_enabled:
        return _probe_row(
            "redis", "Redis 緩存", "system",
            True, 0, "未啟用（跳過）",
            detail={"skipped": True},
        )
    try:
        from src.core.cache import get_cache
        cache = get_cache()
        available = cache.is_redis_available
        elapsed = (time.perf_counter() - t0) * 1000
        return _probe_row(
            "redis", "Redis 緩存", "system",
            available, elapsed,
            "連接正常" if available else "不可用",
            detail=cache.stats(),
        )
    except Exception as e:
        elapsed = (time.perf_counter() - t0) * 1000
        return _probe_row(
            "redis", "Redis 緩存", "system",
            False, elapsed, str(e)[:300],
        )


def probe_notify_webhook() -> dict:
    if not settings.notify_webhook or not settings.webhook_url:
        return _probe_row(
            "notify_webhook", "Webhook 通知", "notify",
            True, 0, "未配置（跳過）",
            detail={"skipped": True},
        )
    t0 = time.perf_counter()
    try:
        from src.core.alerts import test_all_channels
        results = test_all_channels()
        elapsed = (time.perf_counter() - t0) * 1000
        wh = results.get("webhook", "skipped")
        ok = wh == "ok"
        return _probe_row(
            "notify_webhook", "Webhook 通知", "notify",
            ok, elapsed, str(wh),
            detail=results,
        )
    except Exception as e:
        elapsed = (time.perf_counter() - t0) * 1000
        return _probe_row(
            "notify_webhook", "Webhook 通知", "notify",
            False, elapsed, str(e)[:300],
        )


# 探針目錄（供前端展示）
PROBE_CATALOG = [
    {"id": "registry", "name": "數據源註冊表", "category": "system", "active": True},
    {"id": "redis", "name": "Redis 緩存", "category": "system", "active": True},
    {"id": "yahoo_a_share", "name": "Yahoo A股行情", "category": "a_share", "active": True},
    {"id": "eastmoney_sector", "name": "東財板塊列表", "category": "a_share", "active": True},
    {"id": "eastmoney_sector_fund", "name": "東財板塊資金", "category": "a_share", "active": True},
    {"id": "binance", "name": "Binance 現貨", "category": "crypto", "active": True},
    {"id": "frankfurter", "name": "Frankfurter 外匯", "category": "forex", "active": True},
    {"id": "polymarket_gamma", "name": "Polymarket Gamma", "category": "polymarket", "active": True},
    {"id": "polymarket_clob", "name": "Polymarket CLOB", "category": "polymarket", "active": True},
    {"id": "polymarket_service", "name": "Polymarket 業務層", "category": "polymarket", "active": True},
    {"id": "notify_webhook", "name": "Webhook 通知", "category": "notify", "active": True},
]

_PROBE_FUNCS: dict[str, Callable[[], dict]] = {
    "registry": probe_registry,
    "redis": probe_redis,
    "yahoo_a_share": probe_yahoo_a_share,
    "eastmoney_sector": probe_eastmoney_sector,
    "eastmoney_sector_fund": probe_eastmoney_sector_fund,
    "binance": probe_binance,
    "frankfurter": probe_frankfurter,
    "polymarket_gamma": probe_polymarket_gamma,
    "polymarket_clob": probe_polymarket_clob,
    "polymarket_service": probe_polymarket_service,
    "notify_webhook": probe_notify_webhook,
}


def run_all_probes(probe_ids: list[str] = None, max_workers: int = 6) -> dict:
    """並行執行探針，返回匯總結果。"""
    global _last_result
    ids = probe_ids or list(_PROBE_FUNCS.keys())
    started = time.perf_counter()
    probes: list[dict] = []

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(_PROBE_FUNCS[pid]): pid
            for pid in ids
            if pid in _PROBE_FUNCS
        }
        for fut in as_completed(futures):
            pid = futures[fut]
            try:
                probes.append(fut.result())
            except Exception as e:
                probes.append(_probe_row(
                    pid, pid, "error", False, 0, str(e)[:300],
                ))

    probes.sort(key=lambda p: p.get("id", ""))
    ok_n = sum(1 for p in probes if p.get("ok"))
    fail_n = len(probes) - ok_n
    elapsed_total = (time.perf_counter() - started) * 1000

    if fail_n == 0:
        overall = "ok"
    elif ok_n > 0:
        overall = "degraded"
    else:
        overall = "fail"

    result = {
        "status": overall,
        "checked_at": _now_iso(),
        "duration_ms": round(elapsed_total, 1),
        "summary": {"total": len(probes), "ok": ok_n, "fail": fail_n},
        "probes": probes,
        "registry": health_check(),
    }
    _last_result = result
    logger.info(f"對外接口探活完成: {ok_n}/{len(probes)} 通過, {round(elapsed_total)}ms")
    return result


def get_last_probe_result() -> Optional[dict]:
    return _last_result


def get_registry_only() -> dict:
    """僅註冊表快照，不發外網請求。"""
    return {
        "checked_at": _now_iso(),
        "registry": health_check(),
        "sources": get_all_sources(),
        "catalog": PROBE_CATALOG,
    }
