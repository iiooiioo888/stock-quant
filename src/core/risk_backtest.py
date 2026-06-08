"""
回測 / 參數優化共用風控上下文 — 止損止盈、倉位上限、回撤熔斷評分懲罰。
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Any, Optional

import backtrader as bt


@dataclass
class RiskRunConfig:
    """與 run_backtest / optimize 共用的風控參數。"""

    stop_loss_pct: Optional[float] = None
    take_profit_pct: Optional[float] = None
    trailing_stop_pct: Optional[float] = None
    circuit_breaker_dd: Optional[float] = None
    max_position_pct: Optional[float] = None
    slippage_pct: float = 0.0
    commission: Optional[float] = None
    enable_t1: bool = True

    def has_sltp(self) -> bool:
        return any(
            x is not None and float(x) > 0
            for x in (self.stop_loss_pct, self.take_profit_pct, self.trailing_stop_pct)
        )

    def to_dict(self) -> dict:
        return {f.name: getattr(self, f.name) for f in fields(self)}

    @classmethod
    def from_dict(cls, data: dict | None) -> RiskRunConfig:
        if not data:
            return cls()
        known = {f.name for f in fields(cls)}
        kwargs = {k: data[k] for k in known if k in data and data[k] is not None}
        return cls(**kwargs)


def parse_risk_params(params: dict | None) -> RiskRunConfig:
    """從任務 params 或 API body 解析風控（支援嵌套 risk 或扁平鍵）。"""
    if not params:
        return RiskRunConfig()
    nested = params.get("risk")
    if isinstance(nested, dict):
        merged = {**params, **nested}
    else:
        merged = dict(params)
    return RiskRunConfig.from_dict(merged)


def attach_risk_to_cerebro(
    cerebro: bt.Cerebro,
    cfg: RiskRunConfig,
    *,
    sltp: bool = True,
    commission: bool = True,
    slippage: bool = True,
    sizer: bool = True,
) -> None:
    """在已有主策略後掛載 SLTP 層、滑點、倉位上限。"""
    from src.config import settings
    from src.core.strategies.base import StrategyWithSLTP

    if sltp:
        sltp_params = {}
        if cfg.stop_loss_pct is not None and cfg.stop_loss_pct > 0:
            sltp_params["stop_loss_pct"] = float(cfg.stop_loss_pct)
        if cfg.take_profit_pct is not None and cfg.take_profit_pct > 0:
            sltp_params["take_profit_pct"] = float(cfg.take_profit_pct)
        if cfg.trailing_stop_pct is not None and cfg.trailing_stop_pct > 0:
            sltp_params["trailing_stop_pct"] = float(cfg.trailing_stop_pct)
        if sltp_params:
            cerebro.addstrategy(StrategyWithSLTP, **sltp_params)

    if slippage:
        slip = float(cfg.slippage_pct or 0)
        if slip > 0:
            cerebro.broker.set_slippage_perc(slip / 100.0)

    if commission:
        comm = cfg.commission
        if comm is None:
            comm = settings.backtest_commission
        cerebro.broker.setcommission(commission=comm)

    if (
        sizer
        and cfg.max_position_pct is not None
        and 0 < float(cfg.max_position_pct) < 1
    ):
        pct = float(cfg.max_position_pct)

        class _CapSizer(bt.Sizer):
            params = (("percent", pct),)

            def _getsizing(self, comminfo=None):
                cash = self.broker.getcash()
                price = float(self.data.close[0]) or 1.0
                size = int((cash * self.p.percent) / price / 100) * 100
                return max(size, 100)

        cerebro.addsizer(_CapSizer, percent=pct)


def apply_risk_score_adjustment(result: dict, cfg: RiskRunConfig) -> float:
    """
    在基礎評分上套用風控懲罰（回撤熔斷、過深回撤）。
    調用前須已寫入 result['score']。
    返回調整後的 score（寫回 result['score'] / result['risk']）。
    """
    base = float(result.get("score", 0))
    risk_meta: dict[str, Any] = {
        "base_score": round(base, 6),
        "circuit_breaker_dd": cfg.circuit_breaker_dd,
        "max_position_pct": cfg.max_position_pct,
        "stop_loss_pct": cfg.stop_loss_pct,
    }
    adjusted = base
    dd = float(result.get("max_drawdown_pct") or 0)

    if cfg.circuit_breaker_dd is not None and cfg.circuit_breaker_dd > 0:
        threshold = float(cfg.circuit_breaker_dd)
        if dd >= threshold:
            excess = dd - threshold
            penalty = min(0.85, 0.35 + excess / max(threshold, 1) * 0.25)
            adjusted = base * (1.0 - penalty)
            risk_meta["circuit_breaker_hit"] = True
            risk_meta["circuit_penalty"] = round(penalty, 4)
        else:
            risk_meta["circuit_breaker_hit"] = False

    if cfg.max_position_pct is not None:
        risk_meta["position_cap_pct"] = float(cfg.max_position_pct)

    result["score"] = round(adjusted, 6)
    result["risk"] = risk_meta
    return adjusted
