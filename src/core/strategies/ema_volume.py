import backtrader as bt

from src.core.strategies.base import OrderManagedStrategy
from src.core.strategies.registry import register_strategy


@register_strategy("ema_volume", "EMA量價確認策略")
class EMAVolumeStrategy(OrderManagedStrategy):
    """EMA 交叉 + 成交量放大確認"""
    params = (("fast", 12), ("slow", 26), ("vol_ma", 20), ("vol_ratio", 1.2))

    def __init__(self):
        super().__init__()
        self.ema_fast = bt.indicators.EMA(period=self.p.fast)
        self.ema_slow = bt.indicators.EMA(period=self.p.slow)
        self.crossover = bt.indicators.CrossOver(self.ema_fast, self.ema_slow)
        self.vol_ma = bt.indicators.SMA(self.data.volume, period=self.p.vol_ma)

    def next(self):
        if self.order:
            return
        vol_ok = self.data.volume[0] >= self.vol_ma[0] * self.p.vol_ratio
        if self.crossover > 0 and vol_ok and not self.position:
            self.order = self.buy()
        elif self.crossover < 0 and self.position:
            self.order = self.sell()

