import backtrader as bt

from src.core.strategies.base import OrderManagedStrategy
from src.core.strategies.registry import register_strategy

@register_strategy("atr_trail", "ATR移動止損趨勢策略")
class ATRTrailTrendStrategy(OrderManagedStrategy):
    """均線趨勢 + ATR 移動止損（操作優化）"""
    params = (("ma_period", 20), ("atr_period", 14), ("atr_mult", 2.5))

    def __init__(self):
        super().__init__()
        self.ma = bt.indicators.SMA(period=self.p.ma_period)
        self.atr = bt.indicators.ATR(period=self.p.atr_period)
        self.peak = None

    def next(self):
        if self.order:
            return
        price = self.data.close[0]
        if not self.position:
            if price > self.ma[0]:
                self.peak = price
                self.order = self.buy()
        else:
            self.peak = max(self.peak or price, price)
            stop = self.peak - self.p.atr_mult * self.atr[0]
            if price < stop or price < self.ma[0]:
                self.order = self.sell()
                self.peak = None

