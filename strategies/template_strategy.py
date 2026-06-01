"""
策略開發模板 — 新手入門範例

使用方式：
1. 複製本文件並重命名，例如 my_strategy.py
2. 修改類名和策略邏輯
3. 運行測試: python -m pytest tests/test_strategies.py -v
4. 部署後自動被系統發現（無需重啟，支持熱加載）

策略架構說明：
- 繼承 bt.Strategy（Backtrader 策略基類）
- 使用 self.data.close, self.data.open 等訪問 K 線數據
- 使用 self.buy() / self.sell() 發出交易信號
- 使用 self.position 檢查當前持倉狀態
"""
import backtrader as bt


class TemplateStrategy(bt.Strategy):
    """
    策略模板 — 雙均線交叉（Golden Cross / Death Cross）
    
    邏輯：
    - 快線（短期均線）上穿慢線（長期均線）→ 買入
    - 快線下穿慢線 → 賣出
    
    參數：
    - fast: 快線週期（默認 5）
    - slow: 慢線週期（默認 20）
    """
    
    # 策略參數（可在回測時動態調整）
    params = (
        ("fast", 5),    # 快線週期
        ("slow", 20),   # 慢線週期
    )
    
    def __init__(self):
        """初始化指標（只計算一次，效率高）"""
        # 計算移動平均線
        self.fast_ma = bt.indicators.SMA(
            self.data.close, period=self.params.fast
        )
        self.slow_ma = bt.indicators.SMA(
            self.data.close, period=self.params.slow
        )
        
        # 計算交叉信號（1=金叉, -1=死叉, 0=無信號）
        self.crossover = bt.indicators.CrossOver(
            self.fast_ma, self.slow_ma
        )
        
        # 可選：其他輔助指標
        self.atr = bt.indicators.ATR(self.data, period=14)
        self.rsi = bt.indicators.RSI(self.data.close, period=14)
    
    def next(self):
        """
        每根 K 線調用一次（核心邏輯）
        
        注意：
        - self.data.close[0] = 當前收盤價
        - self.data.close[-1] = 上一根收盤價
        - self.position.size = 當前持倉數量（0=空倉）
        """
        if not self.position:
            # 空倉：檢查買入條件
            if self.crossover > 0:
                # 金叉 + RSI 未超買 → 買入
                if self.rsi[0] < 70:
                    self.buy()
        else:
            # 持倉：檢查賣出條件
            if self.crossover < 0:
                # 死叉 → 賣出
                self.sell()
    
    def notify_order(self, order):
        """訂單狀態通知（可選，用於日誌記錄）"""
        if order.status in [order.Completed]:
            if order.isbuy():
                self.log(f"買入: 價格={order.executed.price:.2f}, "
                         f"數量={order.executed.size}, "
                         f"手續費={order.executed.comm:.2f}")
            elif order.issell():
                self.log(f"賣出: 價格={order.executed.price:.2f}, "
                         f"數量={order.executed.size}, "
                         f"手續費={order.executed.comm:.2f}")
    
    def notify_trade(self, trade):
        """交易完成通知（可選）"""
        if trade.isclosed:
            self.log(f"交易完成: 盈虧={trade.pnl:.2f}, "
                     f"淨盈虧={trade.pnlcomm:.2f}")
    
    def log(self, txt, dt=None):
        """日誌輔助方法"""
        dt = dt or self.datas[0].datetime.date(0)
        print(f"[{dt}] {txt}")


# ============================================================
# 更多策略範例
# ============================================================

class RSIOversoldStrategy(bt.Strategy):
    """
    RSI 超賣反彈策略
    
    邏輯：
    - RSI < 30（超賣）→ 買入
    - RSI > 70（超買）→ 賣出
    
    適用場景：震盪行情
    """
    
    params = (
        ("period", 14),
        ("oversold", 30),
        ("overbought", 70),
    )
    
    def __init__(self):
        self.rsi = bt.indicators.RSI(
            self.data.close, period=self.params.period
        )
    
    def next(self):
        if not self.position:
            if self.rsi[0] < self.params.oversold:
                self.buy()
        else:
            if self.rsi[0] > self.params.overbought:
                self.sell()


class BollingerBandStrategy(bt.Strategy):
    """
    布林帶均值回歸策略
    
    邏輯：
    - 價格觸及下軌 → 買入（超跌反彈）
    - 價格觸及上軌 → 賣出（超漲回落）
    - 價格回到中軌 → 平倉（可選）
    
    適用場景：區間震盪
    """
    
    params = (
        ("period", 20),
        ("devfactor", 2.0),
    )
    
    def __init__(self):
        self.boll = bt.indicators.BollingerBands(
            self.data.close,
            period=self.params.period,
            devfactor=self.params.devfactor,
        )
    
    def next(self):
        if not self.position:
            # 觸及下軌 → 買入
            if self.data.close[0] < self.boll.lines.bot[0]:
                self.buy()
        else:
            # 觸及上軌 → 賣出
            if self.data.close[0] > self.boll.lines.top[0]:
                self.sell()


# ============================================================
# 策略註冊（供系統自動發現）
# ============================================================

# 策略元數據（用於策略列表和參數配置頁面）
STRATEGY_META = {
    "template": {
        "class": TemplateStrategy,
        "label": "雙均線交叉（模板）",
        "category": "trend",
        "description": "快慢均線交叉策略，金叉買入死叉賣出。適合作為策略開發入門模板。",
        "default_params": {"fast": 5, "slow": 20},
        "param_ranges": {
            "fast": (3, 20, 1),   # (最小值, 最大值, 步長)
            "slow": (10, 60, 5),
        },
    },
    "rsi_oversold": {
        "class": RSIOversoldStrategy,
        "label": "RSI 超賣反彈",
        "category": "oscillator",
        "description": "RSI 低於 30 買入，高於 70 賣出。適合震盪行情。",
        "default_params": {"period": 14, "oversold": 30, "overbought": 70},
        "param_ranges": {
            "period": (7, 28, 1),
            "oversold": (20, 40, 5),
            "overbought": (60, 80, 5),
        },
    },
    "bollinger": {
        "class": BollingerBandStrategy,
        "label": "布林帶均值回歸",
        "category": "mean_reversion",
        "description": "觸及布林帶下軌買入，上軌賣出。適合區間震盪。",
        "default_params": {"period": 20, "devfactor": 2.0},
        "param_ranges": {
            "period": (10, 40, 5),
            "devfactor": (1.0, 3.0, 0.5),
        },
    },
}