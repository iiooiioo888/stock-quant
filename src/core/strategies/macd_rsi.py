import backtrader as bt

from src.core.strategies.base import OrderManagedStrategy
from src.core.strategies.registry import register_strategy


@register_strategy("macd_rsi", "MACD+RSI過濾策略")
class MacdRsiFilterStrategy(OrderManagedStrategy):
    """MACD 金叉 + RSI 過濾（避免追高）"""

    params = (
        ("macd_fast", 12),
        ("macd_slow", 26),
        ("macd_signal", 9),
        ("rsi_period", 14),
        ("rsi_max", 68),
        ("rsi_min", 35),
    )

    def __init__(self):
        super().__init__()
        self.macd = bt.indicators.MACD(
            period_me1=self.p.macd_fast,
            period_me2=self.p.macd_slow,
            period_signal=self.p.macd_signal,
        )
        self.macd_cross = bt.indicators.CrossOver(self.macd.macd, self.macd.signal)
        self.rsi = bt.indicators.RSI(period=self.p.rsi_period)

    def next(self):
        if self.order:
            return
        rsi = self.rsi[0]
        if (
            self.macd_cross > 0
            and self.p.rsi_min < rsi < self.p.rsi_max
            and not self.position
        ):
            self.order = self.buy()
        elif (self.macd_cross < 0 or rsi >= self.p.rsi_max) and self.position:
            self.order = self.sell()
