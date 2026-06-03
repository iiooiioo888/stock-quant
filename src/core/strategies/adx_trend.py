import backtrader as bt

from src.core.strategies.base import OrderManagedStrategy
from src.core.strategies.registry import register_strategy


@register_strategy("adx_trend", "ADX趨勢強度策略")
class ADXTrendStrategy(OrderManagedStrategy):
    """ADX 趋势强度策略 — ADX 高于阈值时趋势交易，配合 +DI/-DI 交叉"""
    params = (
        ("adx_period", 14),    # ADX 周期
        ("adx_threshold", 25), # ADX 阈值（高于此值视为强趋势）
        ("di_period", 14),     # DI 周期
    )

    def __init__(self):
        super().__init__()
        self.adx = bt.indicators.ADX(self.data, period=self.p.adx_period)
        self.plus_di = bt.indicators.PlusDI(self.data, period=self.p.di_period)
        self.minus_di = bt.indicators.MinusDI(self.data, period=self.p.di_period)

    def next(self):
        if self.order:
            return

        if len(self.data) < max(self.p.adx_period, self.p.di_period) + 1:
            return

        adx_val = self.adx[0]
        plus_di = self.plus_di[0]
        minus_di = self.minus_di[0]
        plus_di_prev = self.plus_di[-1] if len(self.plus_di) > 1 else plus_di
        minus_di_prev = self.minus_di[-1] if len(self.minus_di) > 1 else minus_di

        if not self.position:
            # 买入：ADX > 阈值（强趋势）且 +DI 上穿 -DI
            if adx_val > self.p.adx_threshold and plus_di_prev <= minus_di_prev and plus_di > minus_di:
                cash = self.broker.getcash()
                shares = int(cash * 0.95 / self.data.close[0] / 100) * 100
                if shares >= 100:
                    self.order = self.buy(size=shares)
        else:
            # 卖出：ADX 回落 或 -DI 上穿 +DI
            if adx_val < self.p.adx_threshold or (minus_di_prev <= plus_di_prev and minus_di > plus_di):
                self.order = self.sell()

