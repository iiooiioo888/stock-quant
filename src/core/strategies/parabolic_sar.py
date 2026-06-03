
from src.core.strategies.base import OrderManagedStrategy
from src.core.strategies.registry import register_strategy


@register_strategy("parabolic_sar", "拋物線SAR策略")
class ParabolicSARStrategy(OrderManagedStrategy):
    """抛物线 SAR 策略 — 趋势跟踪，SAR 翻转时交易"""
    params = (
        ("af_start", 0.02),   # 加速因子初始值
        ("af_step", 0.02),    # 加速因子步长
        ("af_max", 0.20),     # 加速因子最大值
    )

    def __init__(self):
        super().__init__()
        self.sar = None
        self.ep = None       # 极值点
        self.af = self.p.af_start
        self.is_long = True  # 当前方向

    def next(self):
        if self.order:
            return

        if len(self.data) < 3:
            return

        high = self.data.high[0]
        low = self.data.low[0]
        self.data.high[-1]
        self.data.low[-1]

        # 初始化
        if self.sar is None:
            self.sar = low
            self.ep = high
            self.is_long = True
            return

        prev_sar = self.sar

        if self.is_long:
            # 上升趋势
            self.sar = prev_sar + self.af * (self.ep - prev_sar)

            # SAR 不能高于前两根K线的最低点
            if len(self.data) >= 2:
                self.sar = min(self.sar, self.data.low[-1], self.data.low[-2] if len(self.data) >= 3 else self.data.low[-1])

            if low < self.sar:
                # 翻转为下降趋势
                self.is_long = False
                self.sar = self.ep
                self.ep = low
                self.af = self.p.af_start

                # 卖出
                if self.position:
                    self.order = self.sell()
            else:
                if high > self.ep:
                    self.ep = high
                    self.af = min(self.af + self.p.af_step, self.p.af_max)
        else:
            # 下降趋势
            self.sar = prev_sar + self.af * (self.ep - prev_sar)

            # SAR 不能低于前两根K线的最高点
            if len(self.data) >= 2:
                self.sar = max(self.sar, self.data.high[-1], self.data.high[-2] if len(self.data) >= 3 else self.data.high[-1])

            if high > self.sar:
                # 翻转为上升趋势
                self.is_long = True
                self.sar = self.ep
                self.ep = high
                self.af = self.p.af_start

                # 买入
                if not self.position:
                    cash = self.broker.getcash()
                    shares = int(cash * 0.95 / self.data.close[0] / 100) * 100
                    if shares >= 100:
                        self.order = self.buy(size=shares)
            else:
                if low < self.ep:
                    self.ep = low
                    self.af = min(self.af + self.p.af_step, self.p.af_max)

