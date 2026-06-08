import backtrader as bt

from src.core.strategies.base import OrderManagedStrategy
from src.core.strategies.registry import register_strategy


@register_strategy("composite", "多策略組合投票策略")
class CompositeStrategy(OrderManagedStrategy):
    """多策略組合信號 — 綜合 dual_ma、macd、rsi、bollinger 四個子策略的買賣信號"""

    params = (
        ("min_agreement", 3),  # 至少 N 個子策略同意才執行
        # 子策略參數
        ("ma_fast", 5),
        ("ma_slow", 20),
        ("macd_fast", 12),
        ("macd_slow", 26),
        ("macd_signal", 9),
        ("rsi_period", 14),
        ("rsi_overbought", 70),
        ("rsi_oversold", 30),
        ("boll_period", 20),
        ("boll_dev", 2.0),
    )

    def __init__(self):
        super().__init__()
        # === 雙均線 ===
        self.ma_fast = bt.indicators.SMA(self.data.close, period=self.p.ma_fast)
        self.ma_slow = bt.indicators.SMA(self.data.close, period=self.p.ma_slow)
        self.ma_crossover = bt.indicators.CrossOver(self.ma_fast, self.ma_slow)

        # === MACD ===
        self.macd = bt.indicators.MACD(
            period_me1=self.p.macd_fast,
            period_me2=self.p.macd_slow,
            period_signal=self.p.macd_signal,
        )
        self.macd_crossover = bt.indicators.CrossOver(self.macd.macd, self.macd.signal)

        # === RSI ===
        self.rsi = bt.indicators.RSI(period=self.p.rsi_period)

        # === 布林帶 ===
        self.boll = bt.indicators.BollingerBands(
            period=self.p.boll_period, devfactor=self.p.boll_dev
        )

    def _compute_sub_signals(self):
        """計算四個子策略的信號：返回 (buy_count, sell_count)"""
        buy_count = 0
        sell_count = 0

        # 1. 雙均線：金叉買入，死叉賣出
        if self.ma_crossover > 0:
            buy_count += 1
        elif self.ma_crossover < 0:
            sell_count += 1

        # 2. MACD：金叉買入，死叉賣出
        if self.macd_crossover > 0:
            buy_count += 1
        elif self.macd_crossover < 0:
            sell_count += 1

        # 3. RSI：超賣買入，超買賣出
        rsi_val = self.rsi[0]
        if rsi_val < self.p.rsi_oversold:
            buy_count += 1
        elif rsi_val > self.p.rsi_overbought:
            sell_count += 1

        # 4. 布林帶：觸及下軌買入，觸及上軌賣出
        if self.data.close[0] < self.boll.lines.bot:
            buy_count += 1
        elif self.data.close[0] > self.boll.lines.top:
            sell_count += 1

        return buy_count, sell_count

    def next(self):
        if self.order:
            return

        buy_count, sell_count = self._compute_sub_signals()

        if not self.position:
            # 買入：至少 min_agreement 個子策略同意買入
            if buy_count >= self.p.min_agreement:
                cash = self.broker.getcash()
                shares = int(cash * 0.95 / self.data.close[0] / 100) * 100
                if shares >= 100:
                    self.order = self.buy(size=shares)
        else:
            # 賣出：至少 min_agreement 個子策略同意賣出
            if sell_count >= self.p.min_agreement:
                self.order = self.sell()
