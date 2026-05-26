import backtrader as bt

from src.core.strategies.base import OrderManagedStrategy
from src.core.strategies.registry import register_strategy

@register_strategy("kdj", "KDJ隨機指標策略")
class KDJStrategy(OrderManagedStrategy):
    """KDJ 策略"""
    params = (
        ("period", 9),
        ("period_dfast", 3),
        ("period_dslow", 3),
        ("overbought", 80),
        ("oversold", 20),
    )

    def __init__(self):
        super().__init__()
        self.stoch = bt.indicators.Stochastic(
            period=self.p.period,
            period_dfast=self.p.period_dfast,
            period_dslow=self.p.period_dslow,
        )

    def next(self):
        if self.order:
            return

        k = self.stoch.percK[0]
        d = self.stoch.percD[0]
        k_prev = self.stoch.percK[-1] if len(self.stoch.percK) > 1 else k
        d_prev = self.stoch.percD[-1] if len(self.stoch.percD) > 1 else d

        if k_prev <= d_prev and k > d and k < self.p.oversold and not self.position:
            self.order = self.buy()
        elif k_prev >= d_prev and k < d and k > self.p.overbought and self.position:
            self.order = self.sell()

