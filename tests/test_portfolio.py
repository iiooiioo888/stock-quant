"""
組合模塊測試 — 測試組合回測、相關性、風險貢獻等
使用合成數據，無需外部服務
"""
import pytest
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock


def _generate_synthetic_returns(n: int = 252, seed: int = 42) -> list:
    """生成合成日收益率"""
    np.random.seed(seed)
    return list(np.random.normal(0.0003, 0.015, n))


def _generate_synthetic_nav(n: int = 252, seed: int = 42) -> tuple:
    """生成合成淨值序列和日期"""
    returns = _generate_synthetic_returns(n, seed)
    nav = [1.0]
    for r in returns:
        nav.append(nav[-1] * (1 + r))
    dates = [datetime(2024, 1, 1) + timedelta(days=i) for i in range(n + 1)]
    return nav, dates, returns


class TestPortfolioMetrics:
    """組合指標計算測試"""

    def test_calc_metrics(self):
        """測試指標計算"""
        from src.core.portfolio import _calc_metrics

        nav, dates, returns = _generate_synthetic_nav()
        metrics = _calc_metrics(nav, dates)

        assert "total_return_pct" in metrics
        assert "annual_return_pct" in metrics
        assert "max_drawdown_pct" in metrics
        assert "sharpe_ratio" in metrics
        assert "calmar_ratio" in metrics
        assert "var_95" in metrics
        assert "sortino_ratio" in metrics
        assert "annual_volatility" in metrics

    def test_max_drawdown_non_negative(self):
        """測試最大回撤為非負數"""
        from src.core.portfolio import _calc_metrics

        nav, dates, _ = _generate_synthetic_nav()
        metrics = _calc_metrics(nav, dates)
        assert metrics["max_drawdown_pct"] >= 0

    def test_metrics_empty_nav(self):
        """測試空淨值序列"""
        from src.core.portfolio import _calc_metrics

        metrics = _calc_metrics([1.0], [])
        assert metrics == {}


class TestAlignNavs:
    """淨值對齊測試"""

    def test_align_common_dates(self):
        """測試共同日期對齊"""
        from src.core.portfolio import _align_navs

        sub_results = [
            {
                "dates": [datetime(2024, 1, 1), datetime(2024, 1, 2), datetime(2024, 1, 3)],
                "daily_returns": [0.01, -0.005, 0.02],
            },
            {
                "dates": [datetime(2024, 1, 2), datetime(2024, 1, 3), datetime(2024, 1, 4)],
                "daily_returns": [0.015, -0.01, 0.005],
            },
        ]

        common_dates, aligned_navs = _align_navs(sub_results)
        assert len(common_dates) == 2  # 1/2, 1/3
        assert len(aligned_navs) == 2
        assert len(aligned_navs[0]) == len(aligned_navs[1])


class TestCorrelationCalculation:
    """相關性計算測試"""

    def test_calc_correlations(self):
        """測試相關性矩陣計算"""
        from src.core.portfolio import calc_strategy_correlations

        # 生成兩個有一定相關性的序列
        np.random.seed(42)
        n = 252
        base = np.random.normal(0.0003, 0.015, n)
        returns_a = list(base + np.random.normal(0, 0.005, n))
        returns_b = list(base * 0.5 + np.random.normal(0, 0.01, n))

        dates = [datetime(2024, 1, 1) + timedelta(days=i) for i in range(n)]

        sub_results = [
            {"strategy": "dual_ma", "code": "000001", "dates": dates, "daily_returns": returns_a},
            {"strategy": "macd", "code": "600519", "dates": dates, "daily_returns": returns_b},
        ]

        corr = calc_strategy_correlations(sub_results)
        assert "labels" in corr
        assert "matrix" in corr
        assert len(corr["matrix"]) == 2
        assert len(corr["matrix"][0]) == 2
        # 對角線應接近 1
        assert corr["matrix"][0][0] > 0.9
        assert corr["matrix"][1][1] > 0.9
        # 因為有共同的 base，非對角線應為正
        assert corr["matrix"][0][1] > 0

    def test_single_strategy_correlation(self):
        """測試單策略相關性（應返回空）"""
        from src.core.portfolio import calc_strategy_correlations

        sub_results = [
            {"strategy": "dual_ma", "code": "000001", "dates": [], "daily_returns": []},
        ]
        corr = calc_strategy_correlations(sub_results)
        assert corr["labels"] == []


class TestRiskContribution:
    """風險貢獻測試"""

    def test_calc_risk_contribution(self):
        """測試風險貢獻計算"""
        from src.core.portfolio import _calc_risk_contribution

        np.random.seed(42)
        n = 252
        dates = [datetime(2024, 1, 1) + timedelta(days=i) for i in range(n)]

        sub_results = [
            {"strategy": "dual_ma", "code": "000001", "dates": dates,
             "daily_returns": list(np.random.normal(0.0003, 0.015, n))},
            {"strategy": "macd", "code": "600519", "dates": dates,
             "daily_returns": list(np.random.normal(0.0005, 0.02, n))},
        ]

        result = _calc_risk_contribution(sub_results, [0.5, 0.5])
        assert len(result) == 2
        assert "risk_contribution" in result[0]
        assert "risk_pct" in result[0]


class TestPortfolioNav:
    """組合淨值計算測試"""

    def test_calc_portfolio_nav(self):
        """測試組合淨值計算"""
        from src.core.portfolio import _calc_portfolio_nav

        nav_a = [1.0, 1.01, 1.02, 1.03, 1.04]
        nav_b = [1.0, 0.99, 1.00, 1.01, 1.02]

        portfolio = _calc_portfolio_nav([nav_a, nav_b], [0.5, 0.5])
        assert len(portfolio) == 5
        assert portfolio[0] == 1.0
        # 組合淨值應在兩個子策略之間
        assert portfolio[-1] > min(nav_a[-1], nav_b[-1])
        assert portfolio[-1] < max(nav_a[-1], nav_b[-1])
