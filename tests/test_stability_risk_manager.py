"""
風控管理器穩定性測試 — PositionSizer、RiskBudget、DrawdownProtector

覆蓋：
  - PositionSizer 各方法邊界條件
  - RiskBudget 風險預算檢查
  - DrawdownProtector 狀態切換
  - drawdown_circuit_breaker 熔斷邏輯
  - 並發安全
"""
from __future__ import annotations

import math
import pytest

from src.core.risk_manager import (
    PositionSizer,
    RiskBudget,
    DrawdownProtector,
    drawdown_circuit_breaker,
)


# ── PositionSizer ───────────────────────────────────────────────

class TestPositionSizer:
    """倉位管理器測試。"""

    @pytest.fixture
    def sizer(self):
        return PositionSizer(total_capital=1000000, max_risk_per_trade=0.02)

    # -- fixed_fraction --
    def test_fixed_fraction_10pct(self, sizer):
        assert sizer.fixed_fraction(0.1) == 100000

    def test_fixed_fraction_1pct(self, sizer):
        assert sizer.fixed_fraction(0.01) == 10000

    def test_fixed_fraction_100pct(self, sizer):
        assert sizer.fixed_fraction(1.0) == 1000000

    def test_fixed_fraction_zero_raises(self, sizer):
        with pytest.raises(ValueError):
            sizer.fixed_fraction(0)

    def test_fixed_fraction_negative_raises(self, sizer):
        with pytest.raises(ValueError):
            sizer.fixed_fraction(-0.1)

    def test_fixed_fraction_over_100_raises(self, sizer):
        with pytest.raises(ValueError):
            sizer.fixed_fraction(1.5)

    # -- atr_based --
    def test_atr_basic(self, sizer):
        shares = sizer.atr_based(atr=2.0, risk_multiplier=1.0)
        # risk_amount = 1000000 * 0.02 = 20000
        # shares = 20000 / (2.0 * 1.0) = 10000
        assert shares == 10000
        assert shares % 100 == 0, "A股最小單位 100 股"

    def test_atr_small_value_large_position(self, sizer):
        shares = sizer.atr_based(atr=0.1)
        assert shares >= 100
        assert shares % 100 == 0

    def test_atr_large_value_small_position(self, sizer):
        shares = sizer.atr_based(atr=100.0)
        assert shares >= 100  # 至少 100 股

    def test_atr_zero_raises(self, sizer):
        with pytest.raises(ValueError):
            sizer.atr_based(atr=0)

    def test_atr_negative_raises(self, sizer):
        with pytest.raises(ValueError):
            sizer.atr_based(atr=-1.0)

    def test_atr_with_multiplier(self, sizer):
        shares_1x = sizer.atr_based(atr=2.0, risk_multiplier=1.0)
        shares_2x = sizer.atr_based(atr=2.0, risk_multiplier=2.0)
        assert shares_2x <= shares_1x, "乘數越大倉位越小"

    # -- kelly_position --
    def test_kelly_basic(self, sizer):
        pos = sizer.kelly_position(win_rate=0.6, avg_win=3000, avg_loss=2000)
        assert pos > 0
        assert pos <= sizer.total_capital * 0.25, "Half-Kelly 上限 25%"

    def test_kelly_negative_edge(self, sizer):
        """期望值為負時 Kelly 應返回 0。"""
        pos = sizer.kelly_position(win_rate=0.3, avg_win=1000, avg_loss=5000)
        assert pos == 0.0

    def test_kelly_high_win_rate(self, sizer):
        pos = sizer.kelly_position(win_rate=0.9, avg_win=5000, avg_loss=1000)
        assert pos > 0
        assert pos <= sizer.total_capital * 0.25

    def test_kelly_win_rate_zero_raises(self, sizer):
        with pytest.raises(ValueError):
            sizer.kelly_position(win_rate=0, avg_win=1000, avg_loss=500)

    def test_kelly_win_rate_one_raises(self, sizer):
        with pytest.raises(ValueError):
            sizer.kelly_position(win_rate=1.0, avg_win=1000, avg_loss=500)

    def test_kelly_avg_win_zero_raises(self, sizer):
        with pytest.raises(ValueError):
            sizer.kelly_position(win_rate=0.5, avg_win=0, avg_loss=500)

    # -- volatility_target --
    def test_vol_target_reduce_position(self, sizer):
        """當前波動率高於目標 → 縮倉。"""
        pos = sizer.volatility_target(target_vol=0.15, current_vol=0.30, current_position=100000)
        assert pos < 100000

    def test_vol_target_increase_position(self, sizer):
        """當前波動率低於目標 → 加倉。"""
        pos = sizer.volatility_target(target_vol=0.30, current_vol=0.15, current_position=100000)
        assert pos > 100000

    def test_vol_target_zero_vol_raises(self, sizer):
        with pytest.raises(ValueError):
            sizer.volatility_target(target_vol=0.15, current_vol=0, current_position=100000)

    def test_vol_target_capped_at_total(self, sizer):
        """調整後倉位不超過總資金。"""
        pos = sizer.volatility_target(target_vol=0.50, current_vol=0.10, current_position=900000)
        assert pos <= sizer.total_capital

    def test_vol_target_floor(self, sizer):
        """調整比例下限 0.1。"""
        pos = sizer.volatility_target(target_vol=0.01, current_vol=0.50, current_position=100000)
        assert pos >= 100000 * 0.1

    # -- drawdown_adjusted --
    def test_dd_no_adjustment_below_5(self, sizer):
        pos = sizer.drawdown_adjusted(current_dd_pct=3.0, base_size=100000)
        assert pos == 100000

    def test_dd_7pct_reduced(self, sizer):
        pos = sizer.drawdown_adjusted(current_dd_pct=7.0, base_size=100000)
        assert pos < 100000
        assert pos > 70000

    def test_dd_15pct_more_reduced(self, sizer):
        pos = sizer.drawdown_adjusted(current_dd_pct=15.0, base_size=100000)
        assert pos < 75000

    def test_dd_25pct_minimum(self, sizer):
        pos = sizer.drawdown_adjusted(current_dd_pct=25.0, base_size=100000)
        assert pos == 100000 * 0.25

    def test_dd_negative_handled(self, sizer):
        """負回撤取絕對值。"""
        pos = sizer.drawdown_adjusted(current_dd_pct=-10.0, base_size=100000)
        assert pos == sizer.drawdown_adjusted(current_dd_pct=10.0, base_size=100000)


