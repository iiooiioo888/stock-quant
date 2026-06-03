import backtrader as bt

from src.core.strategies.base import OrderManagedStrategy
from src.core.strategies.registry import register_strategy


@register_strategy("bollinger_squeeze", "布林帶收窄突破策略")
class BollingerSqueezeStrategy(OrderManagedStrategy):
    """布林带收窄策略 — 布林带宽收窄后突破，预期大行情"""
    params = (
        ("period", 20),           # 布林带周期
        ("devfactor", 2.0),       # 标准差倍数
        ("squeeze_threshold", 0.03),  # 带宽收窄阈值（带宽/中轨 < 此值视为收窄）
        ("squeeze_lookback", 5),  # 收窄持续判断回看期
    )

    def __init__(self):
        super().__init__()
        self.boll = bt.indicators.BollingerBands(
            period=self.p.period, devfactor=self.p.devfactor
        )
        self.sma = bt.indicators.SMA(self.data.close, period=self.p.period)
        self.was_squeezed = False

    def next(self):
        if self.order:
            return

        if len(self.data) < self.p.period + self.p.squeeze_lookback:
            return

        price = self.data.close[0]
        top = self.boll.lines.top[0]
        bot = self.boll.lines.bot[0]
        mid = self.sma[0]

        if mid <= 0:
            return

        bandwidth = (top - bot) / mid

        # 判断是否处于收窄状态
        is_squeeze = bandwidth < self.p.squeeze_threshold

        # 检查之前是否收窄过
        if is_squeeze:
            self.was_squeezed = True

        if self.was_squeezed and not is_squeeze:
            # 收窄后扩张 — 突破信号
            if not self.position and price > top:
                # 向上突破
                cash = self.broker.getcash()
                shares = int(cash * 0.95 / price / 100) * 100
                if shares >= 100:
                    self.order = self.buy(size=shares)
                    self.was_squeezed = False
            elif self.position and price < bot:
                # 向下突破（卖出）
                self.order = self.sell()
                self.was_squeezed = False

        # 正常买卖逻辑：非收窄突破时也交易
        if not self.was_squeezed:
            if not self.position and price < bot:
                cash = self.broker.getcash()
                shares = int(cash * 0.95 / price / 100) * 100
                if shares >= 100:
                    self.order = self.buy(size=shares)
            elif self.position and price > top:
                self.order = self.sell()

