"""策略註冊表 — 統一 key / 顯示名 / Backtrader 策略類。"""
from __future__ import annotations

from typing import Type

import backtrader as bt

STRATEGIES: dict[str, Type[bt.Strategy]] = {}
STRATEGY_NAMES: dict[str, str] = {}


def register_strategy(key: str, display_name: str):
    """裝飾器：將策略類註冊到全局表。"""

    def decorator(cls: Type[bt.Strategy]) -> Type[bt.Strategy]:
        if key in STRATEGIES:
            raise ValueError(f"策略 key 重複註冊: {key}")
        STRATEGIES[key] = cls
        STRATEGY_NAMES[key] = display_name
        return cls

    return decorator


def get_strategy_class(key: str) -> Type[bt.Strategy]:
    cls = STRATEGIES.get(key)
    if cls is None:
        raise KeyError(f"未知策略: {key}，可選: {list(STRATEGIES.keys())}")
    return cls


def list_strategy_keys() -> list[str]:
    return sorted(STRATEGIES.keys())
