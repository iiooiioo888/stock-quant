"""
策略開發框架 — 用戶策略基類 + 加載器 + 模板生成器 + Backtrader 轉換

用戶只需繼承 UserStrategy 並實現 buy_signal / sell_signal 即可。
系統自動發現、加載、沙箱執行，並可無縫接入 Backtrader 回測。
"""
import importlib.util
import os
import re
from pathlib import Path

import backtrader as bt
import pandas as pd

from src.core.strategy_sandbox import (
    validate_strategy_file,
    validate_strategy_source,
)
from src.utils.logger import logger


def _check_strategy_safety(filepath: str) -> bool:
    """策略沙箱校驗（見 strategy_sandbox.py）。"""
    result = validate_strategy_file(filepath)
    if not result.ok:
        logger.warning(f"策略安全檢查未通過: {filepath} — {result.error}")
    return result.ok


# ============================================================
# 策略基類
# ============================================================

class UserStrategy:
    """
    用戶策略基類。

    繼承此類並實現 buy_signal / sell_signal 即可。
    示例：
        class MyStrategy(UserStrategy):
            name = "my_strategy"
            description = "我的自定義策略"
            params = {"period": 20, "threshold": 0.5}

            def buy_signal(self, df, index):
                return df["close"].iloc[index] > df["close"].iloc[index - self.period]

            def sell_signal(self, df, index):
                return df["close"].iloc[index] < df["close"].iloc[index - self.period]
    """

    name: str = "my_strategy"
    description: str = ""
    params: dict = {}

    def __init__(self, **kwargs):
        """初始化策略參數 — 將 params 中的默認值設為實例屬性"""
        for k, v in self.params.items():
            setattr(self, k, kwargs.get(k, v))
        # 保存額外參數
        self._extra_params = {k: v for k, v in kwargs.items() if k not in self.params}

    def buy_signal(self, df: pd.DataFrame, index: int) -> bool:
        """
        買入信號。

        參數:
            df: 包含 OHLCV 數據的 DataFrame
            index: 當前 K 線的索引位置
        返回:
            True 表示發出買入信號
        """
        raise NotImplementedError("請實現 buy_signal 方法")

    def sell_signal(self, df: pd.DataFrame, index: int) -> bool:
        """
        賣出信號。

        參數:
            df: 包含 OHLCV 數據的 DataFrame
            index: 當前 K 線的索引位置
        返回:
            True 表示發出賣出信號
        """
        raise NotImplementedError("請實現 sell_signal 方法")

    def to_backtrader(self) -> type:
        """
        將用戶策略轉換為 Backtrader 策略類。

        自動生成一個 bt.Strategy 子類，在每個 bar 上調用 buy_signal / sell_signal。
        """
        user_strategy_instance = self

        class _UserBtStrategy(bt.Strategy):
            """自動生成的 Backtrader 策略包裝器"""

            def __init__(self_):
                self_.order = None
                # 構建 DataFrame 供 buy_signal/sell_signal 使用
                self_._df_cache = None

            def _build_df(self_) -> pd.DataFrame:
                """從 Backtrader 數據源構建 pandas DataFrame"""
                if self_._df_cache is not None:
                    return self_._df_cache

                data = self_.datas[0]
                dates = []
                opens = []
                highs = []
                lows = []
                closes = []
                volumes = []

                for i in range(len(data)):
                    dt = data.num2date(data.datetime[i])
                    dates.append(dt)
                    opens.append(data.open[i])
                    highs.append(data.high[i])
                    lows.append(data.low[i])
                    closes.append(data.close[i])
                    volumes.append(data.volume[i])

                self_._df_cache = pd.DataFrame({
                    "date": dates,
                    "open": opens,
                    "high": highs,
                    "low": lows,
                    "close": closes,
                    "volume": volumes,
                })
                return self_._df_cache

            def next(self_):
                if self_.order:
                    return

                df = self_._build_df()
                # 當前 bar 的索引（0-based，對應 Backtrader 已處理的數據長度）
                idx = len(self_.datas[0]) - 1

                if idx < 0:
                    return

                try:
                    # 調用用戶的買入信號
                    if user_strategy_instance.buy_signal(df, idx) and not self_.position:
                        self_.order = self_.buy()
                    # 調用用戶的賣出信號
                    elif user_strategy_instance.sell_signal(df, idx) and self_.position:
                        self_.order = self_.sell()
                except Exception as e:
                    logger.debug(f"用戶策略信號異常: {e}")

            def notify_order(self_, order):
                if order.status in [order.Completed, order.Canceled, order.Margin, order.Rejected]:
                    self_.order = None

        # 設置策略名稱
        _UserBtStrategy.__name__ = f"UserBt_{user_strategy_instance.name}"
        _UserBtStrategy.__qualname__ = _UserBtStrategy.__name__
        return _UserBtStrategy


# ============================================================
# 策略加載器
# ============================================================

