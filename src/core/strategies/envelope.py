import backtrader as bt

from src.core.strategies.base import OrderManagedStrategy
from src.core.strategies.registry import register_strategy


@register_strategy("envelope", "均線通道策略")
class EnvelopeStrategy(OrderManagedStrategy):
    """均线通道策略 — 基于均线的上下轨通道，触下轨买入，触上轨卖出"""

    params = (
        ("period", 20),  # 均线周期
        ("deviation_pct", 5),  # 通道偏离百分比
    )

    def __init__(self):
        super().__init__()
        self.sma = bt.indicators.SMA(self.data.close, period=self.p.period)

    def next(self):
        if self.order:
            return

        price = self.data.close[0]
        ma = self.sma[0]
        upper = ma * (1 + self.p.deviation_pct / 100.0)
        lower = ma * (1 - self.p.deviation_pct / 100.0)

        if not self.position:
            # 买入：价格触及下轨
            if price <= lower:
                cash = self.broker.getcash()
                shares = int(cash * 0.95 / price / 100) * 100
                if shares >= 100:
                    self.order = self.buy(size=shares)
        else:
            # 卖出：价格触及上轨
            if price >= upper:
                self.order = self.sell()