# ── RiskBudget ──────────────────────────────────────────────────

class TestRiskBudget:
    """風險預算管理。"""

    @pytest.fixture
    def budget(self):
        return RiskBudget(max_portfolio_risk=0.15, max_single_risk=0.05)

    def test_check_position_within_limit(self, budget):
        result = budget.check_position(
            position_value=50000, total_value=1000000, position_vol=0.20
        )
        assert result["exceeds_limit"] is False
        # position_pct 是小數比例 (0.05 = 5%)
        assert result["position_pct"] == pytest.approx(0.05, rel=1e-2)

    def test_check_position_exceeds(self, budget):
        result = budget.check_position(
            position_value=500000, total_value=1000000, position_vol=0.30
        )
        assert result["exceeds_limit"] is True

    def test_portfolio_risk_budget_empty(self, budget):
        result = budget.portfolio_risk_budget([])
        assert "error" in result  # 空持倉返回錯誤

    def test_portfolio_risk_budget_normal(self, budget):
        positions = [
            {"value": 100000, "vol": 0.20, "code": "000001"},
            {"value": 200000, "vol": 0.15, "code": "000002"},
        ]
        result = budget.portfolio_risk_budget(positions)
        assert result["total_value"] == 300000
        assert result["total_risk"] > 0

    def test_suggest_rebalance(self, budget):
        positions = [
            {"value": 500000, "vol": 0.30, "code": "000001"},
            {"value": 100000, "vol": 0.10, "code": "000002"},
        ]
        suggestions = budget.suggest_rebalance(positions)
        assert len(suggestions) == 2
        for s in suggestions:
            assert "action" in s
            assert s["action"] in ("減倉", "加倉", "保持")


# ── DrawdownProtector ───────────────────────────────────────────

class TestDrawdownProtector:
    """回撤保護器。"""

    @pytest.fixture
    def protector(self):
        return DrawdownProtector(max_drawdown_pct=20.0, warning_pct=10.0)

    def test_initial_state(self, protector):
        result = protector.update(1000000)
        assert result["status"] == "正常"
        assert result["current_dd"] == 0

    def test_warning_state(self, protector):
        protector.update(1000000)  # peak = 1000000
        result = protector.update(890000)  # -11%
        assert result["status"] in ("警告", "危險")

    def test_danger_state(self, protector):
        protector.update(1000000)
        result = protector.update(750000)  # -25%
        assert result["status"] == "停止"

    def test_recovery(self, protector):
        protector.update(1000000)
        protector.update(850000)  # -15%
        result = protector.update(1050000)  # 新高
        assert result["current_dd"] == 0

    def test_position_multiplier_decreases(self, protector):
        assert protector.get_position_multiplier(0) == 1.0
        assert protector.get_position_multiplier(5) == 1.0
        assert protector.get_position_multiplier(15) < 1.0
        assert protector.get_position_multiplier(20) == 0.0

    def test_multiple_updates_monotonic(self, protector):
        """持續下跌時 position_multiplier 應遞減。"""
        protector.update(1000000)
        multipliers = []
        for dd in range(1, 25):
            val = 1000000 * (1 - dd / 100)
            result = protector.update(val)
            multipliers.append(result.get("position_multiplier", 1.0))
        # 應該總體遞減
        assert multipliers[-1] <= multipliers[0]


