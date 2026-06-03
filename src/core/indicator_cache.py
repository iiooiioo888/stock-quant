"""
預計算指標緩存 — 疊加 result_cache + 數據版本，K 線更新後自動失效。
"""
from __future__ import annotations

from typing import Any, Callable, Optional

import numpy as np

from src.core.indicators.fast_indicators import compute_macd, compute_rsi
from src.utils.logger import logger


def _ns(name: str) -> str:
    return f"indicator_{name}"


def get_or_compute(
    code: str,
    indicator: str,
    params: dict,
    builder: Callable[[], Any],
    ttl: int = 86400,
) -> Any:
    from src.core.result_cache import get_cached_compute, is_cache_enabled, set_cached_compute

    if not is_cache_enabled():
        return builder()

    payload = {"code": code, **params}
    hit = get_cached_compute(_ns(indicator), payload, code=code)
    if hit is not None:
        return hit
    result = builder()
    set_cached_compute(_ns(indicator), payload, result, code=code, ttl=ttl)
    return result


def cached_rsi(code: str, period: int = 14) -> np.ndarray:
    from src.core.db import load_daily_kline

    def _build():
        df = load_daily_kline(code)
        if df.empty:
            return []
        arr = compute_rsi(df["close"].astype(float).to_numpy(), period)
        return arr.tolist()

    return np.asarray(
        get_or_compute(code, "rsi", {"period": period}, _build),
        dtype=np.float64,
    )


def cached_macd(
    code: str,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    from src.core.db import load_daily_kline

    params = {"fast": fast, "slow": slow, "signal": signal}

    def _build():
        df = load_daily_kline(code)
        if df.empty:
            return [[], [], []]
        c = df["close"].astype(float).to_numpy()
        line, sig, hist = compute_macd(c, fast=fast, slow=slow, signal=signal)
        return [line.tolist(), sig.tolist(), hist.tolist()]

    raw = get_or_compute(code, "macd", params, _build)
    if not raw or len(raw) != 3:
        empty = np.array([], dtype=np.float64)
        return empty, empty, empty
    return (
        np.asarray(raw[0], dtype=np.float64),
        np.asarray(raw[1], dtype=np.float64),
        np.asarray(raw[2], dtype=np.float64),
    )


def cached_latest_atr(code: str, period: int = 14) -> float:
    from src.core.db import load_daily_kline
    from src.core.indicators.fast_indicators import latest_atr

    def _build():
        df = load_daily_kline(code)
        if df.empty or len(df) < period + 1:
            return 0.0
        tail = df.tail(period + 30)
        return latest_atr(
            tail["high"].astype(float).to_numpy(),
            tail["low"].astype(float).to_numpy(),
            tail["close"].astype(float).to_numpy(),
            period,
        )

    return float(get_or_compute(code, "atr_latest", {"period": period}, _build))


def warm_indicators_for_code(code: str, periods: Optional[list[int]] = None) -> None:
    periods = periods or [14]
    for p in periods:
        try:
            cached_rsi(code, period=p)
            cached_latest_atr(code, period=p)
        except Exception as e:
            logger.debug(f"指標預熱跳過 {code} p={p}: {e}")
