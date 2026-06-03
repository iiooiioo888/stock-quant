import backtrader as bt

from src.core.strategies.base import OrderManagedStrategy
from src.core.strategies.registry import register_strategy


@register_strategy("volume_price", "量價齊升策略")
class VolumePriceStrategy(OrderManagedStrategy):
    """量價策略 — 放量上漲買入，縮量下跌賣出"""
    params = (
        ("price_ma", 20),       # 價格均線週期
        ("volume_ma", 20),      # 成交量均線週期
        ("volume_ratio", 2.0),  # 成交量放大倍數閾值
    )

    def __init__(self):
        super().__init__()
        self.price_sma = bt.indicators.SMA(self.data.close, period=self.p.price_ma)
        self.volume_sma = bt.indicators.SMA(self.data.volume, period=self.p.volume_ma)

    def next(self):
        if self.order:
            return

        price = self.data.close[0]
        vol = self.data.volume[0]
        price_ma = self.price_sma[0]
        vol_ma = self.volume_sma[0]

        if vol_ma <= 0:
            return

        vol_ratio = vol / vol_ma

        if not self.position:
            # 買入：價格站上均線 且 成交量放大（放量上漲）
            if price > price_ma and vol_ratio > self.p.volume_ratio:
                cash = self.broker.getcash()
                shares = int(cash * 0.95 / price / 100) * 100
                if shares >= 100:
                    self.order = self.buy(size=shares)
        else:
            # 賣出：價格跌破均線 或 成交量萎縮（縮量下跌）
            if price < price_ma or vol_ratio < 0.5:
                self.order = self.sell()

