import backtrader as bt

from src.core.strategies.base import OrderManagedStrategy
from src.core.strategies.registry import register_strategy


@register_strategy("cci", "CCI商品通道策略")
class CCIStrategy(OrderManagedStrategy):
    """CCI 商品通道 — 偏離均值反轉"""

    params = (("period", 20), ("overbought", 100), ("oversold", -100))

    def __init__(self):
        super().__init__()
        self.cci = bt.indicators.CCI(period=self.p.period)

    def next(self):
        if self.order:
            return
        cci = self.cci[0]
        cci_prev = self.cci[-1] if len(self.cci) > 1 else cci
        if cci_prev < self.p.oversold and cci >= self.p.oversold and not self.position:
            self.order = self.buy()
        elif (
            cci_prev > self.p.overbought and cci <= self.p.overbought and self.position
        ):
            self.order = self.sell()
