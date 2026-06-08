import backtrader as bt

from src.core.strategies.base import OrderManagedStrategy
from src.core.strategies.registry import register_strategy


@register_strategy("triple_ma", "三重均線過濾策略")
class TripleMAFilterStrategy(OrderManagedStrategy):
    """三重均線多頭排列 + 快線金叉"""

    params = (("fast", 5), ("mid", 20), ("slow", 60))

    def __init__(self):
        super().__init__()
        self.ma_f = bt.indicators.SMA(period=self.p.fast)
        self.ma_m = bt.indicators.SMA(period=self.p.mid)
        self.ma_s = bt.indicators.SMA(period=self.p.slow)
        self.crossover = bt.indicators.CrossOver(self.ma_f, self.ma_m)

    def next(self):
        if self.order:
            return
        c = self.data.close[0]
        aligned = c > self.ma_f[0] > self.ma_m[0] > self.ma_s[0]
        if self.crossover > 0 and aligned and not self.position:
            self.order = self.buy()
        elif (self.crossover < 0 or c < self.ma_m[0]) and self.position:
            self.order = self.sell()
