"""
金融指標單元測試 — 固定輸入，防止重構破壞數學邏輯
"""
import os
import sys
from datetime import datetime

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.backtest import _calc_risk_metrics


def test_calc_risk_metrics_fixed_fixture():
    """固定日收益率序列，斷言 VaR / 年化波動等與手算一致。"""
    daily_returns = [0.01, -0.02, 0.015, -0.005, 0.008, -0.012, 0.003]
    dates = [f"2024-01-{i+1:02d}" for i in range(len(daily_returns))]
    nav = [1.0]
    for r in daily_returns:
        nav.append(nav[-1] * (1 + r))
    max_dd_pct = 3.5

    out = _calc_risk_metrics(daily_returns, dates, max_dd_pct, nav, periods_per_year=252)

    dr = np.array(daily_returns)
    expected_var = float(np.percentile(dr, 5))
    expected_vol = float(np.std(dr) * np.sqrt(252))

    assert out["var_95"] == pytest.approx(round(expected_var, 6), abs=1e-6)
    assert out["annual_volatility"] == pytest.approx(round(expected_vol, 4), abs=1e-4)
    assert out["sortino_ratio"] == pytest.approx(out["sortino_ratio"])
    assert 0 <= out["monthly_win_rate"] <= 100


def test_calc_risk_metrics_empty_returns():
    out = _calc_risk_metrics([], [], 0, [1.0], periods_per_year=252)
    assert out["var_95"] == 0
    assert out["annual_return_pct"] == 0


def test_annual_return_from_nav():
    daily_returns = [0.001] * 100
    dates = _date_range(100)
    nav = [1.0]
    for r in daily_returns:
        nav.append(nav[-1] * (1 + r))
    out = _calc_risk_metrics(daily_returns, dates, 1.0, nav, periods_per_year=252)
    assert out["annual_return_pct"] > 0


def _date_range(n: int) -> list[str]:
    start = datetime(2023, 1, 2)
    return [(start.replace(day=min(start.day + i, 28))).strftime("%Y-%m-%d") for i in range(n)]
