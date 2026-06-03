import backtrader as bt

from src.core.strategies.base import OrderManagedStrategy
from src.core.strategies.registry import register_strategy


@register_strategy("breakout", "N日高點突破策略")
class BreakoutStrategy(OrderManagedStrategy):
    """突破策略 — N 日高點突破買入，ATR 移動止損賣出"""
    params = (
        ("period", 60),          # N日高點突破
        ("atr_period", 20),      # ATR 週期
        ("atr_multiplier", 2.0), # ATR 止損倍數
    )

    def __init__(self):
        super().__init__()
        self.highest = bt.indicators.Highest(self.data.high, period=self.p.period)
        self.atr = bt.indicators.ATR(period=self.p.atr_period)
        self.entry_price = None
        self.trailing_stop = None

    def next(self):
        if self.order:
            return

        price = self.data.close[0]
        atr_val = self.atr[0]

        if not self.position:
            # 買入：價格突破 N 日最高價
            highest_prev = self.highest[-1]
            if highest_prev is not None and price > highest_prev:
                cash = self.broker.getcash()
                shares = int(cash * 0.95 / price / 100) * 100
                if shares >= 100:
                    self.order = self.buy(size=shares)
                    self.entry_price = price
                    self.trailing_stop = price - atr_val * self.p.atr_multiplier
        else:
            # 更新移動止損（只會上移，不會下移）
            new_stop = price - atr_val * self.p.atr_multiplier
            if self.trailing_stop is not None and new_stop > self.trailing_stop:
                self.trailing_stop = new_stop

            # 賣出：價格跌破移動止損
            if self.trailing_stop is not None and price < self.trailing_stop:
                self.order = self.sell()
                self.entry_price = None
                self.trailing_stop = None

