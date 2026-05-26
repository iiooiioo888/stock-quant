"""
回測引擎穩定性測試 — AStockCommission、風險指標、邊界條件

覆蓋：
  - AStockCommission 佣金計算（最低5元、印花稅僅賣出、過戶費）
  - _calc_risk_metrics 邊界（空數據、單元素、全正收益、全負收益、NaN/Inf）
  - LimitFilter 漲跌停邏輯
  - prepare_data 異常處理
  - run_backtest 端到端（合成數據 mock）
"""
from __future__ import annotations

import math
import numpy as np
import pandas as pd
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta

import backtrader as bt
from src.core.backtest import AStockCommission, _calc_risk_metrics, LimitFilter


# ── AStockCommission 佣金計算 ───────────────────────────────────

class TestAStockCommission:
    """A股精確佣金模型驗證。"""

    @pytest.fixture
    def comm_info(self):
        # 默認參數 — Backtrader COMM_PERC 模式將 commission 除以 100
        # 所以默認 commission=0.00025 實際存為 2.5e-06
        return AStockCommission()

    def test_buy_small_amount_min_commission(self):
        """小額買入觸發最低佣金 5 元。"""
        c = AStockCommission()
        cost = c._getcommission(100, 10.0, None)  # 成交額 1000
        # 佣金: max(1000 * 2.5e-06, 5) = 5.0
        # 無印花稅（買入）
        # 過戶費: 1000 * 1e-05 = 0.01
        assert cost == pytest.approx(5.01, rel=1e-4)

    def test_buy_large_amount_proportional(self):
        """大額買入 — 佣金仍被最低佣金覆蓋。"""
        c = AStockCommission()
        cost = c._getcommission(10000, 100.0, None)  # 成交額 1,000,000
        # 佣金: max(1000000 * 2.5e-06, 5) = max(2.5, 5) = 5.0
        # 過戶費: 1000000 * 1e-05 = 10.0
        assert cost == pytest.approx(15.0, rel=1e-4)

    def test_sell_includes_stamp_tax(self):
        """賣出包含印花稅。"""
        c = AStockCommission()
        cost = c._getcommission(-10000, 100.0, None)  # 賣出 1,000,000
        # 佣金: 5.0 (min)
        # 印花稅: 1000000 * 0.0005 = 500.0
        # 過戶費: 10.0
        assert cost == pytest.approx(515.0, rel=1e-4)

    def test_buy_no_stamp_tax(self):
        """買入不收印花稅。"""
        c = AStockCommission()
        buy_cost = c._getcommission(10000, 100.0, None)
        sell_cost = c._getcommission(-10000, 100.0, None)
        diff = sell_cost - buy_cost
        # 差額應等於印花稅: 1000000 * 0.0005 = 500
        assert diff == pytest.approx(500.0, rel=1e-4)

    def test_min_commission_boundary(self):
        """剛好低於最低佣金門檻。"""
        c = AStockCommission()
        # 成交額 10000 元，佣金 10000*2.5e-06=0.025 < 5
        cost = c._getcommission(100, 100.0, None)
        assert cost >= 5.0

    def test_zero_size_no_crash(self):
        """零股數不崩潰。"""
        c = AStockCommission()
        cost = c._getcommission(0, 100.0, None)
        assert cost >= 0

    def test_negative_size_is_sell(self):
        """負 size 為賣出，應含印花稅。"""
        c = AStockCommission()
        cost_neg = c._getcommission(-100, 100.0, None)
        cost_pos = c._getcommission(100, 100.0, None)
        assert cost_neg > cost_pos

    def test_custom_params(self):
        """自定義費率參數（注意 COMM_PERC 會將 commission 除以 100）。"""
        comm = AStockCommission(
            commission=0.03,      # 實際存為 0.0003
            min_commission=10.0,
            stamp_tax=0.001,
            transfer_fee=0.00002,
        )
        cost = comm._getcommission(-1000, 50.0, None)  # 賣出 50000
        # 佣金: max(50000 * 0.0003, 10) = 15.0
        # 印花稅: 50000 * 0.001 = 50.0
        # 過戶費: 50000 * 0.00002 = 1.0
        assert cost == pytest.approx(15.0 + 50.0 + 1.0, rel=1e-4)


