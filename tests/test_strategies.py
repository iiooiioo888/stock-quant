"""
策略測試 — 覆蓋全部 19 個內置策略的基本回測

每個策略至少運行一次回測，驗證:
  - 策略能正常初始化和運行
  - 回測結果結構完整
  - 核心指標在合理範圍內
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SQ_DB_PATH", "/tmp/test_stock.db")
os.environ.setdefault("SQ_REDIS_ENABLED", "false")
os.environ.setdefault("SQ_LOG_LEVEL", "WARNING")

import backtrader as bt
import pandas as pd
import numpy as np


# ============================================================
# Fixtures
# ============================================================

def _generate_synthetic_data(n_days: int = 300, start_price: float = 100.0, volatility: float = 0.02) -> pd.DataFrame:
    """生成合成 K 線數據（無需真實數據庫）"""
    np.random.seed(42)
    dates = pd.bdate_range(start="2023-01-01", periods=n_days)
    returns = np.random.normal(0.0003, volatility, n_days)
    prices = start_price * np.cumprod(1 + returns)

    df = pd.DataFrame({
        "Open": prices * (1 + np.random.uniform(-0.005, 0.005, n_days)),
        "High": prices * (1 + np.abs(np.random.normal(0, 0.01, n_days))),
        "Low": prices * (1 - np.abs(np.random.normal(0, 0.01, n_days))),
        "Close": prices,
        "Volume": np.random.randint(100000, 10000000, n_days).astype(float),
    }, index=dates)

    # 確保 High >= max(Open, Close) 且 Low <= min(Open, Close)
    df["High"] = df[["Open", "Close", "High"]].max(axis=1)
    df["Low"] = df[["Open", "Close", "Low"]].min(axis=1)

    return df


@pytest.fixture
def synthetic_data():
    return _generate_synthetic_data()


def _run_strategy_backtest(strategy_cls, data: pd.DataFrame, params: dict = None) -> dict:
    """用 Backtrader 運行策略回測"""
    cerebro = bt.Cerebro()
    if params:
        cerebro.addstrategy(strategy_cls, **params)
    else:
        cerebro.addstrategy(strategy_cls)

    feed = bt.feeds.PandasData(dataname=data)
    cerebro.adddata(feed)
    cerebro.broker.setcash(100000)
    cerebro.broker.setcommission(commission=0.001)

    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe", riskfreerate=0.03)
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")
    cerebro.addanalyzer(bt.analyzers.Returns, _name="returns")

    initial = cerebro.broker.getvalue()
    results = cerebro.run()
    final = cerebro.broker.getvalue()
    strat = results[0]

    sharpe = strat.analyzers.sharpe.get_analysis()
    drawdown = strat.analyzers.drawdown.get_analysis()
    trades = strat.analyzers.trades.get_analysis()
    returns = strat.analyzers.returns.get_analysis()

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


# ============================================================
# 測試：所有 19 個策略
# ============================================================

# 從 backtest 模塊導入所有策略
from src.core.backtest import (
    DualMAStrategy, MACDStrategy, BollingerStrategy, KDJStrategy,
    RSIStrategy, GridStrategy, TurtleStrategy, DualThrustStrategy,
    MomentumStrategy, MeanReversionStrategy, VolumePriceStrategy,
    BreakoutStrategy, CompositeStrategy, VWAPStrategy, EnvelopeStrategy,
    ParabolicSARStrategy, OBVStrategy, BollingerSqueezeStrategy,
    ADXTrendStrategy, STRATEGIES, STRATEGY_NAMES,
)


class TestAllStrategies:
    """測試所有策略的基本回測"""

    def _test_strategy(self, cls, data, params=None):
        """通用策略測試模板"""
        result = _run_strategy_backtest(cls, data, params)
        # 基本斷言
        assert isinstance(result, dict)
        assert "total_return_pct" in result
        assert "sharpe_ratio" in result
        assert "max_drawdown_pct" in result
        assert "total_trades" in result
        assert "win_rate_pct" in result
        # 指標範圍合理
        assert -100 <= result["total_return_pct"] <= 10000  # 不可能低於 -100%
        assert 0 <= result["max_drawdown_pct"] <= 100
        assert result["total_trades"] >= 0
        assert 0 <= result["win_rate_pct"] <= 100
        return result

    def test_dual_ma(self, synthetic_data):
        r = self._test_strategy(DualMAStrategy, synthetic_data, {"fast": 5, "slow": 20})
        assert r["total_trades"] >= 0

    def test_macd(self, synthetic_data):
        r = self._test_strategy(MACDStrategy, synthetic_data, {"fast": 12, "slow": 26, "signal": 9})

    def test_bollinger(self, synthetic_data):
        r = self._test_strategy(BollingerStrategy, synthetic_data, {"period": 20, "devfactor": 2.0})

    def test_kdj(self, synthetic_data):
        r = self._test_strategy(KDJStrategy, synthetic_data, {
            "period": 9, "period_dfast": 3, "period_dslow": 3,
            "overbought": 80, "oversold": 20,
        })

    def test_rsi(self, synthetic_data):
        r = self._test_strategy(RSIStrategy, synthetic_data, {
            "period": 14, "overbought": 70, "oversold": 30,
        })

    def test_grid(self, synthetic_data):
        r = self._test_strategy(GridStrategy, synthetic_data, {
            "grid_pct": 3.0, "position_pct": 0.1,
        })

    def test_turtle(self, synthetic_data):
        r = self._test_strategy(TurtleStrategy, synthetic_data, {
            "entry_period": 20, "exit_period": 10, "atr_period": 20, "risk_pct": 1.0,
        })

    def test_dual_thrust(self, synthetic_data):
        r = self._test_strategy(DualThrustStrategy, synthetic_data, {
            "period": 4, "k_up": 0.5, "k_down": 0.5,
        })

    def test_momentum(self, synthetic_data):
        r = self._test_strategy(MomentumStrategy, synthetic_data, {
            "lookback": 20, "hold_period": 5,
        })

    def test_mean_reversion(self, synthetic_data):
        r = self._test_strategy(MeanReversionStrategy, synthetic_data, {
            "period": 20, "entry_zscore": -2.0, "exit_zscore": 0.0,
        })

    def test_volume_price(self, synthetic_data):
        r = self._test_strategy(VolumePriceStrategy, synthetic_data, {
            "price_ma": 20, "volume_ma": 20, "volume_ratio": 2.0,
        })

    def test_breakout(self, synthetic_data):
        r = self._test_strategy(BreakoutStrategy, synthetic_data, {
            "period": 60, "atr_period": 20, "atr_multiplier": 2.0,
        })

    def test_composite(self, synthetic_data):
        r = self._test_strategy(CompositeStrategy, synthetic_data, {
            "min_agreement": 3, "ma_fast": 5, "ma_slow": 20,
            "rsi_period": 14, "rsi_overbought": 70, "rsi_oversold": 30,
            "boll_period": 20, "boll_dev": 2.0,
        })

    def test_vwap(self, synthetic_data):
        r = self._test_strategy(VWAPStrategy, synthetic_data, {
            "period": 20, "deviation_pct": 1.0,
        })

    def test_envelope(self, synthetic_data):
        r = self._test_strategy(EnvelopeStrategy, synthetic_data, {
            "period": 20, "deviation_pct": 5,
        })

    def test_parabolic_sar(self, synthetic_data):
        r = self._test_strategy(ParabolicSARStrategy, synthetic_data, {
            "af_start": 0.02, "af_step": 0.02, "af_max": 0.20,
        })

    def test_obv(self, synthetic_data):
        r = self._test_strategy(OBVStrategy, synthetic_data, {
            "obv_ma_period": 20, "price_ma_period": 20,
        })

    def test_bollinger_squeeze(self, synthetic_data):
        r = self._test_strategy(BollingerSqueezeStrategy, synthetic_data, {
            "period": 20, "devfactor": 2.0, "squeeze_threshold": 0.03, "squeeze_lookback": 5,
        })

    def test_adx_trend(self, synthetic_data):
        r = self._test_strategy(ADXTrendStrategy, synthetic_data, {
            "adx_period": 14, "adx_threshold": 25, "di_period": 14,
        })


class TestStrategiesDict:
    """測試 STRATEGIES 字典完整性"""

    def test_all_19_strategies_registered(self):
        assert len(STRATEGIES) == 19

    def test_strategy_names_match(self):
        assert len(STRATEGY_NAMES) == 19
        for name in STRATEGIES:
            assert name in STRATEGY_NAMES, f"{name} 缺少中文名"

    def test_all_strategies_have_params(self):
        """所有策略都有 params 定義"""
        for name, cls in STRATEGIES.items():
            assert hasattr(cls, "params"), f"{name} 缺少 params"

    def test_strategy_classes_are_bt_strategy(self):
        """所有策略都是 bt.Strategy 子類"""
        for name, cls in STRATEGIES.items():
            assert issubclass(cls, bt.Strategy), f"{name} 不是 bt.Strategy 子類"


class TestStrategyWithDefaultParams:
    """測試所有策略用默認參數（不傳 params）也能正常運行"""

    def _test_default_params(self, cls, data):
        result = _run_strategy_backtest(cls, data)  # 不傳 params
        assert isinstance(result, dict)
        assert "total_return_pct" in result

    @pytest.mark.parametrize("strategy_name", list(STRATEGIES.keys()))
    def test_default_params(self, strategy_name, synthetic_data):
        cls = STRATEGIES[strategy_name]
        self._test_default_params(cls, synthetic_data)


class TestRiskPipeline:
    """測試風控管道"""

    def test_pipeline_init(self):
        from src.core.risk_pipeline import RiskPipeline
        pipeline = RiskPipeline(total_capital=100000)
        assert pipeline.total_capital == 100000
        assert pipeline.portfolio.cash == 100000

    def test_pipeline_process_buy_signal(self):
        from src.core.risk_pipeline import RiskPipeline, TradeSignal, SignalType
        pipeline = RiskPipeline(total_capital=100000, sizing_method="fixed", fixed_fraction=0.1)
        signals = [TradeSignal(code="000001", strategy="dual_ma", signal=SignalType.BUY, price=10.0, strength=50.0)]
        orders = pipeline.process_signals(signals, {"000001": 10.0}, {"000001": 0.25})
        assert len(orders) >= 1
        buy_orders = [o for o in orders if o.side.value == "buy"]
        if buy_orders:
            assert buy_orders[0].shares >= 100
            assert buy_orders[0].shares % 100 == 0  # A 股最小單位

    def test_pipeline_rejects_weak_signal(self):
        from src.core.risk_pipeline import RiskPipeline, TradeSignal, SignalType, RiskRejectionReason
        pipeline = RiskPipeline(total_capital=100000, min_signal_strength=20.0)
        signals = [TradeSignal(code="000001", strategy="dual_ma", signal=SignalType.BUY, price=10.0, strength=5.0)]
        orders = pipeline.process_signals(signals, {"000001": 10.0})
        rejected = [o for o in orders if o.risk_status == "rejected"]
        assert any(o.rejection_reason == RiskRejectionReason.SIGNAL_TOO_WEAK for o in rejected)

    def test_pipeline_state(self):
        from src.core.risk_pipeline import RiskPipeline
        pipeline = RiskPipeline(total_capital=100000)
        state = pipeline.get_state()
        assert "cash" in state
        assert "nav" in state
        assert "drawdown_state" in state


class TestDataQuality:
    """測試數據質量模塊"""

    def test_validate_synthetic_data(self):
        from src.core.data_quality import DataIssue
        # 用合成數據測試（不依賴數據庫）
        issue = DataIssue("TEST", "test_type", "warning", "測試問題", 5, True)
        d = issue.to_dict()
        assert d["code"] == "TEST"
        assert d["severity"] == "warning"

    def test_generate_trading_dates(self):
        from src.core.data_quality import _generate_trading_dates
        from datetime import date
        dates = _generate_trading_dates(date(2024, 1, 1), date(2024, 1, 10))
        # 1/1 是元旦假期（但這個函數不排除），1/6-1/7 是週末
        assert len(dates) > 0
        # 不應包含週末
        for d in dates:
            assert d.weekday() < 5

    def test_filter_holiday_gaps(self):
        from src.core.data_quality import _filter_holiday_gaps
        from datetime import date
        # 4 天連續缺失（可能是假期）
        holiday = [date(2024, 2, 9), date(2024, 2, 10), date(2024, 2, 11), date(2024, 2, 12)]
        assert _filter_holiday_gaps(holiday) == []
        # 2 天缺失（不太像假期）
        gap = [date(2024, 3, 5), date(2024, 3, 6)]
        assert len(_filter_holiday_gaps(gap)) == 2
