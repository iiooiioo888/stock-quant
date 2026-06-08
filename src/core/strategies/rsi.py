import backtrader as bt

from src.core.strategies.base import OrderManagedStrategy
from src.core.strategies.registry import register_strategy


@register_strategy("rsi", "RSI相對強弱策略")
class RSIStrategy(OrderManagedStrategy):
    """RSI 策略"""

    params = (
        ("period", 14),
        ("overbought", 70),
        ("oversold", 30),
    )

    def __init__(self):
        super().__init__()
        self.rsi = bt.indicators.RSI(period=self.p.period)

    def next(self):
        if self.order:
            return

        rsi = self.rsi[0]
        rsi_prev = self.rsi[-1] if len(self.rsi) > 1 else rsi

        if rsi_prev < self.p.oversold and rsi >= self.p.oversold and not self.position:
            self.order = self.buy()
        elif (
            rsi_prev > self.p.overbought and rsi <= self.p.overbought and self.position
        ):
            self.order = self.sell()
