"""
內置回測策略包 — 每策略獨立模組，經 registry 統一註冊。

對外主要使用 STRATEGIES / STRATEGY_NAMES；回測引擎見 src.core.backtest。
"""

from __future__ import annotations

from .base import OrderManagedStrategy, StrategyWithSLTP
from .registry import (
    STRATEGIES,
    STRATEGY_NAMES,
    get_strategy_class,
    list_strategy_keys,
    register_strategy,
)

_BUILTIN_MODULES = (
    "dual_ma",
    "macd",
    "bollinger",
    "kdj",
    "rsi",
    "grid",
    "turtle",
    "momentum",
    "mean_reversion",
    "volume_price",
    "breakout",
    "composite",
    "dual_thrust",
    "vwap",
    "envelope",
    "parabolic_sar",
    "obv",
    "bollinger_squeeze",
    "adx_trend",
    "ema_cross",
    "donchian",
    "williams_r",
    "cci",
    "supertrend",
    "atr_trail",
    "ema_volume",
    "triple_ma",
    "macd_rsi",
    "pullback_ma",
)


def load_builtin_strategies() -> None:
    """導入所有策略模組以觸發 @register_strategy。"""
    import importlib

    pkg = __name__
    for name in _BUILTIN_MODULES:
        importlib.import_module(f"{pkg}.{name}")


def _export_class_aliases() -> None:
    """向包命名空間注入 DualMAStrategy 等類名（兼容舊 import）。"""
    for cls in STRATEGIES.values():
        globals()[cls.__name__] = cls


load_builtin_strategies()
_export_class_aliases()

__all__ = [
    "STRATEGIES",
    "STRATEGY_NAMES",
    "OrderManagedStrategy",
    "StrategyWithSLTP",
    "register_strategy",
    "get_strategy_class",
    "list_strategy_keys",
    "load_builtin_strategies",
    *_BUILTIN_MODULES,
]
