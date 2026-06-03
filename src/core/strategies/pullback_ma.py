import backtrader as bt

from src.core.strategies.base import OrderManagedStrategy
from src.core.strategies.registry import register_strategy


@register_strategy("pullback_ma", "趨勢回調均線策略")
class PullbackMAStrategy(OrderManagedStrategy):
    """趨勢回調買入 — 長期均線向上時，短期均線金叉"""
    params = (("fast", 10), ("slow", 50), ("trend", 120))

    def __init__(self):
        super().__init__()
        self.ma_fast = bt.indicators.SMA(period=self.p.fast)
        self.ma_slow = bt.indicators.SMA(period=self.p.slow)
        self.ma_trend = bt.indicators.SMA(period=self.p.trend)
        self.crossover = bt.indicators.CrossOver(self.ma_fast, self.ma_slow)

    def next(self):
        if self.order:
            return
        c = self.data.close[0]
        uptrend = c > self.ma_trend[0] and self.ma_slow[0] > self.ma_trend[0]
        if self.crossover > 0 and uptrend and not self.position:
            self.order = self.buy()
        elif (self.crossover < 0 or c < self.ma_slow[0]) and self.position:
            self.order = self.sell()
