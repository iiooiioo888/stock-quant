"""
示例策略 — 均線交叉策略

這是一個簡單的用戶策略示例，演示如何繼承 UserStrategy。
當短期均線上穿長期均線時買入，下穿時賣出。
"""

from src.core.strategy_base import UserStrategy


class MACrossStrategy(UserStrategy):
    """均線交叉策略 — 短期均線上穿買入，下穿賣出"""

    name = "ma_cross"
    description = "均線交叉策略：短期均線上穿長期均線時買入，下穿時賣出"
    params = {
        "fast_period": 5,  # 短期均線週期
        "slow_period": 20,  # 長期均線週期
    }

    def buy_signal(self, df, index):
        """短均線上穿長均線 → 買入"""
        if index < self.slow_period:
            return False

        fast_now = df["close"].iloc[index - self.fast_period + 1 : index + 1].mean()
        slow_now = df["close"].iloc[index - self.slow_period + 1 : index + 1].mean()
        fast_prev = df["close"].iloc[index - self.fast_period : index].mean()
        slow_prev = df["close"].iloc[index - self.slow_period : index].mean()

        # 金叉：短均線從下方穿越長均線
        return fast_prev <= slow_prev and fast_now > slow_now

    def sell_signal(self, df, index):
        """短均線下穿長均線 → 賣出"""
        if index < self.slow_period:
            return False

        fast_now = df["close"].iloc[index - self.fast_period + 1 : index + 1].mean()
        slow_now = df["close"].iloc[index - self.slow_period + 1 : index + 1].mean()
        fast_prev = df["close"].iloc[index - self.fast_period : index].mean()
        slow_prev = df["close"].iloc[index - self.slow_period : index].mean()

        # 死叉：短均線從上方穿越長均線
        return fast_prev >= slow_prev and fast_now < slow_now
