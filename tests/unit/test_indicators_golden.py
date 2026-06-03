"""
指標 Golden Tests（P2）— 固定輸入序列，鎖定數值回歸。

與 Backtrader 策略解耦，驗證 src.core.indicators.fast_indicators 純函數。
"""
from __future__ import annotations

import numpy as np
import pytest

from src.core.indicators.fast_indicators import compute_rsi, compute_sma

# 固定 40 點線性上行（seed 可重現）
CLOSE_GOLDEN = np.linspace(100.0, 110.0, 40, dtype=np.float64)


def test_sma5_golden_last_value():
    sma = compute_sma(CLOSE_GOLDEN, 5)
    assert sma[-1] == pytest.approx(109.4871794871794, rel=1e-9, abs=1e-9)


def test_sma5_golden_first_valid_index():
    sma = compute_sma(CLOSE_GOLDEN, 5)
    assert sma[4] == pytest.approx(100.51282051282051, rel=1e-9, abs=1e-9)
    assert np.isnan(sma[3])


def test_rsi14_golden_uptrend_near_overbought():
    rsi = compute_rsi(CLOSE_GOLDEN, 14)
    assert rsi[-1] == pytest.approx(100.0, rel=1e-9, abs=1e-9)


def test_dual_ma_golden_cross_detection():
    """雙均線金叉：快線由 ≤ 慢線 變為 > 慢線（與 dual_ma 策略邏輯對齊）。"""
    # 先跌後漲，確保存在至少一次金叉
    close = np.concatenate([
        np.linspace(110.0, 95.0, 25),
        np.linspace(95.0, 120.0, 35),
    ]).astype(np.float64)
    fast = compute_sma(close, 5)
    slow = compute_sma(close, 20)
    crosses = 0
    for i in range(20, len(close)):
        if fast[i - 1] <= slow[i - 1] and fast[i] > slow[i]:
            crosses += 1
    assert crosses >= 1
    assert fast[-1] > slow[-1]


def test_sma_deterministic_across_calls():
    a = compute_sma(CLOSE_GOLDEN, 10)
    b = compute_sma(CLOSE_GOLDEN.copy(), 10)
    np.testing.assert_array_equal(a, b)