def load_user_strategy(filepath: str, source: str | None = None) -> list[type]:
    """
    從 .py 文件加載 UserStrategy 子類。

    步驟：
      1. 安全檢查（AST 解析，禁止危險模塊）
      2. 動態導入模塊
      3. 找出所有 UserStrategy 子類
    返回:
        UserStrategy 子類列表
    """
    filepath = str(filepath)
    if not filepath.endswith(".py"):
        logger.warning(f"策略文件必須是 .py 格式: {filepath}")
        return []

    if not os.path.isfile(filepath):
        logger.warning(f"策略文件不存在: {filepath}")
        return []

    if source is not None:
        check = validate_strategy_source(source)
        if not check.ok:
            logger.warning(f"策略安全檢查未通過: {filepath} — {check.error}")
            return []
    elif not _check_strategy_safety(filepath):
        return []

    try:
        spec = importlib.util.spec_from_file_location("_user_strategy_module", filepath)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except Exception as e:
        logger.error(f"加載策略文件失敗: {filepath} — {e}")
        return []

    strategies = []
    for attr_name in dir(module):
        attr = getattr(module, attr_name)
        if (
            isinstance(attr, type)
            and issubclass(attr, UserStrategy)
            and attr is not UserStrategy
        ):
            strategies.append(attr)

    if not strategies:
        logger.warning(f"策略文件中未找到 UserStrategy 子類: {filepath}")
    else:
        logger.info(f"從 {filepath} 加載了 {len(strategies)} 個策略: {[s.name for s in strategies]}")

    return strategies


def list_user_strategies(directory: str = None) -> list[dict]:
    """
    掃描目錄中的所有 .py 文件，返回找到的用戶策略列表。

    參數:
        directory: 策略目錄路徑，默認為項目根目錄下的 strategies/
    返回:
        [{"name": ..., "description": ..., "class": ..., "filepath": ..., "params": {...}}, ...]
    """
    if directory is None:
        directory = str(Path(__file__).resolve().parent.parent.parent / "strategies")

    directory = str(directory)
    if not os.path.isdir(directory):
        logger.warning(f"策略目錄不存在: {directory}")
        return []

    results = []
    for fname in sorted(os.listdir(directory)):
        if not fname.endswith(".py") or fname.startswith("_"):
            continue
        filepath = os.path.join(directory, fname)
        strategy_classes = load_user_strategy(filepath)
        for cls in strategy_classes:
            results.append({
                "name": getattr(cls, "name", cls.__name__),
                "description": getattr(cls, "description", ""),
                "class": cls,
                "filepath": filepath,
                "params": getattr(cls, "params", {}),
            })

    return results


def get_all_strategies() -> dict:
    """
    獲取所有策略（內置 + 用戶自定義）。

    返回:
        {"strategy_name": {"source": "builtin"|"user", "class": ..., "description": ..., "params": {...}}}
    """
    from src.core.backtest import STRATEGIES

    all_strategies = {}

    # 內置策略
    for name, cls in STRATEGIES.items():
        all_strategies[name] = {
            "source": "builtin",
            "class": cls,
            "description": cls.__doc__ or "",
            "params": {},
        }

    # 用戶策略
    user_strategies = list_user_strategies()
    for s in user_strategies:
        all_strategies[s["name"]] = {
            "source": "user",
            "class": s["class"],
            "description": s["description"],
            "params": s["params"],
            "filepath": s.get("filepath", ""),
        }

    return all_strategies


# ============================================================
# 策略模板生成器
# ============================================================

def create_strategy_template(name: str, filepath: str = None) -> str:
    """
    生成用戶策略模板文件。

    參數:
        name: 策略名稱（英文，用於類名和文件名）
        filepath: 輸出路徑，默認為 strategies/{name}_strategy.py
    返回:
        生成的文件路徑
    """
    # 清理名稱
    safe_name = re.sub(r"[^a-zA-Z0-9_]", "_", name.lower().strip("_"))
    if not safe_name:
        safe_name = "my_strategy"

    if filepath is None:
        strategies_dir = Path(__file__).resolve().parent.parent.parent / "strategies"
        strategies_dir.mkdir(exist_ok=True)
        filepath = str(strategies_dir / f"{safe_name}_strategy.py")

    # 類名：PascalCase
    class_name = "".join(word.capitalize() for word in safe_name.split("_"))

    template = f'''"""
用戶策略模板 — {name}

使用方法：
  1. 實現 buy_signal() 和 sell_signal() 的邏輯
  2. 修改 params 中的參數及其默認值
  3. 在 description 中描述你的策略
  4. 運行: python main.py strategy list  查看已加載策略
  5. 回測: python main.py backtest 600519 {safe_name}
"""
from src.core.strategy_base import UserStrategy


class {class_name}Strategy(UserStrategy):
    """在此描述你的策略邏輯"""

    name = "{safe_name}"
    description = "在此描述你的策略"
    params = {{"period": 20, "threshold": 0.5}}

    def buy_signal(self, df, index):
        """
        買入信號邏輯。

        參數:
            df: DataFrame，包含 date/open/high/low/close/volume 列
            index: 當前 K 線索引（0-based）
        返回:
            True 表示發出買入信號
        """
        # 在此實現買入邏輯
        # 示例：價格突破 N 日均線
        # if index < self.period:
        #     return False
        # ma = df["close"].iloc[index - self.period:index].mean()
        # return df["close"].iloc[index] > ma
        return False

    def sell_signal(self, df, index):
        """
        賣出信號邏輯。

        參數:
            df: DataFrame，包含 date/open/high/low/close/volume 列
            index: 當前 K 線索引（0-based）
        返回:
            True 表示發出賣出信號
        """
        # 在此實現賣出邏輯
        # 示例：價格跌破 N 日均線
        # if index < self.period:
        #     return False
        # ma = df["close"].iloc[index - self.period:index].mean()
        # return df["close"].iloc[index] < ma
        return False
'''

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(template)

    logger.info(f"策略模板已生成: {filepath}")
    return filepath


