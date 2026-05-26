import backtrader as bt

from src.core.strategies.base import OrderManagedStrategy
from src.core.strategies.registry import register_strategy

@register_strategy("dual_ma", "雙均線金叉策略")
class DualMAStrategy(OrderManagedStrategy):
    """雙均線策略"""
    params = (
        ("fast", 5),
        ("slow", 20),
    )

    def __init__(self):
        super().__init__()
        self.ma_fast = bt.indicators.SMA(period=self.p.fast)
        self.ma_slow = bt.indicators.SMA(period=self.p.slow)
        self.crossover = bt.indicators.CrossOver(self.ma_fast, self.ma_slow)

    def next(self):
        if self.order:
            return
        if self.crossover > 0 and not self.position:
            self.order = self.buy()
        elif self.crossover < 0 and self.position:
            self.order = self.sell()

