from src.core.strategies.base import OrderManagedStrategy
from src.core.strategies.registry import register_strategy


@register_strategy("grid", "網格交易策略")
class GridStrategy(OrderManagedStrategy):
    """網格交易策略"""

    params = (
        ("grid_pct", 3.0),
        ("position_pct", 0.1),
    )

    def __init__(self):
        super().__init__()
        self.grid_base = None
        self.grid_level = 0
        self.lot_size = 100

    def next(self):
        if self.order:
            return

        price = self.data.close[0]
        cash = self.broker.getcash()
        total_value = self.broker.getvalue()

        if self.grid_base is None:
            self.grid_base = price
            return

        grid_step = self.grid_base * self.p.grid_pct / 100.0
        if grid_step <= 0:
            return

        current_level = int((price - self.grid_base) / grid_step)

        if current_level < self.grid_level:
            target_value = total_value * self.p.position_pct
            shares = int(target_value / price / self.lot_size) * self.lot_size
            if shares >= self.lot_size and cash >= shares * price:
                self.order = self.buy(size=shares)
                self.grid_level = current_level

        elif current_level > self.grid_level and self.position:
            shares = min(
                self.position.size,
                int(self.position.size * self.p.position_pct / 100 * 100),
            )
            shares = max(shares, self.lot_size)
            if shares >= self.lot_size:
                self.order = self.sell(size=shares)
                self.grid_level = current_level
