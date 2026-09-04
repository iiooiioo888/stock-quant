"""
RSI / MACD / ATR / SMA — NumPy 實現，可選 Numba 加速。
與 pandas.rolling 結果在常見週期下誤差 < 1e-6。
"""

from __future__ import annotations

import numpy as np

_NUMBA = False
try:
    from numba import jit, prange

    _NUMBA = True
except ImportError:
    prange = range

    def jit(*_args, **_kwargs):
        def deco(fn):
            return fn

        return deco


def engine_name() -> str:
    return "numba" if _NUMBA else "numpy"


@jit(nopython=True, cache=True)
def _wilder_smooth(arr: np.ndarray, period: int) -> np.ndarray:
    n = len(arr)
    out = np.empty(n, dtype=np.float64)
    out[:] = np.nan
    if n < period or period < 1:
        return out
    s = 0.0
    for i in range(period):
        s += arr[i]
    out[period - 1] = s / period
    for i in range(period, n):
        out[i] = (out[i - 1] * (period - 1) + arr[i]) / period
    return out


@jit(nopython=True, cache=True)
def _rsi_core(close: np.ndarray, period: int) -> np.ndarray:
    n = len(close)
    out = np.empty(n, dtype=np.float64)
    out[:] = np.nan
    if n < period + 1:
        return out
    deltas = np.empty(n - 1, dtype=np.float64)
    for i in range(n - 1):
        deltas[i] = close[i + 1] - close[i]
    gains = np.empty(n - 1, dtype=np.float64)
    losses = np.empty(n - 1, dtype=np.float64)
    for i in range(n - 1):
        d = deltas[i]
        if d > 0:
            gains[i] = d
            losses[i] = 0.0
        else:
            gains[i] = 0.0
            losses[i] = -d
    avg_gain = _wilder_smooth(gains, period)
    avg_loss = _wilder_smooth(losses, period)
    for i in range(period, n):
        ag = avg_gain[i - 1]
        al = avg_loss[i - 1]
        if al == 0.0:
            out[i] = 100.0 if ag > 0 else 50.0
        else:
            rs = ag / al
            out[i] = 100.0 - (100.0 / (1.0 + rs))
    return out


@jit(nopython=True, cache=True)
def _ema_core(close: np.ndarray, period: int) -> np.ndarray:
    n = len(close)
    out = np.empty(n, dtype=np.float64)
    out[:] = np.nan
    if n < period or period < 1:
        return out
    alpha = 2.0 / (period + 1.0)
    s = 0.0
    for i in range(period):
        s += close[i]
    out[period - 1] = s / period
    for i in range(period, n):
        out[i] = alpha * close[i] + (1.0 - alpha) * out[i - 1]
    return out


@jit(nopython=True, cache=True)
def _atr_core(
    high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int
) -> np.ndarray:
    n = len(close)
    tr = np.empty(n, dtype=np.float64)
    tr[0] = high[0] - low[0]
    for i in range(1, n):
        hl = high[i] - low[i]
        hc = abs(high[i] - close[i - 1])
        lc = abs(low[i] - close[i - 1])
        tr[i] = max(hl, hc, lc)
    return _wilder_smooth(tr, period)


@jit(nopython=True, cache=True)
def _sma_core(close: np.ndarray, period: int) -> np.ndarray:
    n = len(close)
    out = np.empty(n, dtype=np.float64)
    out[:] = np.nan
    if period < 1 or n < period:
        return out
    s = 0.0
    for i in range(period):
        s += close[i]
    out[period - 1] = s / period
    for i in range(period, n):
        s += close[i] - close[i - period]
        out[i] = s / period
    return out


def _as_f64(arr: np.ndarray) -> np.ndarray:
    return np.asarray(arr, dtype=np.float64).ravel()


def compute_rsi(close: np.ndarray, period: int = 14) -> np.ndarray:
    from src.core.indicators.indicator_cache import cached_series, chunked_apply

    c = _as_f64(close)
    p = int(period)

    def _run():
        return chunked_apply(c, lambda x: _rsi_core(x, p), overlap=max(p * 3, 40))

    return cached_series("rsi", c, _run, period=p)


def compute_sma(close: np.ndarray, period: int) -> np.ndarray:
    from src.core.indicators.indicator_cache import cached_series, chunked_apply

    c = _as_f64(close)
    p = int(period)

    def _run():
        return chunked_apply(c, lambda x: _sma_core(x, p), overlap=p)

    return cached_series("sma", c, _run, period=p)


def compute_ema(close: np.ndarray, period: int) -> np.ndarray:
    from src.core.indicators.indicator_cache import cached_series, chunked_apply

    c = _as_f64(close)
    p = int(period)

    def _run():
        return chunked_apply(c, lambda x: _ema_core(x, p), overlap=p)

    return cached_series("ema", c, _run, period=p)


def compute_macd(
    close: np.ndarray,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    from src.core.indicators.indicator_cache import cached_tuple

    c = _as_f64(close)
    f, s, sig_p = int(fast), int(slow), int(signal)

    def _run():
        ema_fast = _ema_core(c, f)
        ema_slow = _ema_core(c, s)
        line = ema_fast - ema_slow
        sig = _ema_core(line, sig_p)
        hist = line - sig
        return line, sig, hist

    return cached_tuple("macd", c, _run, fast=f, slow=s, signal=sig_p)


def compute_bollinger(
    close: np.ndarray, period: int = 20, num_std: float = 2.0
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    from src.core.indicators.indicator_cache import cached_tuple

    c = _as_f64(close)
    p = int(period)
    ns = float(num_std)

    def _run():
        mid = _sma_core(c, p)
        # 滾動標準差（與 SMA 對齊）
        std = np.empty(len(c), dtype=np.float64)
        std[:] = np.nan
        if len(c) >= p:
            csq = np.convolve(c * c, np.ones(p), mode="valid") / p
            mean = mid[p - 1 :]
            var = np.maximum(csq - mean * mean, 0.0)
            std[p - 1 :] = np.sqrt(var)
        up = mid + ns * std
        lo = mid - ns * std
        return up, mid, lo

    return cached_tuple("bb", c, _run, period=p, num_std=ns)


def compute_atr(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    period: int = 14,
) -> np.ndarray:
    return _atr_core(_as_f64(high), _as_f64(low), _as_f64(close), int(period))


def latest_atr(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    period: int = 14,
) -> float:
    series = compute_atr(high, low, close, period)
    if series.size == 0:
        return 0.0
    for i in range(series.size - 1, -1, -1):
        v = series[i]
        if not np.isnan(v):
            return round(float(v), 4)
    return 0.0
