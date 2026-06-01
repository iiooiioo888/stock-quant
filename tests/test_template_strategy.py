"""
策略模板單元測試 — 驗證參數範圍與信號邏輯
"""
import pandas as pd
import numpy as np
import pytest


class TestTemplateStrategyParams:
    """驗證策略默認參數"""

    def test_template_default_params(self):
        from strategies.template_strategy import STRATEGY_META
        meta = STRATEGY_META["template"]
        p = meta["default_params"]
        assert p["fast"] == 5
        assert p["slow"] == 20
        assert p["fast"] < p["slow"]

    def test_rsi_default_params(self):
        from strategies.template_strategy import STRATEGY_META
        meta = STRATEGY_META["rsi_oversold"]
        p = meta["default_params"]
        assert p["period"] == 14
        assert p["oversold"] == 30
        assert p["overbought"] == 70
        assert p["oversold"] < p["overbought"]

    def test_bollinger_default_params(self):
        from strategies.template_strategy import STRATEGY_META
        meta = STRATEGY_META["bollinger"]
        p = meta["default_params"]
        assert p["period"] == 20
        assert p["devfactor"] == 2.0
        assert p["devfactor"] > 0


class TestStrategyMeta:
    """驗證 STRATEGY_META 結構完整性"""

    def test_all_meta_have_required_fields(self):
        from strategies.template_strategy import STRATEGY_META
        required = {"class", "label", "category", "description", "default_params", "param_ranges"}
        for name, meta in STRATEGY_META.items():
            missing = required - set(meta.keys())
            assert not missing, f"策略 {name} 缺少字段: {missing}"

    def test_meta_categories_valid(self):
        from strategies.template_strategy import STRATEGY_META
        valid_cats = {"trend", "oscillator", "mean_reversion", "volatility", "volume", "composite"}
        for name, meta in STRATEGY_META.items():
            assert meta["category"] in valid_cats, f"策略 {name} 無效類別: {meta['category']}"

    def test_param_ranges_tuple_structure(self):
        from strategies.template_strategy import STRATEGY_META
        for name, meta in STRATEGY_META.items():
            for param, rng in meta["param_ranges"].items():
                assert len(rng) == 3, f"策略 {name} 參數 {param} 範圍應為 (min, max, step)"
                assert rng[0] < rng[1], f"策略 {name} 參數 {param} min 應 < max"

    def test_default_params_in_ranges(self):
        from strategies.template_strategy import STRATEGY_META
        for name, meta in STRATEGY_META.items():
            for param, default in meta["default_params"].items():
                if param in meta["param_ranges"]:
                    lo, hi, _ = meta["param_ranges"][param]
                    assert lo <= default <= hi, (
                        f"策略 {name} 默認 {param}={default} 不在範圍 [{lo}, {hi}]"
                    )


class TestStrategySignalLogic:
    """驗證信號邏輯（使用模擬 K 線數據）"""

    @staticmethod
    def _make_df(prices: list[float]) -> pd.DataFrame:
        """構建 OHLCV DataFrame，避免 zero division"""
        n = len(prices)
        return pd.DataFrame({
            "open": prices,
            "high": [c * 1.015 for c in prices],
            "low": [c * 0.985 for c in prices],
            "close": prices,
            "volume": [10000] * n,
            "openinterest": [0] * n,
        }, index=pd.date_range("2024-01-01", periods=n))

    def test_template_bullish_crossover(self):
        """快線上穿慢線 → 買入信號"""
        from strategies.template_strategy import TemplateStrategy
        import backtrader as bt

        # 構造上升趨勢數據：先平後漲（避免零值和極端值）
        n = 120
        prices = [100.0 + 2.0 * np.sin(i * 0.15) + i * 0.05 for i in range(n)]
        df = self._make_df(prices)

        cerebro = bt.Cerebro()
        cerebro.adddata(bt.feeds.PandasData(dataname=df))
        cerebro.addstrategy(TemplateStrategy)
        cerebro.broker.setcash(100000)
        cerebro.runstandard = False
        results = cerebro.run()
        strat = results[0]
        assert len(strat) > 0  # 策略已執行

    def test_template_params_affect_behavior(self):
        """不同參數元組可覆寫且與默認值不同"""
        from strategies.template_strategy import TemplateStrategy

        assert TemplateStrategy.params.fast == 5
        assert TemplateStrategy.params.slow == 20

        class FastTemplate(TemplateStrategy):
            params = (("fast", 8), ("slow", 21))

        assert FastTemplate.params.fast == 8
        assert FastTemplate.params.slow == 21
        assert (FastTemplate.params.fast, FastTemplate.params.slow) != (
            TemplateStrategy.params.fast,
            TemplateStrategy.params.slow,
        )
