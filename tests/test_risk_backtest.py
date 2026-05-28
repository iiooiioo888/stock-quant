"""風控回測上下文與優化評分懲罰"""
from src.core.risk_backtest import (
    RiskRunConfig,
    apply_risk_score_adjustment,
    parse_risk_params,
)


def test_parse_risk_params_nested():
    p = parse_risk_params({
        "code": "600519",
        "risk": {"stop_loss_pct": 8, "circuit_breaker_dd": 20},
    })
    assert p.stop_loss_pct == 8
    assert p.circuit_breaker_dd == 20


def test_circuit_breaker_penalizes_score():
    cfg = RiskRunConfig(circuit_breaker_dd=15.0)
    result = {
        "score": 2.0,
        "max_drawdown_pct": 25.0,
        "total_trades": 10,
    }
    apply_risk_score_adjustment(result, cfg)
    assert result["score"] < 2.0
    assert result["risk"]["circuit_breaker_hit"] is True


def test_no_penalty_under_threshold():
    cfg = RiskRunConfig(circuit_breaker_dd=20.0)
    result = {
        "score": 1.5,
        "max_drawdown_pct": 12.0,
        "total_trades": 5,
    }
    apply_risk_score_adjustment(result, cfg)
    assert result["score"] == 1.5
    assert result["risk"]["circuit_breaker_hit"] is False
