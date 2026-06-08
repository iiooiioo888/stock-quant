"""快速指標計算與緩存"""

import numpy as np
import pandas as pd
import pytest

from src.core.indicators.fast_indicators import (
    compute_atr,
    compute_rsi,
    compute_sma,
    engine_name,
)


def test_rsi_wilder_stable_tail():
    """尾部 RSI 應落在 0–100 且與 pandas Wilder 參考在可接受誤差內。"""
    rng = np.random.default_rng(42)
    close = 100 + np.cumsum(rng.normal(0, 1, 200))
    period = 14
    fast = compute_rsi(close, period)
    s = pd.Series(close)
    delta = s.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    ref = (100 - (100 / (1 + rs))).to_numpy()
    tail = 40
    f = fast[-tail:]
    r = ref[-tail:]
    mask = ~(np.isnan(f) | np.isnan(r))
    assert mask.sum() > 20
    assert f[mask].min() >= 0 and f[mask].max() <= 100
    np.testing.assert_allclose(f[mask], r[mask], rtol=0.08, atol=3.0)


def test_sma_tail():
    close = np.arange(1.0, 61.0)
    sma = compute_sma(close, 5)
    assert abs(sma[-1] - close[-5:].mean()) < 1e-9


def test_atr_positive():
    n = 80
    close = np.linspace(100, 110, n)
    high = close + 1
    low = close - 1
    atr = compute_atr(high, low, close, 14)
    assert np.nanmax(atr) > 0


def test_engine_name():
    assert engine_name() in ("numba", "numpy")


def test_indicator_cache_roundtrip():
    from src.core.indicator_cache import cached_rsi

    arr = cached_rsi("__nonexistent_code__", period=14)
    assert arr.size == 0 or np.all(np.isnan(arr))
