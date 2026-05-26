import backtrader as bt

from src.core.strategies.base import OrderManagedStrategy
from src.core.strategies.registry import register_strategy

@register_strategy("mean_reversion", "均值回歸Z-score策略")
class MeanReversionStrategy(OrderManagedStrategy):
    """均值回歸策略 — 基於滾動 Z-score，超賣買入，回歸均值賣出"""
    params = (
        ("period", 20),
        ("entry_zscore", -2.0),  # Z-score 低於此值買入（超賣）
        ("exit_zscore", 0.0),    # Z-score 高於此值賣出（回歸均值）
    )

    def __init__(self):
        super().__init__()
        self.sma = bt.indicators.SMA(self.data.close, period=self.p.period)
        self.std = bt.indicators.StdDev(self.data.close, period=self.p.period)

    def next(self):
        if self.order:
            return

        # 計算 Z-score: (price - MA) / rolling_std
        std_val = self.std[0]
        if std_val <= 0:
            return  # 標準差為零時跳過

        zscore = (self.data.close[0] - self.sma[0]) / std_val

        if not self.position:
            # 買入：Z-score 低於 entry_zscore（價格遠低於均值，超賣）
            if zscore < self.p.entry_zscore:
                cash = self.broker.getcash()
                shares = int(cash * 0.95 / self.data.close[0] / 100) * 100
                if shares >= 100:
                    self.order = self.buy(size=shares)
        else:
            # 賣出：Z-score 高於 exit_zscore（價格回歸或超越均值）
            if zscore > self.p.exit_zscore:
                self.order = self.sell()

