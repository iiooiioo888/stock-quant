import backtrader as bt

from src.core.strategies.base import OrderManagedStrategy
from src.core.strategies.registry import register_strategy


@register_strategy("ema_cross", "EMA交叉策略")
class EMACrossStrategy(OrderManagedStrategy):
    """EMA 交叉 — 對近期價格更敏感"""
    params = (("fast", 12), ("slow", 26))

    def __init__(self):
        super().__init__()
        self.ema_fast = bt.indicators.EMA(period=self.p.fast)
        self.ema_slow = bt.indicators.EMA(period=self.p.slow)
        self.crossover = bt.indicators.CrossOver(self.ema_fast, self.ema_slow)

    def next(self):
        if self.order:
            return
        if self.crossover > 0 and not self.position:
            self.order = self.buy()
        elif self.crossover < 0 and self.position:
            self.order = self.sell()

