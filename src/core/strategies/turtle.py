import backtrader as bt

from src.core.strategies.base import OrderManagedStrategy
from src.core.strategies.registry import register_strategy


@register_strategy("turtle", "海龜趨勢跟蹤策略")
class TurtleStrategy(OrderManagedStrategy):
    """海龜交易策略"""

    params = (
        ("entry_period", 20),
        ("exit_period", 10),
        ("atr_period", 20),
        ("risk_pct", 1.0),
    )

    def __init__(self):
        super().__init__()
        self.highest = bt.indicators.Highest(self.data.high, period=self.p.entry_period)
        self.lowest = bt.indicators.Lowest(self.data.low, period=self.p.exit_period)
        self.atr = bt.indicators.ATR(period=self.p.atr_period)

    def next(self):
        if self.order:
            return

        price = self.data.close[0]
        total_value = self.broker.getvalue()

        if not self.position and price > self.highest[-1]:
            risk_amount = total_value * self.p.risk_pct / 100.0
            atr = self.atr[0]
            if atr > 0:
                shares = int(risk_amount / atr / 100) * 100
                if shares >= 100:
                    self.order = self.buy(size=shares)

        elif self.position and price < self.lowest[-1]:
            self.order = self.sell()
