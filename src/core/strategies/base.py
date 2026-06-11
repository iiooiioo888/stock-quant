"""策略基類與止損/止盈包裝。"""

import backtrader as bt


class OrderManagedStrategy(bt.Strategy):
    """統一未完成訂單保護；子類在 next() 開頭檢查 self.order。"""

    def __init__(self):
        self.order = None

    def notify_order(self, order):
        if order.status in [
            order.Completed,
            order.Canceled,
            order.Margin,
            order.Rejected,
        ]:
            self.order = None


# ============================================================
# 止損/止盈策略包裝器
# ============================================================


class StrategyWithSLTP(bt.Strategy):
    """
    止損/止盈包裝策略。
    包裝任意策略，監控未實現盈虧，自動觸發止損/止盈。
    注意：此策略只負責監控持倉並在觸發條件時賣出，不開新倉。
    """

    params = (
        ("stop_loss_pct", 0),  # 止損百分比 (0 = 不啟用)
        ("take_profit_pct", 0),  # 止盈百分比 (0 = 不啟用)
        ("trailing_stop_pct", 0),  # 移動止損 (0 = 不啟用)
    )

    def __init__(self):
        self.entry_price = None
        self.max_price = None
        self.sltp_order = None  # 用獨立變量避免與主策略衝突

    def notify_order(self, order):
        # 只追蹤自己發出的訂單
        if order is not self.sltp_order:
            return
        if order.status in [
            order.Completed,
            order.Canceled,
            order.Margin,
            order.Rejected,
        ]:
            if order.status == order.Completed and order.isbuy():
                self.entry_price = order.executed.price
                self.max_price = order.executed.price
            self.sltp_order = None

    def notify_trade(self, trade):
        # 通過 trade 回調獲取真實的入場價
        if trade.isclosed:
            self.entry_price = None
            self.max_price = None
        elif trade.isopen:
            self.entry_price = trade.price
            self.max_price = trade.price

    def next(self):
        if self.sltp_order:
            return

        if not self.position:
            self.entry_price = None
            self.max_price = None
            return

        price = self.data.close[0]
        if self.entry_price is None:
            self.entry_price = price
        if self.max_price is None:
            self.max_price = price

        # 更新最高價
        if price > self.max_price:
            self.max_price = price

        pnl_pct = (price - self.entry_price) / self.entry_price * 100

        # 止損
        if self.p.stop_loss_pct > 0 and pnl_pct <= -self.p.stop_loss_pct:
            self.sltp_order = self.sell()
            return

        # 止盈
        if self.p.take_profit_pct > 0 and pnl_pct >= self.p.take_profit_pct:
            self.sltp_order = self.sell()
            return

        # 移動止損
        if self.p.trailing_stop_pct > 0:
            from_high = (self.max_price - price) / self.max_price * 100
            if from_high >= self.p.trailing_stop_pct:
                self.sltp_order = self.sell()
                return
