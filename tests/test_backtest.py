"""
回測引擎測試 — 使用合成數據測試雙均線策略
無需外部服務，純本地運行
"""
import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock


def _generate_synthetic_kline(
    code: str = "TEST001",
    days: int = 300,
    start_price: float = 100.0,
    trend: str = "up",
) -> pd.DataFrame:
    """
    生成合成 K 線數據用於測試。
    支持 up / down / sideways 三種趨勢。
    """
    np.random.seed(42)
    dates = pd.date_range(end=datetime.now(), periods=days, freq="B")  # 工作日

    if trend == "up":
        # 緩慢上漲趨勢
        drift = 0.0005
    elif trend == "down":
        drift = -0.0003
    else:
        drift = 0.0

    prices = [start_price]
    for _ in range(days - 1):
        change = drift + np.random.normal(0, 0.015)
        prices.append(prices[-1] * (1 + change))

    records = []
    for i, (dt, close) in enumerate(zip(dates, prices)):
        noise = np.random.uniform(-0.01, 0.01)
        open_p = close * (1 + noise)
        high = max(open_p, close) * (1 + abs(np.random.normal(0, 0.005)))
        low = min(open_p, close) * (1 - abs(np.random.normal(0, 0.005)))
        volume = int(np.random.uniform(500000, 2000000))
        records.append({
            "code": code,
            "date": dt.strftime("%Y-%m-%d"),
            "open": round(open_p, 2),
            "high": round(high, 2),
            "low": round(low, 2),
            "close": round(close, 2),
            "volume": volume,
            "amount": round(volume * close, 2),
            "turnover": round(np.random.uniform(0.5, 5.0), 2),
        })

    return pd.DataFrame(records)


class TestSyntheticData:
    """合成數據生成測試"""

    def test_generate_up_trend(self):
        """測試上漲趨勢數據生成"""
        df = _generate_synthetic_kline(trend="up", days=100)
        assert len(df) == 100
        assert df["close"].iloc[-1] > df["close"].iloc[0] * 0.8  # 大體向上

    def test_generate_down_trend(self):
        """測試下跌趨勢數據生成"""
        df = _generate_synthetic_kline(trend="down", days=100)
        assert len(df) == 100

    def test_data_columns(self):
        """測試數據列完整性"""
        df = _generate_synthetic_kline()
        required_cols = {"code", "date", "open", "high", "low", "close", "volume"}
        assert required_cols.issubset(set(df.columns))

    def test_price_positive(self):
        """測試所有價格為正"""
        df = _generate_synthetic_kline()
        assert (df["open"] > 0).all()
        assert (df["high"] > 0).all()
        assert (df["low"] > 0).all()
        assert (df["close"] > 0).all()

    def test_high_low_consistency(self):
        """測試高價 >= 低價"""
        df = _generate_synthetic_kline()
        assert (df["high"] >= df["low"]).all()


class TestDualMAStrategy:
    """雙均線策略測試"""

    def test_backtest_runs(self):
        """測試回測能正常運行"""
        from src.core.backtest import DualMAStrategy, STRATEGIES
        import backtrader as bt

        # 生成合成數據
        df = _generate_synthetic_kline(days=200, trend="up")
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date")
        df = df[["open", "high", "low", "close", "volume"]]
        df.columns = ["Open", "High", "Low", "Close", "Volume"]

        cerebro = bt.Cerebro()
        cerebro.addstrategy(DualMAStrategy, fast=5, slow=20)
        data = bt.feeds.PandasData(dataname=df)
        cerebro.adddata(data)
        cerebro.broker.setcash(100000)
        cerebro.broker.setcommission(commission=0.001)

        cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe", riskfreerate=0.03)
        cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
        cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")

        results = cerebro.run()
        strat = results[0]

        # 驗證分析器正常工作
        sharpe = strat.analyzers.sharpe.get_analysis()
        drawdown = strat.analyzers.drawdown.get_analysis()
        trades = strat.analyzers.trades.get_analysis()

        assert "sharperatio" in sharpe or sharpe.get("sharperatio") is not None
        assert "max" in drawdown
        assert "total" in trades

    def test_strategy_registered(self):
        """測試策略已註冊"""
        from src.core.backtest import STRATEGIES

        assert "dual_ma" in STRATEGIES
        assert "macd" in STRATEGIES
        assert "bollinger" in STRATEGIES
        assert "kdj" in STRATEGIES
        assert "rsi" in STRATEGIES
        assert "grid" in STRATEGIES
        assert "turtle" in STRATEGIES
        assert "dual_thrust" in STRATEGIES

    def test_backtest_with_mock_data(self):
        """使用 mock 測試完整回測流程"""
        from src.core.backtest import run_backtest

        # Mock 本地優先 K 線入口，避免單元測試觸發外部數據源。
        # 需同時 patch local_kline（源）和 kline_timeframe（from-import 引用）。
        synthetic_df = _generate_synthetic_kline(code="TEST001", days=250, trend="up")

        with patch("src.core.local_kline.ensure_daily_kline", return_value=(synthetic_df, "mock")), \
             patch("src.core.kline_timeframe.ensure_daily_kline", return_value=(synthetic_df, "mock")):
            result = run_backtest("TEST001", strategy_name="dual_ma", cash=100000)

        assert "total_return_pct" in result
        assert "sharpe_ratio" in result
        assert "max_drawdown_pct" in result
        assert "nav" in result
        assert "dates" in result
        assert len(result["nav"]) > 0
        assert result["initial_cash"] == 100000


class TestBacktestRiskMetrics:
    """風險指標測試"""

    def test_risk_metrics_calculation(self):
        """測試風險指標計算"""
        from src.core.backtest import _calc_risk_metrics

        # 模擬日收益率
        np.random.seed(42)
        daily_returns = list(np.random.normal(0.0005, 0.015, 252))
        dates = [datetime(2024, 1, 1) + timedelta(days=i) for i in range(252)]
        nav = [1.0]
        for r in daily_returns:
            nav.append(nav[-1] * (1 + r))
        max_dd = 10.0

        metrics = _calc_risk_metrics(daily_returns, dates, max_dd, nav)

        assert "var_95" in metrics
        assert "cvar_95" in metrics
        assert "sortino_ratio" in metrics
        assert "calmar_ratio" in metrics
        assert "annual_volatility" in metrics
        assert "annual_return_pct" in metrics
        assert metrics["annual_volatility"] > 0


class TestEquityCurveAnalysis:
    """權益曲線分析測試"""

    def test_analyze_equity_curve(self):
        """測試權益曲線分析"""
        from src.core.backtest import analyze_equity_curve

        nav = [1.0, 1.05, 1.03, 1.08, 1.02, 1.10, 1.12]
        dates = [datetime(2024, 1, 1) + timedelta(days=i * 30) for i in range(7)]
        daily_returns = [0, 0.05, -0.019, 0.048, -0.056, 0.078, 0.018]

        result = analyze_equity_curve(nav, dates, daily_returns)

        assert "underwater_periods" in result
        assert "recovery_periods" in result
        assert "max_underwater_days" in result

    def test_empty_nav(self):
        """測試空淨值序列"""
        from src.core.backtest import analyze_equity_curve

        result = analyze_equity_curve([], [], [])
        assert result["max_underwater_days"] == 0
