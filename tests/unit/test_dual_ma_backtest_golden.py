"""
雙均線 Backtrader 回測 Golden（P2）— 固定 seed 合成 K 線，鎖定指標回歸。

與 tests/test_strategies.py 使用相同合成邏輯（np.random.seed(42)）。
"""

from __future__ import annotations

import os
import sys

import backtrader as bt
import numpy as np
import pandas as pd
import pytest

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
os.environ.setdefault("SQ_DB_PATH", "/tmp/test_stock.db")
os.environ.setdefault("SQ_REDIS_ENABLED", "false")
os.environ.setdefault("SQ_LOG_LEVEL", "WARNING")

from src.core.backtest import DualMAStrategy

GOLDEN_N_DAYS = 300
GOLDEN_PARAMS = {"fast": 5, "slow": 20}


def _generate_synthetic_data(
    n_days: int = GOLDEN_N_DAYS,
    start_price: float = 100.0,
    volatility: float = 0.02,
) -> pd.DataFrame:
    np.random.seed(42)
    dates = pd.bdate_range(start="2023-01-01", periods=n_days)
    returns = np.random.normal(0.0003, volatility, n_days)
    prices = start_price * np.cumprod(1 + returns)

    df = pd.DataFrame(
        {
            "Open": prices * (1 + np.random.uniform(-0.005, 0.005, n_days)),
            "High": prices * (1 + np.abs(np.random.normal(0, 0.01, n_days))),
            "Low": prices * (1 - np.abs(np.random.normal(0, 0.01, n_days))),
            "Close": prices,
            "Volume": np.random.randint(100000, 10000000, n_days).astype(float),
        },
        index=dates,
    )
    df["High"] = df[["Open", "Close", "High"]].max(axis=1)
    df["Low"] = df[["Open", "Close", "Low"]].min(axis=1)
    return df


def _run_dual_ma_backtest(data: pd.DataFrame, params: dict) -> dict:
    cerebro = bt.Cerebro()
    cerebro.addstrategy(DualMAStrategy, **params)
    cerebro.adddata(bt.feeds.PandasData(dataname=data))
    cerebro.broker.setcash(100_000)
    cerebro.broker.setcommission(commission=0.001)

    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe", riskfreerate=0.03)
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")

    initial = cerebro.broker.getvalue()
    results = cerebro.run()
    final = cerebro.broker.getvalue()
    strat = results[0]

    sharpe = strat.analyzers.sharpe.get_analysis()
    drawdown = strat.analyzers.drawdown.get_analysis()
    trades = strat.analyzers.trades.get_analysis()

    total_return = (final - initial) / initial * 100
    max_dd = drawdown.get("max", {}).get("drawdown", 0)
    total_trades = trades.get("total", {}).get("total", 0)
    won = trades.get("won", {}).get("total", 0)
    win_rate = (won / total_trades * 100) if total_trades > 0 else 0

    return {
        "total_return_pct": round(total_return, 4),
        "sharpe_ratio": sharpe.get("sharperatio") or 0,
        "max_drawdown_pct": round(max_dd, 4),
        "total_trades": total_trades,
        "win_rate_pct": round(win_rate, 2),
        "final_value": final,
    }


@pytest.fixture(scope="module")
def golden_dual_ma_result() -> dict:
    return _run_dual_ma_backtest(_generate_synthetic_data(), GOLDEN_PARAMS)


def test_dual_ma_backtest_golden_metrics(golden_dual_ma_result: dict) -> None:
    r = golden_dual_ma_result
    assert r["total_return_pct"] == pytest.approx(0.0022, rel=0, abs=1e-4)
    assert r["max_drawdown_pct"] == pytest.approx(0.0236, rel=0, abs=1e-4)
    assert r["total_trades"] == 9
    assert r["win_rate_pct"] == pytest.approx(44.44, rel=0, abs=0.01)
    assert r["final_value"] == pytest.approx(100_002.24488427352, rel=1e-9, abs=1e-6)
    assert r["sharpe_ratio"] == pytest.approx(-226.08697360330072, rel=1e-6, abs=1e-3)


def test_dual_ma_backtest_deterministic_repeat(golden_dual_ma_result: dict) -> None:
    again = _run_dual_ma_backtest(_generate_synthetic_data(), GOLDEN_PARAMS)
    assert again == golden_dual_ma_result
