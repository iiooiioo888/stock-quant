import backtrader as bt

from src.core.strategies.base import OrderManagedStrategy
from src.core.strategies.registry import register_strategy

@register_strategy("bollinger", "布林帶突破策略")
class BollingerStrategy(OrderManagedStrategy):
    """布林帶策略"""
    params = (
        ("period", 20),
        ("devfactor", 2.0),
    )

    def __init__(self):
        super().__init__()
        self.boll = bt.indicators.BollingerBands(
            period=self.p.period, devfactor=self.p.devfactor
        )

    def next(self):
        if self.order:
            return
        if not self.position and self.data.close < self.boll.lines.bot:
            self.order = self.buy()
        elif self.position and self.data.close > self.boll.lines.top:
            self.order = self.sell()

