import backtrader as bt

from src.core.strategies.base import OrderManagedStrategy
from src.core.strategies.registry import register_strategy


@register_strategy("supertrend", "超級趨勢策略")
class SuperTrendStrategy(OrderManagedStrategy):
    """超級趨勢（ATR 軌跡翻轉）"""
    params = (("period", 10), ("multiplier", 3.0))

    def __init__(self):
        super().__init__()
        self.atr = bt.indicators.ATR(period=self.p.period)
        self.direction = 0

    def next(self):
        if self.order or len(self.data) < self.p.period + 2:
            return
        hl2 = (self.data.high[0] + self.data.low[0]) / 2.0
        atr = max(self.atr[0], 1e-9)
        upper = hl2 + self.p.multiplier * atr
        lower = hl2 - self.p.multiplier * atr
        close = self.data.close[0]
        if close > upper:
            self.direction = 1
        elif close < lower:
            self.direction = -1
        if self.direction == 1 and not self.position:
            self.order = self.buy()
        elif self.direction == -1 and self.position:
            self.order = self.sell()

