from src.core.strategies.base import OrderManagedStrategy
from src.core.strategies.registry import register_strategy


@register_strategy("dual_thrust", "雙軌日內突破策略")
class DualThrustStrategy(OrderManagedStrategy):
    """DualThrust 策略"""

    params = (
        ("period", 4),
        ("k_up", 0.5),
        ("k_down", 0.5),
    )

    def __init__(self):
        super().__init__()

    def next(self):
        if self.order:
            return

        if len(self.data) < self.p.period + 1:
            return

        highs = [self.data.high[-i] for i in range(1, self.p.period + 1)]
        lows = [self.data.low[-i] for i in range(1, self.p.period + 1)]
        closes = [self.data.close[-i] for i in range(1, self.p.period + 1)]

        hh = max(highs)
        ll = min(lows)
        hc = max(closes)
        lc = min(closes)

        range_val = max(hh - lc, hc - ll)

        open_price = self.data.open[0]
        upper = open_price + self.p.k_up * range_val
        lower = open_price - self.p.k_down * range_val

        price = self.data.close[0]

        if not self.position and price > upper:
            cash = self.broker.getcash()
            shares = int(cash * 0.95 / price / 100) * 100
            if shares >= 100:
                self.order = self.buy(size=shares)

        elif self.position and price < lower:
            self.order = self.sell()