# ============================================================
# 用戶策略快速回測（不經過 Backtrader，純 pandas 計算）
# ============================================================

def quick_backtest_user_strategy(strategy_instance: UserStrategy, code: str) -> dict:
    """
    使用純 pandas 對用戶策略進行快速回測。

    適用於簡單的信號邏輯驗證，不依賴 Backtrader。
    """
    import numpy as np

    from src.config import settings
    from src.core.db import load_daily_kline

    df = load_daily_kline(code)
    if df.empty:
        raise ValueError(f"股票 {code} 無歷史數據")

    df = df.reset_index(drop=True)
    n = len(df)
    if n < 10:
        raise ValueError(f"數據量不足: {n} 條")

    cash = settings.backtest_cash
    initial_cash = cash
    position = 0
    commission = settings.backtest_commission
    trades = []
    nav = []
    dates = []

    for i in range(n):
        price = df["close"].iloc[i]
        date_str = str(df["date"].iloc[i])

        try:
            buy = strategy_instance.buy_signal(df, i)
            sell = strategy_instance.sell_signal(df, i)
        except Exception:
            buy = sell = False

        # 買入
        if buy and position == 0 and cash > 0:
            shares = int(cash * 0.95 / price / 100) * 100
            if shares >= 100:
                cost = shares * price * (1 + commission)
                cash -= cost
                position = shares
                trades.append({"date": date_str, "type": "buy", "price": price, "shares": shares})

        # 賣出
        elif sell and position > 0:
            revenue = position * price * (1 - commission)
            cash += revenue
            trades.append({"date": date_str, "type": "sell", "price": price, "shares": position})
            position = 0

        # 記錄淨值
        total_value = cash + position * price
        nav.append(total_value)
        dates.append(date_str)

    # 最終強制平倉
    if position > 0:
        last_price = df["close"].iloc[-1]
        revenue = position * last_price * (1 - commission)
        cash += revenue
        trades.append({"date": str(df["date"].iloc[-1]), "type": "sell", "price": last_price, "shares": position})
        position = 0
        nav[-1] = cash

    final_value = cash
    total_return_pct = (final_value - initial_cash) / initial_cash * 100

    # 計算日收益率
    nav_arr = np.array(nav)
    daily_returns = np.diff(nav_arr) / nav_arr[:-1] if len(nav_arr) > 1 else np.array([])

    # 夏普比率
    if len(daily_returns) > 1:
        sharpe = (np.mean(daily_returns) - 0.03 / 252) / np.std(daily_returns) * np.sqrt(252) if np.std(daily_returns) > 0 else 0
    else:
        sharpe = 0

    # 最大回撤
    peak = np.maximum.accumulate(nav_arr)
    drawdown = (peak - nav_arr) / peak
    max_dd = float(np.max(drawdown)) * 100 if len(drawdown) > 0 else 0

    # 勝率
    buy_trades = [t for t in trades if t["type"] == "buy"]
    sell_trades = [t for t in trades if t["type"] == "sell"]
    pairs = min(len(buy_trades), len(sell_trades))
    wins = 0
    for j in range(pairs):
        if sell_trades[j]["price"] > buy_trades[j]["price"]:
            wins += 1
    win_rate = (wins / pairs * 100) if pairs > 0 else 0

    return {
        "code": code,
        "strategy": strategy_instance.name,
        "initial_cash": initial_cash,
        "final_value": round(final_value, 2),
        "total_return_pct": round(total_return_pct, 4),
        "sharpe_ratio": round(sharpe, 4),
        "max_drawdown_pct": round(max_dd, 4),
        "total_trades": pairs,
        "win_rate_pct": round(win_rate, 2),
        "nav": [round(v, 2) for v in nav],
        "dates": dates,
        "trade_details": [
            {
                "buy_date": buy_trades[j]["date"],
                "buy_price": buy_trades[j]["price"],
                "sell_date": sell_trades[j]["date"],
                "sell_price": sell_trades[j]["price"],
                "size": buy_trades[j]["shares"],
                "pnl": round((sell_trades[j]["price"] - buy_trades[j]["price"]) * buy_trades[j]["shares"], 2),
                "return_pct": round((sell_trades[j]["price"] / buy_trades[j]["price"] - 1) * 100, 2),
            }
            for j in range(pairs)
        ],
    }
