import backtrader as bt

from src.core.strategies.base import OrderManagedStrategy
from src.core.strategies.registry import register_strategy

@register_strategy("williams_r", "威廉指標策略")
class WilliamsRStrategy(OrderManagedStrategy):
    """威廉指標 %R 超買超賣反轉"""
    params = (("period", 14), ("overbought", -20), ("oversold", -80))

    def __init__(self):
        super().__init__()
        self.wr = bt.indicators.WilliamsR(period=self.p.period)

    def next(self):
        if self.order:
            return
        wr = self.wr[0]
        wr_prev = self.wr[-1] if len(self.wr) > 1 else wr
        if wr_prev >= self.p.oversold and wr < self.p.oversold and not self.position:
            self.order = self.buy()
        elif wr_prev <= self.p.overbought and wr > self.p.overbought and self.position:
            self.order = self.sell()

