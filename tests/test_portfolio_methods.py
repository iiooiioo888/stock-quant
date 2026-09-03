"""組合方法 smoke + BL/HRP/CVaR/板塊限制（mock 子策略淨值）。"""

from datetime import datetime, timedelta

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
    "black_litterman_portfolio",
    "hierarchical_risk_parity",
    "cvar_optimize",
    "sector_exposure_limit",
]


def _fake_sub(strategy, code, params=None, cash=None):
    n = 80
    dates = [datetime(2024, 1, 2) + timedelta(days=i) for i in range(n)]
    seed = sum(ord(c) for c in f"{strategy}{code}") % 7
    daily = []
    nav = [1.0]
    for i in range(n):
        r = 0.0008 + 0.0003 * ((i + seed) % 5 - 2) / 2.0
        if code.startswith("000"):
            r -= 0.0002
        daily.append(r)
        nav.append(nav[-1] * (1 + r))
    return {
        "strategy": strategy,
        "code": code,
        "params": params or {},
        "dates": dates,
        "daily_returns": daily,
        "nav": nav,
        "total_return_pct": (nav[-1] - 1) * 100,
        "sharpe_ratio": 1.1,
        "max_drawdown_pct": 4.0,
        "total_trades": 6,
        "win_rate_pct": 55.0,
        "final_value": cash or 100000,
    }


ALLOCS = [
    {"strategy": "dual_ma", "code": "600519", "weight": 0.34},
    {"strategy": "rsi", "code": "000001", "weight": 0.33},
    {"strategy": "macd", "code": "300750", "weight": 0.33},
]


@pytest.mark.parametrize("name", PORTFOLIO_FUNCS)
def test_portfolio_function_exists(name):
    assert hasattr(pf, name)
    assert callable(getattr(pf, name))


def test_black_litterman_with_mock_nav(monkeypatch):
    monkeypatch.setattr(pf, "_run_strategy_on_data", _fake_sub)
    views = {"dual_ma/600519": 0.12}
    confidence = {"dual_ma/600519": 0.7}
    out = pf.black_litterman_portfolio(ALLOCS, views, confidence, cash=100000)
    assert "error" not in out
    assert out["method"] == "black_litterman"
    assert len(out["optimal_weights"]) == 3
    assert abs(sum(out["optimal_weights"]) - 1) < 0.05


def test_hrp_with_mock_nav(monkeypatch):
    monkeypatch.setattr(pf, "_run_strategy_on_data", _fake_sub)
    out = pf.hierarchical_risk_parity(ALLOCS, cash=100000)
    assert "error" not in out
    assert out["method"] == "hierarchical_risk_parity"
    assert len(out.get("optimal_weights") or out.get("weights") or []) >= 2


def test_cvar_optimize_with_mock_nav(monkeypatch):
    monkeypatch.setattr(pf, "_run_strategy_on_data", _fake_sub)
    out = pf.cvar_optimize(ALLOCS, cash=100000)
    assert "error" not in out
    assert out["method"] == "cvar_optimize"
    assert "optimal_cvar" in out


def test_sector_limit_caps_exposure(monkeypatch):
    monkeypatch.setattr(pf, "_run_strategy_on_data", _fake_sub)
    heavy = [
        {"strategy": "dual_ma", "code": "600519", "weight": 0.5},
        {"strategy": "macd", "code": "601318", "weight": 0.5},
        {"strategy": "rsi", "code": "000001", "weight": 0.0},
    ]
    out = pf.sector_exposure_limit(heavy, max_sector_pct=40.0, cash=100000)
    assert "error" not in out
    assert "sector_breakdown" in out
    assert out["method"] == "sector_exposure_limit"
