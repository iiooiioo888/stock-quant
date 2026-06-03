import backtrader as bt


class _OBV(bt.Indicator):
    """自定義 OBV（On-Balance Volume）指標"""
    lines = ('obv',)
    params = ()

    def __init__(self):
        super().__init__()
        vol = self.data.volume
        close = self.data.close
        prev_close = close(-1)
        direction = bt.If(close > prev_close, vol, bt.If(close < prev_close, -vol, 0))
        self.lines.obv = bt.indicators.SumN(direction, period=len(self.data))

from src.core.strategies.base import OrderManagedStrategy
from src.core.strategies.registry import register_strategy


@register_strategy("obv", "OBV能量潮策略")
class OBVStrategy(OrderManagedStrategy):
    """OBV 能量潮策略 — OBV 趨勢與價格趨勢背離時交易"""
    params = (
        ("obv_ma_period", 20),   # OBV 均線週期
        ("price_ma_period", 20), # 價格均線週期
    )

    def __init__(self):
        super().__init__()
        self.obv = _OBV(self.data)
        self.obv_sma = bt.indicators.SMA(self.obv, period=self.p.obv_ma_period)
        self.price_sma = bt.indicators.SMA(self.data.close, period=self.p.price_ma_period)

    def next(self):
        if self.order:
            return

        if len(self.data) < max(self.p.obv_ma_period, self.p.price_ma_period) + 1:
            return

        price = self.data.close[0]
        price_ma = self.price_sma[0]
        obv_now = self.obv[0]
        obv_ma = self.obv_sma[0]

        if not self.position:
            # 买入：OBV 上穿均线（资金流入）且价格在均线下方（底背离）
            if obv_now > obv_ma and price < price_ma:
                cash = self.broker.getcash()
                shares = int(cash * 0.95 / price / 100) * 100
                if shares >= 100:
                    self.order = self.buy(size=shares)
        else:
            # 卖出：OBV 下穿均线（资金流出）或价格上穿均线
            if obv_now < obv_ma or price > price_ma * 1.05:
                self.order = self.sell()

