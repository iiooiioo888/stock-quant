import backtrader as bt

from src.core.strategies.base import OrderManagedStrategy
from src.core.strategies.registry import register_strategy


@register_strategy("momentum", "動量ROC策略")
class MomentumStrategy(OrderManagedStrategy):
    """動量策略 — 基於 N 日 ROC 動量指標，正動量買入，負動量賣出"""
    params = (
        ("lookback", 20),       # 動量回看期
        ("hold_period", 5),     # 持有期
        ("top_pct", 0.1),       # 動量排名百分比（單股用，此處保留）
    )

    def __init__(self):
        super().__init__()
        # 使用 ROC（Rate of Change）作為動量指標
        self.roc = bt.indicators.ROC(self.data.close, period=self.p.lookback)
        self.hold_counter = 0  # 持有計數器

    def next(self):
        if self.order:
            return

        roc_val = self.roc[0]

        if not self.position:
            # 買入條件：ROC > 0（正動量）
            if roc_val > 0:
                cash = self.broker.getcash()
                shares = int(cash * 0.95 / self.data.close[0] / 100) * 100
                if shares >= 100:
                    self.order = self.buy(size=shares)
                    self.hold_counter = 0
        else:
            self.hold_counter += 1
            # 賣出條件：ROC 轉負 或 持有超過 hold_period
            if roc_val < 0 or self.hold_counter >= self.p.hold_period:
                self.order = self.sell()

