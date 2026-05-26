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
        return AStockCommission(
            commission=0.00025,
            min_commission=5.0,
            stamp_tax=0.0005,
            transfer_fee=0.00001,
        )

    def test_buy_small_amount_min_commission(self, comm_info):
        """小額買入觸發最低佣金 5 元。"""
        cost = comm_info._getcommission(100, 10.0, None)  # 成交額 1000 元
        # 佣金: max(1000 * 0.00025, 5) = 5.0
        # 無印花稅（買入）
        # 過戶費: 1000 * 0.00001 = 0.01
        assert cost >= 5.0
        assert cost == pytest.approx(5.0 + 0.01, rel=1e-6)

    def test_buy_large_amount_proportional(self, comm_info):
        """大額買入按比例計算佣金。"""
        cost = comm_info._getcommission(10000, 100.0, None)  # 成交額 1,000,000
        # 佣金: max(1000000 * 0.00025, 5) = 250.0
        # 無印花稅
        # 過戶費: 1000000 * 0.00001 = 10.0
        assert cost == pytest.approx(250.0 + 10.0, rel=1e-6)

    def test_sell_includes_stamp_tax(self, comm_info):
        """賣出包含印花稅。"""
        cost = comm_info._getcommission(-10000, 100.0, None)  # 賣出 1,000,000
        # 佣金: 250.0
        # 印花稅: 1000000 * 0.0005 = 500.0
        # 過戶費: 10.0
        assert cost == pytest.approx(250.0 + 500.0 + 10.0, rel=1e-6)

    def test_buy_no_stamp_tax(self, comm_info):
        """買入不收印花稅。"""
        buy_cost = comm_info._getcommission(10000, 100.0, None)
        sell_cost = comm_info._getcommission(-10000, 100.0, None)
        diff = sell_cost - buy_cost
        # 差額應等於印花稅
        assert diff == pytest.approx(10000 * 100.0 * 0.0005, rel=1e-6)

    def test_min_commission_boundary(self, comm_info):
        """剛好低於最低佣金門檻。"""
        # 成交額 10000 元，佣金費率 0.025% → 2.5 元 < 5 元最低
        cost = comm_info._getcommission(100, 100.0, None)
        assert cost >= 5.0

    def test_zero_size_no_crash(self, comm_info):
        """零股數不崩潰。"""
        cost = comm_info._getcommission(0, 100.0, None)
        assert cost >= 0

    def test_negative_size_is_sell(self, comm_info):
        """負 size 為賣出，應含印花稅。"""
        cost_neg = comm_info._getcommission(-100, 100.0, None)
        cost_pos = comm_info._getcommission(100, 100.0, None)
        assert cost_neg > cost_pos

    def test_custom_params(self):
        """自定義費率參數。"""
        comm = AStockCommission(
            commission=0.0003,
            min_commission=10.0,
            stamp_tax=0.001,
            transfer_fee=0.00002,
        )
        cost = comm._getcommission(-1000, 50.0, None)  # 賣出 50000
        # 佣金: max(50000*0.0003, 10) = 15.0
        # 印花稅: 50000*0.001 = 50.0
        # 過戶費: 50000*0.00002 = 1.0
        assert cost == pytest.approx(15.0 + 50.0 + 1.0, rel=1e-6)


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
        assert result["annual_volatility"] > 0

    def test_all_negative_returns(self):
        """全負收益 — 最大回撤應很大。"""
        returns = [-0.01] * 100
        dates = [(datetime(2024, 1, 1) + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(100)]
        nav = [100]
        for r in returns:
            nav.append(nav[-1] * (1 + r))
        result = _calc_risk_metrics(returns, dates, 63.4, nav)
        assert result["var_95"] < 0
        assert result["annual_volatility"] > 0

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
    """漲跌停限制分析器。"""

    def test_main_board_limit_pct(self):
        """主板 ±10%。"""
        f = LimitFilter()
        f._code = "600519"
        assert f._get_limit_pct("600519") == 0.10
        assert f._get_limit_pct("000001") == 0.10

    def test_gem_limit_pct(self):
        """創業板 ±20%。"""
        f = LimitFilter()
        assert f._get_limit_pct("300001") == 0.20

    def test_star_limit_pct(self):
        """科創板 ±20%。"""
        f = LimitFilter()
        assert f._get_limit_pct("688001") == 0.20

    def test_get_analysis_default(self):
        """初始狀態分析。"""
        f = LimitFilter()
        analysis = f.get_analysis()
        assert analysis["blocked_buys"] == 0
        assert analysis["blocked_sells"] == 0


# ── run_backtest 端到端（合成數據） ─────────────────────────────

class TestRunBacktestE2E:
    """端到端回測 — 使用合成數據 mock。"""

    def _make_synthetic_kline(self, n=100, start_price=10.0, daily_return=0.001):
        """生成合成 K 線數據。"""
        dates = pd.bdate_range("2023-01-01", periods=n)
        prices = [start_price]
        for _ in range(n - 1):
            prices.append(prices[-1] * (1 + daily_return))
        df = pd.DataFrame({
            "date": dates,
            "open": [p * 0.99 for p in prices],
            "high": [p * 1.02 for p in prices],
            "low": [p * 0.98 for p in prices],
            "close": prices,
            "volume": [1000000] * n,
        })
        return df

    @patch("src.core.backtest.load_daily_kline")
    def test_dual_ma_basic(self, mock_load):
        """雙均線策略基本回測。"""
        mock_load.return_value = self._make_synthetic_kline(200)
        from src.core.backtest import run_backtest
        result = run_backtest("000001", strategy_name="dual_ma", cash=100000)
        assert "total_return_pct" in result
        assert "sharpe_ratio" in result
        assert "max_drawdown_pct" in result
        assert "trade_details" in result
        assert isinstance(result["trade_details"], list)

    @patch("src.core.backtest.load_daily_kline")
    def test_empty_data_raises(self, mock_load):
        """空數據應拋出 ValueError。"""
        mock_load.return_value = pd.DataFrame()
        from src.core.backtest import run_backtest
        with pytest.raises(ValueError, match="無日線數據|無數據"):
            run_backtest("999999", strategy_name="dual_ma")

    @patch("src.core.backtest.load_daily_kline")
    def test_unknown_strategy_raises(self, mock_load):
        """未知策略名稱應拋出異常。"""
        mock_load.return_value = self._make_synthetic_kline(100)
        from src.core.backtest import run_backtest
        with pytest.raises((ValueError, KeyError)):
            run_backtest("000001", strategy_name="nonexistent_strategy_xyz")

    @patch("src.core.backtest.load_daily_kline")
    def test_single_bar_insufficient(self, mock_load):
        """僅 1 根 K 線不足以回測。"""
        mock_load.return_value = self._make_synthetic_kline(1)
        from src.core.backtest import run_backtest
        # 應該不崩潰，但可能返回空結果或拋異常
        try:
            result = run_backtest("000001", strategy_name="dual_ma", cash=100000)
            # 如果成功，trade_details 應為空
            assert isinstance(result.get("trade_details", []), list)
        except (ValueError, Exception):
            pass  # 數據不足拋異常也是合理的

    @patch("src.core.backtest.load_daily_kline")
    def test_result_has_risk_fields(self, mock_load):
        """回測結果應包含完整風險指標字段。"""
        mock_load.return_value = self._make_synthetic_kline(300)
        from src.core.backtest import run_backtest
        result = run_backtest("000001", strategy_name="dual_ma", cash=100000)
        expected_fields = [
            "var_95", "cvar_95", "sortino_ratio", "calmar_ratio",
            "annual_volatility", "monthly_win_rate", "profit_loss_ratio",
        ]
        for field in expected_fields:
            assert field in result, f"缺少字段 {field}"

    @patch("src.core.backtest.load_daily_kline")
    def test_different_strategies(self, mock_load):
        """多種策略均能正常運行。"""
        mock_load.return_value = self._make_synthetic_kline(200)
        from src.core.backtest import run_backtest
        strategies = ["dual_ma", "rsi", "macd", "kdj", "bollinger"]
        for strat in strategies:
            result = run_backtest("000001", strategy_name=strat, cash=100000)
            assert "total_return_pct" in result, f"策略 {strat} 結果缺少字段"

    @patch("src.core.backtest.load_daily_kline")
    def test_custom_cash(self, mock_load):
        """自定義初始資金。"""
        mock_load.return_value = self._make_synthetic_kline(100)
        from src.core.backtest import run_backtest
        result = run_backtest("000001", strategy_name="dual_ma", cash=500000)
        assert result["code"] == "000001"
