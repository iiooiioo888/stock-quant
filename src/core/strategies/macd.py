import backtrader as bt

from src.core.strategies.base import OrderManagedStrategy
from src.core.strategies.registry import register_strategy


@register_strategy("macd", "MACD金叉策略")
class MACDStrategy(OrderManagedStrategy):
    """MACD 策略"""

    params = (
        ("fast", 12),
        ("slow", 26),
        ("signal", 9),
    )

    def __init__(self):
        super().__init__()
        self.macd = bt.indicators.MACD(
            period_me1=self.p.fast,
            period_me2=self.p.slow,
            period_signal=self.p.signal,
        )
        self.crossover = bt.indicators.CrossOver(self.macd.macd, self.macd.signal)

    def next(self):
        if self.order:
            return
        if self.crossover > 0 and not self.position:
            self.order = self.buy()
        elif self.crossover < 0 and self.position:
            self.order = self.sell()