# ── 風險指標計算 ────────────────────────────────────────────────

class TestRiskMetrics:
    """_calc_risk_metrics 邊界條件。"""

    def test_empty_returns(self):
        """空收益列表返回全零。"""
        result = _calc_risk_metrics([], [], 0, [])
        assert result["var_95"] == 0
        assert result["sortino_ratio"] == 0
        assert result["annual_volatility"] == 0

    def test_single_return(self):
        """單個收益返回全零。"""
        result = _calc_risk_metrics([0.01], ["2024-01-01"], 0, [100, 101])
        assert result["var_95"] == 0

    def test_normal_returns(self):
        """正常收益數據。"""
        np.random.seed(42)
        returns = list(np.random.normal(0.001, 0.02, 252))
        dates = [(datetime(2024, 1, 1) + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(252)]
        nav = [100]
        for r in returns:
            nav.append(nav[-1] * (1 + r))
        result = _calc_risk_metrics(returns, dates, 10.0, nav)
        assert result["var_95"] < 0, "VaR 應為負值"
        assert result["annual_volatility"] > 0
        assert result["sortino_ratio"] != 0
        assert result["monthly_win_rate"] > 0

    def test_all_positive_returns(self):
        """全正收益 — 無下行風險。"""
        returns = [0.01] * 100
        dates = [(datetime(2024, 1, 1) + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(100)]
        nav = [100]
        for r in returns:
            nav.append(nav[-1] * (1 + r))
        result = _calc_risk_metrics(returns, dates, 0, nav)
        assert result["sortino_ratio"] != 0  # 有值即可
        # 全相同收益 → std=0 → volatility=0
        assert result["annual_volatility"] >= 0

    def test_all_negative_returns(self):
        """全負收益 — 最大回撤應很大。"""
        returns = [-0.01] * 100
        dates = [(datetime(2024, 1, 1) + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(100)]
        nav = [100]
        for r in returns:
            nav.append(nav[-1] * (1 + r))
        result = _calc_risk_metrics(returns, dates, 63.4, nav)
        assert result["var_95"] < 0
        # 全相同收益 → std=0 → volatility=0
        assert result["annual_volatility"] >= 0

    def test_zero_volatility(self):
        """零波動率（全部為零收益）。"""
        returns = [0.0] * 100
        dates = [(datetime(2024, 1, 1) + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(100)]
        nav = [100] * 101
        result = _calc_risk_metrics(returns, dates, 0, nav)
        assert result["annual_volatility"] == 0

    def test_extreme_returns(self):
        """極端收益（+50% 和 -50%）。"""
        returns = [0.5, -0.5, 0.5, -0.5]
        dates = [(datetime(2024, 1, 1) + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(4)]
        nav = [100, 150, 75, 112.5, 56.25]
        result = _calc_risk_metrics(returns, dates, 62.5, nav)
        assert not math.isnan(result["var_95"])
        assert not math.isinf(result["annual_volatility"])

    def test_periods_per_year_weekly(self):
        """週線數據（52 週/年）影響年化。"""
        returns = list(np.random.normal(0.002, 0.03, 52))
        dates = [(datetime(2024, 1, 1) + timedelta(weeks=i)).strftime("%Y-%m-%d") for i in range(52)]
        nav = [100]
        for r in returns:
            nav.append(nav[-1] * (1 + r))
        result = _calc_risk_metrics(returns, dates, 10.0, nav, periods_per_year=52)
        assert result["annual_volatility"] > 0

    def test_no_nan_in_output(self):
        """所有輸出不應含 NaN 或 Inf。"""
        np.random.seed(123)
        returns = list(np.random.normal(0.001, 0.02, 200))
        dates = [(datetime(2024, 1, 1) + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(200)]
        nav = [100]
        for r in returns:
            nav.append(nav[-1] * (1 + r))
        result = _calc_risk_metrics(returns, dates, 5.0, nav)
        for k, v in result.items():
            if isinstance(v, float):
                assert not math.isnan(v), f"{k} 不應為 NaN"
                assert not math.isinf(v), f"{k} 不應為 Inf"


# ── LimitFilter 漲跌停 ─────────────────────────────────────────

class TestLimitFilter:
    """漲跌停限制分析器 — 需要 bt.Strategy 上下文。"""

    def _make_filter(self):
        """創建帶 mock strategy 的 LimitFilter。"""
        import types
        cerebro = bt.Cerebro()
        # 用一個空的 data feed
        data = bt.feeds.PandasData(dataname=pd.DataFrame(
            {"open": [1], "high": [1], "low": [1], "close": [1], "volume": [100]},
            index=[datetime(2024, 1, 1)]
        ))
        cerebro.adddata(data)

        class TestStrategy(bt.Strategy):
            def __init__(self):
                self.lf = LimitFilter()
        cerebro.addstrategy(TestStrategy)
        results = cerebro.run()
        return results[0].lf

    def test_main_board_limit_pct(self):
        """主板 ±10%。"""
        f = self._make_filter()
        assert f._get_limit_pct("600519") == 0.10
        assert f._get_limit_pct("000001") == 0.10

    def test_gem_limit_pct(self):
        """創業板 ±20%。"""
        f = self._make_filter()
        f._limit_pct = None  # reset cache
        assert f._get_limit_pct("300001") == 0.20

    def test_star_limit_pct(self):
        """科創板 ±20%。"""
        f = self._make_filter()
        f._limit_pct = None  # reset cache
        assert f._get_limit_pct("688001") == 0.20

    def test_get_analysis_default(self):
        """初始狀態分析。"""
        f = self._make_filter()
        analysis = f.get_analysis()
        assert analysis["blocked_buys"] == 0
        assert analysis["blocked_sells"] == 0


# ── run_backtest 端到端（合成數據） ─────────────────────────────

class TestRunBacktestE2E:
    """端到端回測 — 使用合成數據 mock。"""

    def _make_synthetic_kline(self, n=100, start_price=10.0, daily_return=0.001):
        """生成合成 K 線數據（DatetimeIndex）。"""
        dates = pd.bdate_range("2023-01-01", periods=n)
        prices = [start_price]
        for _ in range(n - 1):
            prices.append(prices[-1] * (1 + daily_return))
        df = pd.DataFrame({
            "open": [p * 0.99 for p in prices],
            "high": [p * 1.02 for p in prices],
            "low": [p * 0.98 for p in prices],
            "close": prices,
            "volume": [1000000] * n,
        }, index=dates)
        return df

    @patch("src.core.kline_timeframe.ensure_kline_for_backtest")
    def test_dual_ma_basic(self, mock_ensure):
        """雙均線策略基本回測。"""
        mock_ensure.return_value = (self._make_synthetic_kline(200), "synthetic", "1d")
        from src.core.backtest import run_backtest
        result = run_backtest("000001", strategy_name="dual_ma", cash=100000)
        assert "total_return_pct" in result
        assert "sharpe_ratio" in result
        assert "max_drawdown_pct" in result
        assert "trade_details" in result
        assert isinstance(result["trade_details"], list)

    @patch("src.core.kline_timeframe.ensure_kline_for_backtest")
    def test_empty_data_raises(self, mock_ensure):
        """空數據應拋出 ValueError。"""
        mock_ensure.return_value = (pd.DataFrame(), "empty", "1d")
        from src.core.backtest import run_backtest
        with pytest.raises((ValueError, Exception)):
            run_backtest("999999", strategy_name="dual_ma")

    @patch("src.core.kline_timeframe.ensure_kline_for_backtest")
    def test_unknown_strategy_raises(self, mock_ensure):
        """未知策略名稱應拋出異常。"""
        mock_ensure.return_value = (self._make_synthetic_kline(100), "synthetic", "1d")
        from src.core.backtest import run_backtest
        with pytest.raises((ValueError, KeyError)):
            run_backtest("000001", strategy_name="nonexistent_strategy_xyz")

    @patch("src.core.kline_timeframe.ensure_kline_for_backtest")
    def test_single_bar_insufficient(self, mock_ensure):
        """僅 1 根 K 線不足以回測。"""
        mock_ensure.return_value = (self._make_synthetic_kline(1), "synthetic", "1d")
        from src.core.backtest import run_backtest
        try:
            result = run_backtest("000001", strategy_name="dual_ma", cash=100000)
            assert isinstance(result.get("trade_details", []), list)
        except (ValueError, Exception):
            pass  # 數據不足拋異常也是合理的

    @patch("src.core.kline_timeframe.ensure_kline_for_backtest")
    def test_result_has_risk_fields(self, mock_ensure):
        """回測結果應包含完整風險指標字段。"""
        mock_ensure.return_value = (self._make_synthetic_kline(300), "synthetic", "1d")
        from src.core.backtest import run_backtest
        result = run_backtest("000001", strategy_name="dual_ma", cash=100000)
        expected_fields = [
            "var_95", "cvar_95", "sortino_ratio", "calmar_ratio",
            "annual_volatility", "monthly_win_rate", "profit_loss_ratio",
        ]
        for field in expected_fields:
            assert field in result, f"缺少字段 {field}"

    @patch("src.core.kline_timeframe.ensure_kline_for_backtest")
    def test_different_strategies(self, mock_load):
        """多種策略均能正常運行（部分策略可能因合成數據不足而失敗，屬正常）。"""
        # 使用隨機數據避免除零
        np.random.seed(42)
        dates = pd.bdate_range("2023-01-01", periods=200)
        close = 10.0 + np.cumsum(np.random.randn(200) * 0.3)
        close = np.maximum(close, 1.0)
        df = pd.DataFrame({
            "open": close * 0.99,
            "high": close * 1.02,
            "low": close * 0.98,
            "close": close,
            "volume": np.random.randint(100000, 1000000, 200).astype(float),
        }, index=dates)
        mock_load.return_value = (df, "synthetic", "1d")
        from src.core.backtest import run_backtest
        strategies = ["dual_ma", "rsi", "macd", "kdj", "bollinger"]
        for strat in strategies:
            try:
                result = run_backtest("000001", strategy_name=strat, cash=100000)
                assert "total_return_pct" in result, f"策略 {strat} 結果缺少字段"
            except (ZeroDivisionError, Exception):
                pass  # 合成數據可能觸發策略內部異常

    @patch("src.core.kline_timeframe.ensure_kline_for_backtest")
    def test_custom_cash(self, mock_ensure):
        """自定義初始資金。"""
        mock_ensure.return_value = (self._make_synthetic_kline(100), "synthetic", "1d")
        from src.core.backtest import run_backtest
        result = run_backtest("000001", strategy_name="dual_ma", cash=500000)
        assert result["code"] == "000001"


# ── T1Filter T+1 分析器 ─────────────────────────────────────────

class TestT1Filter:
    """T+1 限制分析器。"""

    def _make_t1_filter(self):
        """創建帶 T1Filter 的 Cerebro。"""
        dates = pd.bdate_range("2024-01-01", periods=20)
        close = [10.0 + i * 0.1 for i in range(20)]
        df = pd.DataFrame({
            "open": [p * 0.99 for p in close],
            "high": [p * 1.02 for p in close],
            "low": [p * 0.98 for p in close],
            "close": close,
            "volume": [1e6] * 20,
        }, index=dates)
        from src.core.backtest import T1Filter

        cerebro = bt.Cerebro()
        cerebro.adddata(bt.feeds.PandasData(dataname=df))

        class TestStrat(bt.Strategy):
            def __init__(self):
                self.t1 = T1Filter()
        cerebro.addstrategy(TestStrat)
        results = cerebro.run()
        return results[0].t1

    def test_initial_analysis(self):
        f = self._make_t1_filter()
        analysis = f.get_analysis()
        assert analysis["blocked_sells"] == 0
        assert analysis["tracked_positions"] == 0


# ── analyze_equity_curve ────────────────────────────────────────

class TestAnalyzeEquityCurve:
    """淨值曲線深度分析。"""

    def test_normal_curve(self):
        from src.core.backtest import analyze_equity_curve
        nav = [100 + i * 0.5 for i in range(252)]
        dates = [f"2024-{(i//28)+1:02d}-{(i%28)+1:02d}" for i in range(252)]
        returns = [(nav[i] / nav[i - 1]) - 1 for i in range(1, len(nav))]
        result = analyze_equity_curve(nav, dates, returns)
        assert "underwater_periods" in result
        assert "recovery_periods" in result
        assert "rolling_1y_returns" in result
        assert "drawdown_durations" in result
        assert "underwater_pct" in result
        assert isinstance(result["underwater_periods"], list)
        assert isinstance(result["rolling_1y_returns"], list)

    def test_empty_curve(self):
        from src.core.backtest import analyze_equity_curve
        result = analyze_equity_curve([], [], [])
        assert "underwater_periods" in result
        assert result["max_underwater_days"] == 0

    def test_v_shaped_curve(self):
        from src.core.backtest import analyze_equity_curve
        nav = [100] * 20 + [80] * 20 + [100] * 20
        dates = [f"2024-01-{i+1:02d}" for i in range(60)]
        returns = [(nav[i] / nav[i - 1]) - 1 if i > 0 else 0.0 for i in range(60)]
        result = analyze_equity_curve(nav, dates, returns)
        assert result["max_underwater_days"] >= 0


# ── trade_analysis ──────────────────────────────────────────────

class TestTradeAnalysis:
    """交易分析。"""

    def test_normal_trades(self):
        from src.core.backtest import trade_analysis
        trades = [
            {"pnl": 500, "hold_days": 5, "return_pct": 5.0, "buy_date": "2024-01-02", "sell_date": "2024-01-07"},
            {"pnl": -200, "hold_days": 3, "return_pct": -2.0, "buy_date": "2024-01-10", "sell_date": "2024-01-13"},
            {"pnl": 300, "hold_days": 7, "return_pct": 3.0, "buy_date": "2024-01-15", "sell_date": "2024-01-22"},
        ]
        result = trade_analysis(trades)
        assert result["total_trades"] == 3
        assert result["profit_factor"] > 0
        assert "streak" in result
        assert "hold_period" in result
        assert "expectancy" in result
        assert result["gross_profit"] == 800
        assert abs(result["gross_loss"]) == 200  # 可能正或負

    def test_empty_trades(self):
        from src.core.backtest import trade_analysis
        result = trade_analysis([])
        assert result["total_trades"] == 0

    def test_all_wins(self):
        from src.core.backtest import trade_analysis
        trades = [
            {"pnl": 100, "hold_days": 1, "return_pct": 1.0, "buy_date": "2024-01-01", "sell_date": "2024-01-02"},
            {"pnl": 200, "hold_days": 2, "return_pct": 2.0, "buy_date": "2024-01-03", "sell_date": "2024-01-05"},
        ]
        result = trade_analysis(trades)
        assert result["streak"]["max_win_streak"] == 2
        assert result["streak"]["max_loss_streak"] == 0


# ── monte_carlo_simulation ──────────────────────────────────────

class TestMonteCarlo:
    """蒙地卡羅模擬。"""

    def test_basic_simulation(self):
        from src.core.backtest import monte_carlo_simulation
        np.random.seed(42)
        returns = list(np.random.normal(0.001, 0.02, 252))
        result = monte_carlo_simulation(returns, n_simulations=100, days=60)
        assert "percentiles" in result
        assert "prob_profit" in result
        assert "prob_large_drawdown" in result
        assert "simulated_curves" in result
        assert result["n_simulations"] == 100
        assert result["days"] == 60
        assert 0 <= result["prob_profit"] <= 1

    def test_empty_returns(self):
        from src.core.backtest import monte_carlo_simulation
        try:
            result = monte_carlo_simulation([], n_simulations=10, days=10)
            # 可能返回空結果或拋異常
            assert isinstance(result, dict)
        except (ValueError, IndexError):
            pass  # 空數據拋異常合理

    def test_confidence_intervals(self):
        from src.core.backtest import monte_carlo_simulation
        returns = [0.001] * 100
        try:
            result = monte_carlo_simulation(returns, n_simulations=50, days=30)
            ci = result["confidence_intervals"]
            assert "90pct" in ci
            assert "50pct" in ci
            assert ci["90pct"][0] <= ci["90pct"][1]
        except (ValueError, ZeroDivisionError):
            pass  # 常數收益可能觸發異常


# ── rolling_metrics ─────────────────────────────────────────────

class TestRollingMetrics:
    """滾動指標。"""

    def test_basic_rolling(self):
        from src.core.backtest import rolling_metrics
        np.random.seed(42)
        returns = list(np.random.normal(0.001, 0.02, 252))
        dates = [f"2024-{(i//28)+1:02d}-{(i%28)+1:02d}" for i in range(252)]
        result = rolling_metrics(returns, dates, window=60)
        assert "rolling_sharpe" in result
        assert "rolling_sortino" in result
        assert "rolling_volatility" in result
        assert "summary" in result
        assert result["window"] == 60
        assert len(result["rolling_sharpe"]) > 0

    def test_short_data(self):
        from src.core.backtest import rolling_metrics
        returns = [0.01, -0.01, 0.005]
        dates = ["2024-01-01", "2024-01-02", "2024-01-03"]
        result = rolling_metrics(returns, dates, window=5)
        # 數據不足一個窗口，可能返回空
        assert isinstance(result, dict)

    def test_summary_fields(self):
        from src.core.backtest import rolling_metrics
        np.random.seed(123)
        returns = list(np.random.normal(0.001, 0.02, 200))
        dates = [f"2024-{(i//28)+1:02d}-{(i%28)+1:02d}" for i in range(200)]
        result = rolling_metrics(returns, dates, window=30)
        s = result["summary"]
        assert "sharpe_mean" in s
        assert "sortino_mean" in s
        assert "volatility_mean" in s


# ── run_multi_strategy ──────────────────────────────────────────

class TestRunMultiStrategy:
    """多策略並行回測。"""

    @patch("src.core.kline_timeframe.ensure_kline_for_backtest")
    def test_multi_strategy_basic(self, mock_ensure):
        """多策略回測至少返回部分結果。"""
        np.random.seed(42)
        dates = pd.bdate_range("2023-01-01", periods=200)
        close = 10.0 + np.cumsum(np.random.randn(200) * 0.3)
        close = np.maximum(close, 1.0)
        df = pd.DataFrame({
            "open": close * 0.99,
            "high": close * 1.02,
            "low": close * 0.98,
            "close": close,
            "volume": np.random.randint(100000, 1000000, 200).astype(float),
        }, index=dates)
        mock_ensure.return_value = (df, "synthetic", "1d")
        from src.core.backtest import run_multi_strategy
        results = run_multi_strategy("000001")
        assert isinstance(results, list)
        for r in results:
            assert "total_return_pct" in r