# ── drawdown_circuit_breaker ────────────────────────────────────

class TestDrawdownCircuitBreaker:
    """回撤熔斷分析。"""

    def test_no_breaker_on_steady_growth(self):
        nav = [100 + i * 0.5 for i in range(100)]
        dates = [f"2024-01-{i+1:02d}" for i in range(100)]
        result = drawdown_circuit_breaker(nav, dates, max_dd=20.0)
        assert result["total_triggers"] == 0

    def test_breaker_on_big_drop(self):
        nav = [100] * 50 + [70] * 50  # -30% drop
        dates = [f"2024-01-{i+1:02d}" for i in range(100)]
        result = drawdown_circuit_breaker(nav, dates, max_dd=20.0)
        assert result["total_triggers"] >= 1
        assert result["would_stop_trading"] is True

    def test_empty_nav(self):
        result = drawdown_circuit_breaker([], [], max_dd=20.0)
        assert "error" in result  # 空序列返回錯誤

    def test_single_nav(self):
        result = drawdown_circuit_breaker([100], ["2024-01-01"], max_dd=20.0)
        assert result.get("total_triggers", 0) == 0

    def test_multiple_drops(self):
        """多次觸發熔斷。"""
        nav = [100] * 20 + [75] * 20 + [100] * 20 + [70] * 20
        dates = [f"2024-01-{i+1:02d}" for i in range(80)]
        result = drawdown_circuit_breaker(nav, dates, max_dd=20.0)
        assert result["total_triggers"] >= 1

    def test_custom_threshold(self):
        """自定義熔斷閾值。"""
        nav = [100] * 50 + [92] * 50  # -8% drop
        dates = [f"2024-01-{i+1:02d}" for i in range(100)]
        # max_dd=5% 會觸發
        result = drawdown_circuit_breaker(nav, dates, max_dd=5.0)
        assert result["total_triggers"] >= 1
        # max_dd=10% 不觸發
        result2 = drawdown_circuit_breaker(nav, dates, max_dd=10.0)
        assert result2["total_triggers"] == 0


# ── DrawdownProtector 併發 ──────────────────────────────────────

class TestDrawdownProtectorConcurrency:
    """回撤保護器併發安全。"""

    def test_concurrent_updates(self):
        """多線程同時 update 不崩潰。"""
        import threading
        from concurrent.futures import ThreadPoolExecutor, as_completed
        protector = DrawdownProtector(max_drawdown_pct=20.0, warning_pct=10.0)
        protector.update(1000000)  # set peak
        errors = []

        def _update(val):
            try:
                return protector.update(val)
            except Exception as e:
                errors.append(e)
                return None

        with ThreadPoolExecutor(max_workers=8) as pool:
            futs = [pool.submit(_update, 1000000 - i * 10000) for i in range(20)]
            results = [f.result(timeout=5) for f in as_completed(futs)]

        assert len(errors) == 0
        assert all(r is not None for r in results)

    def test_position_multiplier_thread_safety(self):
        """get_position_multiplier 併發調用。"""
        import threading
        protector = DrawdownProtector()
        errors = []

        def _get(dd):
            try:
                return protector.get_position_multiplier(dd)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=_get, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)
        assert len(errors) == 0


# ── RiskBudget 進階邊界 ────────────────────────────────────────

class TestRiskBudgetAdvanced:
    """風險預算進階測試。"""

    def test_check_position_zero_value(self):
        budget = RiskBudget(max_portfolio_risk=0.15, max_single_risk=0.05)
        result = budget.check_position(0, 1000000, 0.20)
        assert result["exceeds_limit"] is False

    def test_portfolio_risk_budget_single_position(self):
        budget = RiskBudget()
        positions = [{"value": 100000, "vol": 0.25, "code": "000001"}]
        result = budget.portfolio_risk_budget(positions)
        assert result["total_value"] == 100000
        assert result["total_risk"] > 0

    def test_suggest_rebalance_all_within_limit(self):
        budget = RiskBudget(max_portfolio_risk=0.50, max_single_risk=0.50)
        positions = [
            {"value": 100000, "vol": 0.10, "code": "000001"},
            {"value": 100000, "vol": 0.10, "code": "000002"},
        ]
        suggestions = budget.suggest_rebalance(positions)
        for s in suggestions:
            assert s["action"] in ("減倉", "加倉", "保持")
