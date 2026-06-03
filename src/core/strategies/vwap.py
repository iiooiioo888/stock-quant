
from src.core.strategies.base import OrderManagedStrategy
from src.core.strategies.registry import register_strategy


@register_strategy("vwap", "VWAP成交量加權策略")
class VWAPStrategy(OrderManagedStrategy):
    """VWAP 策略 — 成交量加权平均价格，价格低于 VWAP 买入，高于 VWAP 卖出"""
    params = (
        ("period", 20),         # VWAP 计算周期
        ("deviation_pct", 1.0), # 偏离阈值百分比
    )

    def __init__(self):
        super().__init__()
        self.cum_vol = 0
        self.cum_pv = 0
        self.vwap = None

    def next(self):
        if self.order:
            return

        price = self.data.close[0]
        vol = self.data.volume[0]

        if vol <= 0:
            return

        # 滚动 VWAP：用 SMA 近似
        # 计算典型价格 * 成交量的滚动和 / 成交量的滚动和
        (self.data.high[0] + self.data.low[0] + self.data.close[0]) / 3.0

        # 使用简单方法：累计 VWAP
        if len(self.data) < self.p.period + 1:
            return

        # 计算滚动 VWAP
        cum_tp_vol = 0.0
        cum_vol = 0.0
        for i in range(self.p.period):
            idx = -i
            h = self.data.high[idx]
            low_px = self.data.low[idx]
            c = self.data.close[idx]
            v = self.data.volume[idx]
            tp = (h + low_px + c) / 3.0
            cum_tp_vol += tp * v
            cum_vol += v

        if cum_vol <= 0:
            return

        vwap_val = cum_tp_vol / cum_vol
        deviation = (price - vwap_val) / vwap_val * 100

        if not self.position:
            # 买入：价格低于 VWAP 超过 deviation_pct（折价买入）
            if deviation < -self.p.deviation_pct:
                cash = self.broker.getcash()
                shares = int(cash * 0.95 / price / 100) * 100
                if shares >= 100:
                    self.order = self.buy(size=shares)
        else:
            # 卖出：价格高于 VWAP 超过 deviation_pct（溢价卖出）
            if deviation > self.p.deviation_pct:
                self.order = self.sell()

