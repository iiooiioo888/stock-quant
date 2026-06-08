import backtrader as bt

from src.core.strategies.base import OrderManagedStrategy
from src.core.strategies.registry import register_strategy


@register_strategy("donchian", "唐奇安通道突破策略")
class DonchianStrategy(OrderManagedStrategy):
    """唐奇安通道突破"""

    params = (("period", 20),)

    def __init__(self):
        super().__init__()
        self.high_n = bt.indicators.Highest(self.data.high, period=self.p.period)
        self.low_n = bt.indicators.Lowest(self.data.low, period=self.p.period)

    def next(self):
        if self.order:
            return
        price = self.data.close[0]
        if not self.position and price >= self.high_n[-1]:
            self.order = self.buy()
        elif self.position and price <= self.low_n[-1]:
            self.order = self.sell()
