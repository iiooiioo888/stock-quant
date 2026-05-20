"""組合方法 smoke 測試"""
import pytest

from src.core import portfolio as pf


PORTFOLIO_FUNCS = [
    "run_portfolio",
    "dynamic_weight_portfolio",
    "kelly_criterion",
    "arbitrate_signals",
    "risk_parity_portfolio",
    "mean_variance_optimize",
    "volatility_targeting",
    "max_diversification_portfolio",
    "anti_correlation_portfolio",
    "regime_switch_portfolio",
    "strategy_voting_portfolio",
]


@pytest.mark.parametrize("name", PORTFOLIO_FUNCS)
def test_portfolio_function_exists(name):
    assert hasattr(pf, name)
    assert callable(getattr(pf, name))
