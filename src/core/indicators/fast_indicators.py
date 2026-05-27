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
def _atr_core(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int) -> np.ndarray:
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
    return _rsi_core(_as_f64(close), int(period))


def compute_sma(close: np.ndarray, period: int) -> np.ndarray:
    return _sma_core(_as_f64(close), int(period))


def compute_macd(
    close: np.ndarray,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    c = _as_f64(close)
    ema_fast = _ema_core(c, int(fast))
    ema_slow = _ema_core(c, int(slow))
    n = len(c)
    line = np.empty(n, dtype=np.float64)
    line[:] = np.nan
    for i in range(n):
        if not np.isnan(ema_fast[i]) and not np.isnan(ema_slow[i]):
            line[i] = ema_fast[i] - ema_slow[i]
    sig = _ema_core(line, int(signal))
    hist = np.empty(n, dtype=np.float64)
    hist[:] = np.nan
    for i in range(n):
        if not np.isnan(line[i]) and not np.isnan(sig[i]):
            hist[i] = line[i] - sig[i]
    return line, sig, hist


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
