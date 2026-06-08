"""
回測引擎 — 基於 Backtrader，支持多種內置策略
包含：滑點模擬、漲跌停限制、T+1 限制、權益曲線分析
"""

from datetime import datetime

import backtrader as bt
import numpy as np
import pandas as pd

from src.config import settings
from src.core.db import load_daily_kline
from src.utils.logger import logger

# ============================================================
# A 股精確佣金模型
# ============================================================


class AStockCommission(bt.CommInfoBase):
    """
    A 股交易成本模型：
      - 佣金：雙邊收取，默認 0.025%，最低 5 元
      - 印花稅：僅賣出收取，2023 年後 0.05%
      - 過戶費：雙邊收取，0.001%
    """

    params = (
        ("commission", 0.00025),  # 佣金費率（雙邊）
        ("min_commission", 5.0),  # 最低佣金（元）
        ("stamp_tax", 0.0005),  # 印花稅費率（僅賣出）
        ("transfer_fee", 0.00001),  # 過戶費費率（雙邊）
        ("stocklike", True),
        ("commtype", bt.CommInfoBase.COMM_PERC),
    )

    def _getcommission(self, size, price, pseudoexec):
        """計算單筆交易總成本（佣金 + 印花稅 + 過戶費）"""
        turnover = abs(size) * price

        # 佣金：按費率計算，最低 5 元
        comm = max(turnover * self.p.commission, self.p.min_commission)

        # 印花稅：僅賣出
        if size < 0:
            comm += turnover * self.p.stamp_tax

        # 過戶費：雙邊
        comm += turnover * self.p.transfer_fee

        return comm


# ============================================================
# A股漲跌停限制分析器
# ============================================================


class LimitFilter(bt.Analyzer):
    """
    漲跌停過濾分析器。
    A股規則：
      - 主板（600xxx/601xxx/603xxx/000xxx/001xxx/002xxx）：±10%
      - 創業板（300xxx）：±20%
      - 科創板（688xxx）：±20%
    當股票漲停時禁止買入，跌停時禁止賣出。
    """

    def __init__(self):
        self.blocked_buys = 0  # 被阻止的買入次數
        self.blocked_sells = 0  # 被阻止的賣出次數
        self._limit_pct = None  # 漲跌停幅度（根據代碼前綴動態判斷）

    def _get_limit_pct(self, code: str) -> float:
        """根據股票代碼前綴獲取漲跌停幅度"""
        if self._limit_pct is not None:
            return self._limit_pct

        code_str = str(code)
        # 科創板 688xxx 或 創業板 300xxx → ±20%
        if code_str.startswith("688") or code_str.startswith("300"):
            self._limit_pct = 0.20
        else:
            # 主板 → ±10%
            self._limit_pct = 0.10

        return self._limit_pct

    def start(self):
        """初始化時從策略的數據源獲取代碼"""
        # 嘗試從 cerebro 或 data 中獲取股票代碼
        self._code = getattr(self.strategy, "_stock_code", "")
        if not self._code:
            # 從 data name 推斷
            data_name = self.datas[0]._name if self.datas else ""
            self._code = data_name

    def _is_limit_up(self) -> bool:
        """判斷當前是否漲停"""
        if len(self.datas[0]) < 2:
            return False
        limit_pct = self._get_limit_pct(self._code)
        prev_close = self.datas[0].close[-1]
        curr_close = self.datas[0].close[0]
        if prev_close <= 0:
            return False
        change = (curr_close - prev_close) / prev_close
        return change >= limit_pct - 0.001  # 容差 0.1%

    def _is_limit_down(self) -> bool:
        """判斷當前是否跌停"""
        if len(self.datas[0]) < 2:
            return False
        limit_pct = self._get_limit_pct(self._code)
        prev_close = self.datas[0].close[-1]
        curr_close = self.datas[0].close[0]
        if prev_close <= 0:
            return False
        change = (curr_close - prev_close) / prev_close
        return change <= -(limit_pct - 0.001)

    def notify_order(self, order):
        """攔截訂單：漲停時拒絕買入，跌停時拒絕賣出"""
        if order.status != order.Submitted:
            return

        if order.isbuy() and self._is_limit_up():
            # 漲停時取消買入訂單
            self.strategy.broker.cancel(order)
            self.blocked_buys += 1
            return

        if order.issell() and self._is_limit_down():
            # 跌停時取消賣出訂單
            self.strategy.broker.cancel(order)
            self.blocked_sells += 1
            return

    def get_analysis(self):
        return {
            "blocked_buys": self.blocked_buys,
            "blocked_sells": self.blocked_sells,
            "limit_pct": self._limit_pct or 0.10,
        }


# ============================================================
# T+1 限制分析器
# ============================================================


class T1Filter(bt.Analyzer):
    """
    T+1 限制分析器。
    A股規則：當天買入的股票，次日才能賣出。
    追蹤每個持倉的買入日期，阻止同日賣出。
    """

    def __init__(self):
        self._buy_dates = {}  # {data_name: 買入日期}
        self.blocked_sells = 0  # 被阻止的賣出次數

    def notify_trade(self, trade):
        """通過 trade 回調追蹤持倉買入日期"""
        data_name = trade.data._name or "default"
        if trade.isopen:
            dt = self.datas[0].num2date(trade.dtopen)
            dt_date = dt.date() if hasattr(dt, "date") else dt
            self._buy_dates[data_name] = dt_date

    def _check_sell_allowed(self, data) -> bool:
        """檢查是否允許賣出（T+1 限制）"""
        data_name = data._name or "default"
        buy_date = self._buy_dates.get(data_name)
        if buy_date is None:
            return True  # 無記錄則允許賣出

        current_dt = self.datas[0].num2date(self.datas[0].datetime[0])
        current_date = current_dt.date() if hasattr(current_dt, "date") else current_dt

        # 賣出日期必須晚於買入日期
        if current_date <= buy_date:
            return False
        return True

    def notify_order(self, order):
        """攔截賣出訂單（T+1 限制）並記錄已完成的買入日期"""
        # 記錄已完成的買入/賣出
        if order.status == order.Completed:
            dt = self.datas[0].num2date(order.executed.dt)
            dt_date = dt.date() if hasattr(dt, "date") else dt
            data_name = order.data._name or "default"

            if order.isbuy():
                self._buy_dates[data_name] = dt_date
            elif order.issell():
                if data_name in self._buy_dates:
                    del self._buy_dates[data_name]

        # 攔截提交中的賣出訂單：T+1 限制
        if order.status == order.Submitted:
            if order.issell() and not self._check_sell_allowed(order.data):
                self.strategy.broker.cancel(order)
                self.blocked_sells += 1
                return

    def get_analysis(self):
        return {
            "blocked_sells": self.blocked_sells,
            "tracked_positions": len(self._buy_dates),
        }


# ============================================================
# 權益曲線分析
# ============================================================


def analyze_equity_curve(nav: list, dates: list, daily_returns: list) -> dict:
    """
    權益曲線深度分析。

    返回：
      - underwater_periods: 水下期間（淨值低於歷史最高點的時段）
      - recovery_periods: 回撤恢復期（從最大回撤到恢復的天數）
      - rolling_1y_returns: 滾動一年收益率
      - drawdown_durations: 回撤持續時間分佈
    """
    if not nav or len(nav) < 2:
        return {
            "underwater_periods": [],
            "recovery_periods": [],
            "rolling_1y_returns": [],
            "drawdown_durations": [],
            "max_underwater_days": 0,
            "avg_underwater_days": 0,
            "underwater_pct": 0,
        }

    nav_arr = np.array(nav, dtype=float)

    # === 計算回撤序列 ===
    peak = np.maximum.accumulate(nav_arr)
    drawdown = (peak - nav_arr) / peak  # 回撤比例（正值）

    # === 水下期間分析 ===
    underwater_periods = []
    in_underwater = False
    uw_start = 0

    for i in range(len(nav_arr)):
        if drawdown[i] > 0.0001:  # 淨值低於高點
            if not in_underwater:
                in_underwater = True
                uw_start = i
        else:
            if in_underwater:
                underwater_periods.append(
                    {
                        "start_idx": uw_start,
                        "end_idx": i,
                        "start_date": (
                            str(dates[uw_start]) if uw_start < len(dates) else ""
                        ),
                        "end_date": str(dates[i]) if i < len(dates) else "",
                        "duration_days": i - uw_start,
                        "max_drawdown_pct": round(
                            float(np.max(drawdown[uw_start:i])) * 100, 4
                        ),
                    }
                )
                in_underwater = False

    # 如果結束時仍在水下
    if in_underwater:
        underwater_periods.append(
            {
                "start_idx": uw_start,
                "end_idx": len(nav_arr) - 1,
                "start_date": str(dates[uw_start]) if uw_start < len(dates) else "",
                "end_date": str(dates[-1]) if len(dates) > 0 else "",
                "duration_days": len(nav_arr) - 1 - uw_start,
                "max_drawdown_pct": round(float(np.max(drawdown[uw_start:])) * 100, 4),
            }
        )

    # === 回撤恢復期 ===
    recovery_periods = []
    # 找到所有回撤超過 5% 的事件
    peak_val = nav_arr[0]
    peak_idx = 0
    dd_start_idx = None

    for i in range(len(nav_arr)):
        if nav_arr[i] > peak_val:
            peak_val = nav_arr[i]
            peak_idx = i
            dd_start_idx = None
        dd = (peak_val - nav_arr[i]) / peak_val
        if dd > 0.05 and dd_start_idx is None:
            dd_start_idx = peak_idx
            dd_trough_val = dd
            dd_trough_idx = i
        elif dd_start_idx is not None:
            if dd > dd_trough_val:
                dd_trough_val = dd
                dd_trough_idx = i
            if nav_arr[i] >= peak_val:
                # 恢復到前高
                recovery_periods.append(
                    {
                        "drawdown_pct": round(dd_trough_val * 100, 4),
                        "trough_date": (
                            str(dates[dd_trough_idx])
                            if dd_trough_idx < len(dates)
                            else ""
                        ),
                        "recovery_date": str(dates[i]) if i < len(dates) else "",
                        "recovery_days": i - dd_trough_idx,
                        "total_days": i - dd_start_idx,
                    }
                )
                dd_start_idx = None

    # === 滾動一年收益率 ===
    rolling_1y_returns = []
    window = 252  # 約一年交易日
    if len(nav_arr) > window:
        for i in range(window, len(nav_arr)):
            ret_1y = (nav_arr[i] / nav_arr[i - window] - 1) * 100
            rolling_1y_returns.append(
                {
                    "date": str(dates[i]) if i < len(dates) else "",
                    "return_pct": round(float(ret_1y), 4),
                }
            )

    # === 回撤持續時間分佈 ===
    dd_durations = []
    in_dd = False
    dd_start = 0
    for i in range(len(drawdown)):
        if drawdown[i] > 0.0001:
            if not in_dd:
                in_dd = True
                dd_start = i
        else:
            if in_dd:
                dd_durations.append(i - dd_start)
                in_dd = False
    if in_dd:
        dd_durations.append(len(drawdown) - 1 - dd_start)

    # 分佈統計
    drawdown_duration_dist = {}
    if dd_durations:
        dd_arr = np.array(dd_durations)
        drawdown_duration_dist = {
            "mean_days": round(float(np.mean(dd_arr)), 1),
            "median_days": round(float(np.median(dd_arr)), 1),
            "max_days": int(np.max(dd_arr)),
            "min_days": int(np.min(dd_arr)),
            "count": len(dd_arr),
            "distribution": {
                "0-5天": int(np.sum(dd_arr <= 5)),
                "5-10天": int(np.sum((dd_arr > 5) & (dd_arr <= 10))),
                "10-20天": int(np.sum((dd_arr > 10) & (dd_arr <= 20))),
                "20-50天": int(np.sum((dd_arr > 20) & (dd_arr <= 50))),
                "50天以上": int(np.sum(dd_arr > 50)),
            },
        }

    # 水下時間統計
    underwater_days = [p["duration_days"] for p in underwater_periods]
    total_bars = len(nav_arr)
    underwater_bars = sum(underwater_days)
    underwater_pct = underwater_bars / total_bars * 100 if total_bars > 0 else 0

    return {
        "underwater_periods": underwater_periods[:10],  # 最多返回 10 個
        "recovery_periods": recovery_periods[:10],
        "rolling_1y_returns": (
            rolling_1y_returns[-250:] if rolling_1y_returns else []
        ),  # 最近一年
        "drawdown_durations": drawdown_duration_dist,
        "max_underwater_days": max(underwater_days) if underwater_days else 0,
        "avg_underwater_days": (
            round(float(np.mean(underwater_days)), 1) if underwater_days else 0
        ),
        "underwater_pct": round(underwater_pct, 2),
    }


# ============================================================
# 交易深度分析
# ============================================================


def trade_analysis(trade_details: list) -> dict:
    """
    交易深度分析。

    參數：
        trade_details: 配對交易列表，每筆需含 pnl, hold_days, return_pct, buy_date, sell_date

    返回：
        - streak: 連勝/連敗分析
        - hold_period: 按盈虧分類的持有期
        - profit_factor: 盈虧比
        - expectancy: 每筆期望收益
        - distribution: 收益分佈直方圖
        - best_worst_month: 最佳/最差月份
        - recovery_factor: 恢復因子
    """
    if not trade_details or len(trade_details) == 0:
        return {
            "streak": {
                "max_win_streak": 0,
                "max_loss_streak": 0,
                "current_streak": 0,
                "current_type": "none",
            },
            "hold_period": {"avg_winner_days": 0, "avg_loser_days": 0},
            "profit_factor": 0,
            "expectancy": 0,
            "distribution": {"bins": [], "counts": []},
            "best_month": None,
            "worst_month": None,
            "recovery_factor": 0,
            "total_trades": 0,
        }

    # 提取盈虧列表
    pnls = [t.get("pnl", 0) for t in trade_details]
    returns = [t.get("return_pct", 0) for t in trade_details]
    hold_days = [t.get("hold_days", 0) for t in trade_details]
    sell_dates = [t.get("sell_date", "") for t in trade_details]

    # === 連勝/連敗分析 ===
    max_win_streak = 0
    max_loss_streak = 0
    current_win = 0
    current_loss = 0
    for pnl in pnls:
        if pnl > 0:
            current_win += 1
            current_loss = 0
            max_win_streak = max(max_win_streak, current_win)
        elif pnl < 0:
            current_loss += 1
            current_win = 0
            max_loss_streak = max(max_loss_streak, current_loss)
        else:
            current_win = 0
            current_loss = 0

    # 當前連勝/連敗
    current_streak = 0
    current_type = "none"
    for pnl in reversed(pnls):
        if pnl > 0:
            if current_type in ("win", "none"):
                current_type = "win"
                current_streak += 1
            else:
                break
        elif pnl < 0:
            if current_type in ("loss", "none"):
                current_type = "loss"
                current_streak += 1
            else:
                break
        else:
            break

    # === 持有期分析 ===
    winners_days = [hold_days[i] for i in range(len(pnls)) if pnls[i] > 0]
    losers_days = [hold_days[i] for i in range(len(pnls)) if pnls[i] < 0]
    avg_winner_days = round(float(np.mean(winners_days)), 1) if winners_days else 0
    avg_loser_days = round(float(np.mean(losers_days)), 1) if losers_days else 0

    # === 盈虧比 (Profit Factor) ===
    gross_profit = sum(p for p in pnls if p > 0)
    gross_loss = abs(sum(p for p in pnls if p < 0))
    profit_factor = (
        round(gross_profit / gross_loss, 4) if gross_loss > 0 else float("inf")
    )

    # === 期望收益 (Expectancy) ===
    win_rate = len([p for p in pnls if p > 0]) / len(pnls) if pnls else 0
    avg_win = (
        float(np.mean([p for p in pnls if p > 0])) if any(p > 0 for p in pnls) else 0
    )
    avg_loss = (
        float(np.mean([p for p in pnls if p < 0])) if any(p < 0 for p in pnls) else 0
    )
    expectancy = round(win_rate * avg_win + (1 - win_rate) * avg_loss, 4)

    # === 收益分佈直方圖 ===
    if len(returns) >= 5:
        ret_arr = np.array(returns)
        # 自動計算分箱邊界
        min_ret = float(np.min(ret_arr))
        max_ret = float(np.max(ret_arr))
        # 10 個分箱
        bin_edges = np.linspace(min_ret, max_ret, 11)
        counts, _ = np.histogram(ret_arr, bins=bin_edges)
        distribution = {
            "bins": [round(float(b), 2) for b in bin_edges],
            "counts": [int(c) for c in counts],
        }
    else:
        distribution = {"bins": [], "counts": []}

    # === 最佳/最差月份 ===
    from collections import defaultdict

    monthly_pnl = defaultdict(float)
    for i, d in enumerate(sell_dates):
        if d and i < len(pnls):
            month_key = d[:7]  # YYYY-MM
            monthly_pnl[month_key] += pnls[i]

    best_month = None
    worst_month = None
    if monthly_pnl:
        best_key = max(monthly_pnl, key=monthly_pnl.get)
        worst_key = min(monthly_pnl, key=monthly_pnl.get)
        best_month = {"month": best_key, "pnl": round(monthly_pnl[best_key], 2)}
        worst_month = {"month": worst_key, "pnl": round(monthly_pnl[worst_key], 2)}

    # === 恢復因子 (Recovery Factor) ===
    total_return = sum(pnls)
    # 計算累計淨值的最大回撤
    cum_nav = [1.0]
    for r in returns:
        cum_nav.append(cum_nav[-1] * (1 + r / 100))
    cum_arr = np.array(cum_nav)
    peak = np.maximum.accumulate(cum_arr)
    dd = (peak - cum_arr) / peak
    max_dd_val = float(np.max(dd)) if len(dd) > 0 else 0
    max_dd_dollar = max_dd_val * 100  # 轉為百分比基準
    recovery_factor = round(total_return / max_dd_dollar, 4) if max_dd_dollar > 0 else 0

    return {
        "streak": {
            "max_win_streak": max_win_streak,
            "max_loss_streak": max_loss_streak,
            "current_streak": current_streak,
            "current_type": current_type,
        },
        "hold_period": {
            "avg_winner_days": avg_winner_days,
            "avg_loser_days": avg_loser_days,
            "winner_loser_ratio": (
                round(avg_winner_days / avg_loser_days, 2) if avg_loser_days > 0 else 0
            ),
        },
        "profit_factor": profit_factor,
        "expectancy": expectancy,
        "distribution": distribution,
        "best_month": best_month,
        "worst_month": worst_month,
        "recovery_factor": recovery_factor,
        "total_trades": len(pnls),
        "gross_profit": round(gross_profit, 2),
        "gross_loss": round(gross_loss, 2),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
    }


# ============================================================
# 蒙特卡羅模擬
# ============================================================


def monte_carlo_simulation(
    daily_returns: list, n_simulations: int = 1000, days: int = 252
) -> dict:
    """
    蒙特卡羅模擬 — 基於歷史日收益率重抽樣生成模擬權益曲線。

    參數：
        daily_returns: 歷史日收益率列表
        n_simulations: 模擬次數（默認 1000）
        days: 模擬天數（默認 252，約一年交易日）

    返回：
        - percentiles: 各百分位的終點淨值
        - confidence_intervals: 信賴區間 (5%, 25%, 50%, 75%, 95%)
        - prob_profit: 盈利概率
        - prob_large_drawdown: 發生 >20% 回撤的概率
        - simulated_curves: 百分位曲線數據（用於前端繪圖）
    """
    if not daily_returns or len(daily_returns) < 10:
        return {
            "percentiles": {},
            "confidence_intervals": {},
            "prob_profit": 0,
            "prob_large_drawdown": 0,
            "simulated_curves": {},
            "n_simulations": n_simulations,
            "days": days,
        }

    returns_arr = np.array(daily_returns, dtype=float)

    # 重抽樣模擬
    # 每次模擬：從歷史收益率中有放回地抽取 days 個
    np.random.seed(42)  # 可重複
    # 生成所有模擬的每日收益矩陣
    sampled = np.random.choice(returns_arr, size=(n_simulations, days), replace=True)

    # 計算每條模擬曲線的累計淨值
    cum_returns = np.cumprod(1 + sampled, axis=1)  # shape: (n_simulations, days)

    # 最終淨值
    final_values = cum_returns[:, -1]

    # 百分位統計
    percentiles = {
        "p5": round(float(np.percentile(final_values, 5)), 6),
        "p25": round(float(np.percentile(final_values, 25)), 6),
        "p50": round(float(np.percentile(final_values, 50)), 6),
        "p75": round(float(np.percentile(final_values, 75)), 6),
        "p95": round(float(np.percentile(final_values, 95)), 6),
        "mean": round(float(np.mean(final_values)), 6),
        "std": round(float(np.std(final_values)), 6),
    }

    # 信賴區間
    confidence_intervals = {
        "90pct": [percentiles["p5"], percentiles["p95"]],
        "50pct": [percentiles["p25"], percentiles["p75"]],
        "median": percentiles["p50"],
    }

    # 盈利概率（最終淨值 > 1）
    prob_profit = round(float(np.sum(final_values > 1.0) / n_simulations), 4)

    # 發生 >20% 回撤的概率
    # 計算每條曲線的最大回撤
    running_max = np.maximum.accumulate(cum_returns, axis=1)
    drawdowns = (running_max - cum_returns) / running_max
    max_drawdowns = np.max(drawdowns, axis=1)
    prob_large_dd = round(float(np.sum(max_drawdowns > 0.20) / n_simulations), 4)

    # 百分位曲線（用於前端繪圖）
    # 取 5%, 25%, 50%, 75%, 95% 對應的曲線
    # 按最終淨值排序後取對應百分位的那條曲線
    sorted_indices = np.argsort(final_values)
    n = n_simulations
    curve_indices = {
        "p5": sorted_indices[int(n * 0.05)],
        "p25": sorted_indices[int(n * 0.25)],
        "p50": sorted_indices[int(n * 0.50)],
        "p75": sorted_indices[int(n * 0.75)],
        "p95": sorted_indices[int(n * 0.95)],
    }
    simulated_curves = {}
    for label, idx in curve_indices.items():
        simulated_curves[label] = [round(float(v), 6) for v in cum_returns[idx]]

    return {
        "percentiles": percentiles,
        "confidence_intervals": confidence_intervals,
        "prob_profit": prob_profit,
        "prob_large_drawdown": prob_large_dd,
        "simulated_curves": simulated_curves,
        "n_simulations": n_simulations,
        "days": days,
    }


# ============================================================
# 滾動指標
# ============================================================


def rolling_metrics(daily_returns: list, dates: list, window: int = 60) -> dict:
    """
    滾動性能指標計算。

    參數：
        daily_returns: 日收益率列表
        dates: 對應日期列表
        window: 滾動窗口（默認 60 天）

    返回：
        - rolling_sharpe: 滾動夏普比率時間序列
        - rolling_sortino: 滾動 Sortino 時間序列
        - rolling_max_dd: 滾動最大回撤時間序列
        - rolling_volatility: 滾動波動率時間序列
        - dates: 對應日期
        - window: 使用的窗口
    """
    if not daily_returns or len(daily_returns) < window:
        return {
            "rolling_sharpe": [],
            "rolling_sortino": [],
            "rolling_max_dd": [],
            "rolling_volatility": [],
            "dates": [],
            "window": window,
            "summary": {},
        }

    dr = np.array(daily_returns, dtype=float)
    n = len(dr)

    rolling_sharpe = []
    rolling_sortino = []
    rolling_max_dd = []
    rolling_volatility = []
    out_dates = []

    for i in range(window, n):
        segment = dr[i - window : i]
        out_dates.append(str(dates[i]) if i < len(dates) else "")

        # 均值和標準差
        mean_r = float(np.mean(segment))
        std_r = float(np.std(segment))

        # 年化夏普（無風險利率 3%）
        sharpe = (mean_r - 0.03 / 252) / std_r * np.sqrt(252) if std_r > 0 else 0
        rolling_sharpe.append(round(sharpe, 4))

        # Sortino（下行標準差）
        downside = segment[segment < 0]
        downside_std = float(np.std(downside)) if len(downside) > 0 else 1e-9
        sortino = (
            (mean_r - 0.03 / 252) / downside_std * np.sqrt(252)
            if downside_std > 0
            else 0
        )
        rolling_sortino.append(round(sortino, 4))

        # 滾動最大回撤
        cum = np.cumprod(1 + segment)
        peak = np.maximum.accumulate(cum)
        dd = (peak - cum) / peak
        max_dd = float(np.max(dd)) * 100  # 百分比
        rolling_max_dd.append(round(max_dd, 4))

        # 年化波動率
        vol = std_r * np.sqrt(252)
        rolling_volatility.append(round(vol, 4))

    # 摘要統計
    sharpe_arr = np.array(rolling_sharpe)
    sort_arr = np.array(rolling_sortino)
    dd_arr = np.array(rolling_max_dd)
    vol_arr = np.array(rolling_volatility)

    summary = {
        "sharpe_mean": round(float(np.mean(sharpe_arr)), 4),
        "sharpe_min": round(float(np.min(sharpe_arr)), 4),
        "sharpe_max": round(float(np.max(sharpe_arr)), 4),
        "sortino_mean": round(float(np.mean(sort_arr)), 4),
        "sortino_min": round(float(np.min(sort_arr)), 4),
        "sortino_max": round(float(np.max(sort_arr)), 4),
        "max_dd_mean": round(float(np.mean(dd_arr)), 2),
        "max_dd_worst": round(float(np.max(dd_arr)), 2),
        "volatility_mean": round(float(np.mean(vol_arr)), 4),
        "volatility_min": round(float(np.min(vol_arr)), 4),
        "volatility_max": round(float(np.max(vol_arr)), 4),
    }

    return {
        "rolling_sharpe": rolling_sharpe,
        "rolling_sortino": rolling_sortino,
        "rolling_max_dd": rolling_max_dd,
        "rolling_volatility": rolling_volatility,
        "dates": out_dates,
        "window": window,
        "summary": summary,
    }


# ============================================================
# 詳細基準對比
# ============================================================


def benchmark_comparison_detail(bt_result: dict) -> dict:
    """
    詳細基準對比分析。

    參數：
        bt_result: run_backtest 返回的回測結果 dict

    返回：
        - up_capture: 上行捕獲率
        - down_capture: 下行捕獲率
        - batting_average: 打擊率（策略跑贏基準的天數比例）
        - relative_strength: 相對強度指數
        - bull_correlation: 牛市相關性
        - bear_correlation: 熊市相關性
    """
    daily_returns = bt_result.get("daily_returns", [])
    dates = bt_result.get("dates", [])

    if not daily_returns or len(daily_returns) < 20:
        return {
            "up_capture": 0,
            "down_capture": 0,
            "batting_average": 0,
            "relative_strength": [],
            "bull_correlation": 0,
            "bear_correlation": 0,
            "benchmark_available": False,
        }

    # 嘗試獲取基準收益率
    try:
        from src.core.benchmark import get_benchmark_returns

        start = dates[0] if dates else None
        end = dates[-1] if dates else None
        bench_data = get_benchmark_returns(start_date=start, end_date=end)
        bench_returns = bench_data.get("returns", [])
        bench_dates = bench_data.get("dates", [])
    except Exception:
        return {
            "up_capture": 0,
            "down_capture": 0,
            "batting_average": 0,
            "relative_strength": [],
            "bull_correlation": 0,
            "bear_correlation": 0,
            "benchmark_available": False,
        }

    if not bench_returns or len(bench_returns) < 20:
        return {
            "up_capture": 0,
            "down_capture": 0,
            "batting_average": 0,
            "relative_strength": [],
            "bull_correlation": 0,
            "bear_correlation": 0,
            "benchmark_available": False,
        }

    # 對齊日期
    bench_map = {str(d): r for d, r in zip(bench_dates, bench_returns)}
    aligned_strategy = []
    aligned_benchmark = []
    aligned_dates = []

    for i, d in enumerate(dates):
        d_str = str(d)
        if d_str in bench_map and i < len(daily_returns):
            aligned_strategy.append(daily_returns[i])
            aligned_benchmark.append(bench_map[d_str])
            aligned_dates.append(d_str)

    if len(aligned_strategy) < 20:
        return {
            "up_capture": 0,
            "down_capture": 0,
            "batting_average": 0,
            "relative_strength": [],
            "bull_correlation": 0,
            "bear_correlation": 0,
            "benchmark_available": False,
        }

    s = np.array(aligned_strategy)
    b = np.array(aligned_benchmark)

    # === 上行/下行捕獲率 ===
    up_mask = b > 0
    down_mask = b < 0

    if np.any(up_mask):
        up_capture = round(float(np.mean(s[up_mask]) / np.mean(b[up_mask])), 4)
    else:
        up_capture = 0

    if np.any(down_mask):
        down_capture = round(float(np.mean(s[down_mask]) / np.mean(b[down_mask])), 4)
    else:
        down_capture = 0

    # === 打擊率 ===
    outperform = np.sum(s > b)
    batting_average = round(float(outperform / len(s)), 4)

    # === 相對強度指數 ===
    # 滾動 20 日相對強度
    rs_window = 20
    relative_strength = []
    if len(s) >= rs_window:
        for i in range(rs_window, len(s)):
            strat_cum = float(np.prod(1 + s[i - rs_window : i]) - 1)
            bench_cum = float(np.prod(1 + b[i - rs_window : i]) - 1)
            rs = strat_cum - bench_cum
            relative_strength.append(
                {
                    "date": aligned_dates[i],
                    "rs": round(rs * 100, 4),  # 百分比
                }
            )

    # === 牛熊市相關性 ===
    # 牛市：基準 > 0，熊市：基準 < 0
    bull_mask = b > 0
    bear_mask = b < 0

    bull_corr = (
        round(float(np.corrcoef(s[bull_mask], b[bull_mask])[0, 1]), 4)
        if np.sum(bull_mask) > 5
        else 0
    )
    bear_corr = (
        round(float(np.corrcoef(s[bear_mask], b[bear_mask])[0, 1]), 4)
        if np.sum(bear_mask) > 5
        else 0
    )

    # 總相關性
    total_corr = round(float(np.corrcoef(s, b)[0, 1]), 4) if len(s) > 5 else 0

    return {
        "up_capture": up_capture,
        "down_capture": down_capture,
        "batting_average": batting_average,
        "relative_strength": (
            relative_strength[-250:] if relative_strength else []
        ),  # 最近一年
        "bull_correlation": bull_corr,
        "bear_correlation": bear_corr,
        "total_correlation": total_corr,
        "aligned_days": len(s),
        "benchmark_available": True,
    }


def _calc_risk_metrics(
    daily_returns: list,
    dates: list,
    max_dd_pct: float,
    nav: list,
    periods_per_year: int = 252,
) -> dict:
    """計算完整風險指標（periods_per_year 隨 K 線週期調整年化）"""
    bpy = max(int(periods_per_year), 1)
    if not daily_returns or len(daily_returns) < 2:
        return {
            "var_95": 0,
            "cvar_95": 0,
            "sortino_ratio": 0,
            "calmar_ratio": 0,
            "max_drawdown_recovery_days": 0,
            "annual_volatility": 0,
            "monthly_win_rate": 0,
            "profit_loss_ratio": 0,
            "annual_return_pct": 0,
        }

    dr = np.array(daily_returns)

    # VaR 95% (5th percentile)
    var_95 = float(np.percentile(dr, 5))

    # CVaR / Expected Shortfall
    cvar_95 = float(np.mean(dr[dr <= var_95])) if np.any(dr <= var_95) else var_95

    # Annual volatility
    annual_volatility = float(np.std(dr) * np.sqrt(bpy))

    # Sortino ratio (downside deviation)
    downside = dr[dr < 0]
    downside_std = float(np.std(downside)) if len(downside) > 0 else 1e-9
    mean_ret = float(np.mean(dr))
    sortino_ratio = (
        (mean_ret - 0.03 / bpy) / downside_std * np.sqrt(bpy) if downside_std > 0 else 0
    )

    # Annual return
    if dates:
        start = pd.to_datetime(dates[0]).to_pydatetime()
        end = pd.to_datetime(dates[-1]).to_pydatetime()
        years = (end - start).days / 365.25
        if years > 0 and nav and len(nav) > 1:
            annual_return_pct = float((nav[-1] / nav[0]) ** (1 / years) - 1) * 100
        else:
            annual_return_pct = 0
    else:
        annual_return_pct = 0

    # Calmar ratio (annual return / max drawdown)
    calmar_ratio = annual_return_pct / max_dd_pct if max_dd_pct > 0 else 0

    # Max drawdown recovery days
    max_dd_recovery_days = 0
    if nav and len(nav) > 1:
        peak = nav[0]
        peak_idx = 0
        dd_start_idx = None
        max_dd_idx = 0
        max_dd_val = 0
        for i, v in enumerate(nav):
            if v > peak:
                peak = v
                peak_idx = i
                dd_start_idx = None
            dd = (peak - v) / peak
            if dd > max_dd_val:
                max_dd_val = dd
                max_dd_idx = i
                dd_start_idx = peak_idx
        # Find recovery point
        if dd_start_idx is not None and max_dd_val > 0:
            peak_at_dd = nav[dd_start_idx]
            for i in range(max_dd_idx, len(nav)):
                if nav[i] >= peak_at_dd:
                    max_dd_recovery_days = i - max_dd_idx
                    break
            else:
                max_dd_recovery_days = len(nav) - 1 - max_dd_idx

    # Monthly win rate
    monthly_win_rate = 0
    if dates and len(dates) > 20:
        from collections import defaultdict

        month_returns = defaultdict(float)
        for i, d in enumerate(dates):
            dt = d if isinstance(d, datetime) else datetime.strptime(str(d), "%Y-%m-%d")
            key = dt.strftime("%Y-%m")
            if i < len(daily_returns):
                month_returns[key] += daily_returns[i]
        if month_returns:
            wins = sum(1 for v in month_returns.values() if v > 0)
            monthly_win_rate = wins / len(month_returns) * 100

    # Profit/Loss ratio
    profit_loss_ratio = 0
    wins = dr[dr > 0]
    losses = dr[dr < 0]
    if len(wins) > 0 and len(losses) > 0:
        profit_loss_ratio = float(np.mean(wins) / abs(np.mean(losses)))

    return {
        "var_95": round(var_95, 6),
        "cvar_95": round(cvar_95, 6),
        "sortino_ratio": round(sortino_ratio, 4),
        "calmar_ratio": round(calmar_ratio, 4),
        "max_drawdown_recovery_days": max_dd_recovery_days,
        "annual_volatility": round(annual_volatility, 4),
        "monthly_win_rate": round(monthly_win_rate, 2),
        "profit_loss_ratio": round(profit_loss_ratio, 4),
        "annual_return_pct": round(annual_return_pct, 4),
    }


# ============================================================
# 策略定義 — 已遷移至 src.core.strategies 包
# ============================================================
from src.core.strategies import STRATEGIES, STRATEGY_NAMES
from src.core.strategies.base import StrategyWithSLTP

for _cls in STRATEGIES.values():
    globals()[_cls.__name__] = _cls


def _max_drawdown_pct_from_nav(nav: list) -> float:
    """依淨值序列重算最大回撤（%），避免 Backtrader 在小樣本上與總收益混淆。"""
    if not nav or len(nav) < 2:
        return 0.0
    peak = float(nav[0])
    max_dd = 0.0
    for raw in nav:
        v = float(raw)
        if v > peak:
            peak = v
        if peak > 0:
            max_dd = max(max_dd, (peak - v) / peak * 100.0)
    return round(max_dd, 4)


# ============================================================
# 回測執行
# ============================================================

_prepared_df_cache: dict[str, pd.DataFrame] = {}
_PREPARED_CACHE_MAX = 96


def clear_prepare_cache():
    """清除回測數據預處理緩存（數據更新後調用）"""
    _prepared_df_cache.clear()


def _format_bar_datetime(dt) -> str:
    """日線僅日期；分鐘線含時分。"""
    if hasattr(dt, "strftime"):
        if getattr(dt, "hour", 0) == 0 and getattr(dt, "minute", 0) == 0:
            return dt.strftime("%Y-%m-%d")
        return dt.strftime("%Y-%m-%d %H:%M")
    return str(dt)[:16]


def _get_prepared_df(code: str, timeframe: str = "1d") -> pd.DataFrame:
    """Backtrader 用 OHLCV DataFrame（按 code+週期 進程內緩存）"""
    from src.core.kline_timeframe import cache_key, ensure_kline_for_backtest

    key = cache_key(code, timeframe)
    if key in _prepared_df_cache:
        return _prepared_df_cache[key]

    df, _src, _tf = ensure_kline_for_backtest(code, timeframe)
    if df.empty:
        raise ValueError(f"股票 {code} 無歷史數據（請檢查代碼、週期或網路）")

    from src.core.backtest_runtime import trim_ohlcv_dataframe

    df = trim_ohlcv_dataframe(df)

    if len(_prepared_df_cache) >= _PREPARED_CACHE_MAX:
        _prepared_df_cache.pop(next(iter(_prepared_df_cache)))
    _prepared_df_cache[key] = df
    return df


def prepare_data(code: str, timeframe: str = "1d") -> bt.feeds.PandasData:
    """從數據庫讀取數據並轉為 Backtrader 格式"""
    return bt.feeds.PandasData(dataname=_get_prepared_df(code, timeframe=timeframe))


def run_backtest(
    code: str,
    strategy_name: str = "dual_ma",
    params: dict = None,
    cash: float = None,
    commission: float = None,
    plot: bool = False,
    stop_loss_pct: float = None,
    take_profit_pct: float = None,
    trailing_stop_pct: float = None,
    benchmark: bool = False,
    slippage_pct: float = 0.0,
    volume_slippage: bool = None,
    order_size_shares: int = 0,
    enable_t1: bool = True,
    enable_limit: bool = True,
    timeframe: str = "1d",
    task_id: str = None,
    circuit_breaker_dd: float = None,
    max_position_pct: float = None,
    sandbox_mode: bool = False,
    user_id: int = None,
) -> dict:
    """
    執行回測並返回結果。

    參數：
        code: 股票代碼
        strategy_name: 策略名稱
        params: 策略參數
        cash: 初始資金
        commission: 手續費率
        plot: 是否繪圖
        stop_loss_pct: 止損百分比
        take_profit_pct: 止盈百分比
        trailing_stop_pct: 移動止損百分比
        benchmark: 是否基準對比
        slippage_pct: 滑點百分比（默認 0.0，即 0%）
        enable_t1: 是否啟用 T+1 限制（默認 True）
        enable_limit: 是否啟用漲跌停限制（默認 True）
        timeframe: K 線週期 1d / 1h / 1m（默認 1d）
        sandbox_mode: 是否為沙箱模式（不污染正式記錄）
    """
    from src.core.kline_timeframe import (
        bars_per_year as tf_bars_per_year,
    )
    from src.core.kline_timeframe import (
        normalize_timeframe,
        timeframe_label,
    )

    tf = normalize_timeframe(timeframe)
    bpy = tf_bars_per_year(tf)
    tf_label = timeframe_label(tf)

    if cash is None:
        cash = settings.backtest_cash
    if commission is None:
        commission = settings.backtest_commission

    strategy_cls = STRATEGIES.get(strategy_name)
    if not strategy_cls:
        raise ValueError(f"未知策略: {strategy_name}，可選: {list(STRATEGIES.keys())}")

    if task_id:
        from src.core.task_manager import is_task_cancelled, update_task

        if is_task_cancelled(task_id):
            raise RuntimeError("任務已取消")
        update_task(task_id, progress=10)

    from src.core.backtest_runtime import (
        compute_volume_impact_slippage_pct,
        dispose_cerebro,
    )

    cerebro = bt.Cerebro()
    results = None

    # 添加主策略
    if params:
        cerebro.addstrategy(strategy_cls, **params)
    else:
        cerebro.addstrategy(strategy_cls)

    # 添加止損/止盈層（如果指定）
    sltp_params = {}
    if stop_loss_pct is not None and stop_loss_pct > 0:
        sltp_params["stop_loss_pct"] = stop_loss_pct
    if take_profit_pct is not None and take_profit_pct > 0:
        sltp_params["take_profit_pct"] = take_profit_pct
    if trailing_stop_pct is not None and trailing_stop_pct > 0:
        sltp_params["trailing_stop_pct"] = trailing_stop_pct

    if sltp_params:
        cerebro.addstrategy(StrategyWithSLTP, **sltp_params)

    if max_position_pct is not None and 0 < float(max_position_pct) < 1:
        from src.core.risk_backtest import RiskRunConfig, attach_risk_to_cerebro

        _rc = RiskRunConfig(max_position_pct=float(max_position_pct))
        attach_risk_to_cerebro(
            cerebro, _rc, sltp=False, commission=False, slippage=False
        )

    data = prepare_data(code, timeframe=tf)
    # 將股票代碼掛載到 data 上，供 LimitFilter 使用
    data._name = code
    cerebro.adddata(data)

    # 數據長度校驗：確保 K 線條數 >= 策略最大指標週期
    try:
        strat_cls = cerebro.strats[0][0]
        max_period = 0
        if hasattr(strat_cls, "params"):
            for _name, default in strat_cls.params._getpairs():
                if isinstance(default, int) and default > max_period:
                    max_period = default
        if max_period > 0 and len(data) < max_period:
            raise ValueError(
                f"數據不足：{code} 僅 {len(data)} 條 K 線，"
                f"策略需要至少 {max_period} 條"
            )
    except ValueError:
        raise
    except Exception:
        pass

    cerebro.broker.setcash(cash)
    # 設置手續費和滑點
    # Backtrader 的 slip_perc 只作用於價格，不作用於佣金
    # 所以我們手動設置 slip_perc 來模擬滑點
    use_volume_slip = (
        volume_slippage
        if volume_slippage is not None
        else getattr(settings, "volume_slippage_enabled", False)
    )
    effective_slip_pct = slippage_pct
    if use_volume_slip and slippage_pct > 0:
        prep_df = _get_prepared_df(code, timeframe=tf)
        bar_vol = (
            float(prep_df["Volume"].iloc[-1])
            if not prep_df.empty and "Volume" in prep_df.columns
            else 0.0
        )
        est_shares = float(order_size_shares or 100)
        effective_slip_pct = compute_volume_impact_slippage_pct(
            slippage_pct,
            est_shares,
            bar_vol,
            participation_cap=getattr(
                settings, "volume_slippage_participation_cap", 0.05
            ),
        )
    slip_pct = effective_slip_pct / 100.0 if effective_slip_pct > 0 else 0.0
    # 使用 A 股精確佣金模型（佣金最低 5 元 + 印花稅僅賣出 + 過戶費）
    stamp_tax_rate = settings.backtest_stamp_tax
    comm_info = AStockCommission(
        commission=commission,
        stamp_tax=stamp_tax_rate,
        min_commission=5.0,
    )
    cerebro.broker.addcommissioninfo(comm_info)
    if slip_pct > 0:
        cerebro.broker.set_slippage_perc(slip_pct)

    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe", riskfreerate=0.03)
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.Returns, _name="returns")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")
    cerebro.addanalyzer(bt.analyzers.TimeReturn, _name="timereturn")

    # 添加漲跌停限制分析器
    if enable_limit:
        cerebro.addanalyzer(LimitFilter, _name="limit_filter")

    # 添加 T+1 限制分析器
    if enable_t1:
        cerebro.addanalyzer(T1Filter, _name="t1_filter")

    # 交易明細記錄器
    trade_log = []

    class TradeObserver(bt.Analyzer):
        def notify_trade(self, trade):
            if trade.isclosed:
                trade_log.append(
                    {
                        "date": _format_bar_datetime(
                            self.datas[0].num2date(trade.dtclose)
                        ),
                        "type": "close",
                        "price": round(trade.price, 2),
                        "size": trade.size,
                        "pnl": round(trade.pnl, 2),
                        "pnlcomm": round(trade.pnlcomm, 2),
                        "barlen": trade.barlen,
                    }
                )
            elif trade.isopen:
                trade_log.append(
                    {
                        "date": _format_bar_datetime(
                            self.datas[0].num2date(trade.dtopen)
                        ),
                        "type": "open",
                        "price": round(trade.price, 2),
                        "size": trade.size,
                        "pnl": 0,
                        "pnlcomm": 0,
                        "barlen": 0,
                    }
                )

    cerebro.addanalyzer(TradeObserver, _name="tradeobs")

    initial_value = cerebro.broker.getvalue()
    try:
        results = cerebro.run()
        final_value = cerebro.broker.getvalue()
        strat = results[0]
    finally:
        if not plot:
            dispose_cerebro(cerebro, results)

    sharpe = strat.analyzers.sharpe.get_analysis()
    drawdown = strat.analyzers.drawdown.get_analysis()
    _ = strat.analyzers.returns.get_analysis()
    trades = strat.analyzers.trades.get_analysis()
    time_returns = strat.analyzers.timereturn.get_analysis()

    total_return = (final_value - initial_value) / initial_value * 100

    total_trades = trades.get("total", {}).get("total", 0)
    won = trades.get("won", {}).get("total", 0)
    lost = trades.get("lost", {}).get("total", 0)
    win_rate = (won / total_trades * 100) if total_trades > 0 else 0

    # 構建淨值曲線
    dates = sorted(time_returns.keys())
    daily_returns = [time_returns[d] for d in dates]
    nav = [1.0]
    for r in daily_returns:
        nav.append(nav[-1] * (1 + r))

    max_dd_bt = float(drawdown.get("max", {}).get("drawdown", 0) or 0)
    max_dd = _max_drawdown_pct_from_nav(nav)
    if max_dd <= 0 and max_dd_bt > 0:
        max_dd = round(min(max_dd_bt, 100.0), 4)

    # 用日收益率計算夏普（更準確）
    import numpy as np

    if daily_returns and len(daily_returns) > 1:
        mean_ret = np.mean(daily_returns)
        std_ret = np.std(daily_returns)
        computed_sharpe = (
            (mean_ret - 0.03 / bpy) / std_ret * (bpy**0.5) if std_ret > 0 else 0
        )
    else:
        computed_sharpe = 0

    bt_sharpe = sharpe.get("sharperatio")
    final_sharpe = (
        computed_sharpe if bt_sharpe is None or abs(bt_sharpe) > 100 else bt_sharpe
    )

    # 整理交易明細（配對 open/close）
    paired_trades = []
    open_stack = []
    for t in trade_log:
        if t["type"] == "open":
            open_stack.append(t)
        elif t["type"] == "close" and open_stack:
            op = open_stack.pop(0)
            paired_trades.append(
                {
                    "buy_date": op["date"],
                    "buy_price": op["price"],
                    "sell_date": t["date"],
                    "sell_price": t["price"],
                    "size": t["size"],
                    "pnl": t["pnlcomm"],
                    "hold_days": t["barlen"],
                    "return_pct": (
                        round(t["pnlcomm"] / (op["price"] * abs(op["size"])) * 100, 2)
                        if op["price"] and op["size"]
                        else 0
                    ),
                }
            )

    # 讀取 K 線數據（用於前端畫圖）— 從已加載的 data 轉換，避免重複讀取 DB
    kline = []
    try:
        kline_df = data.p.dataname  # 這是 prepare_data 返回的 DataFrame
        if kline_df is not None and not kline_df.empty:
            for idx, row in kline_df.iterrows():
                date_str = _format_bar_datetime(idx)
                kline.append(
                    {
                        "date": date_str,
                        "open": round(float(row["Open"]), 2),
                        "high": round(float(row["High"]), 2),
                        "low": round(float(row["Low"]), 2),
                        "close": round(float(row["Close"]), 2),
                        "volume": (
                            int(row["Volume"]) if not pd.isna(row["Volume"]) else 0
                        ),
                    }
                )
    except Exception:
        # 備用：從 DB 重新讀取
        kline_df = load_daily_kline(code)
        if not kline_df.empty:
            for _, row in kline_df.iterrows():
                kline.append(
                    {
                        "date": str(row["date"]),
                        "open": round(float(row["open"]), 2),
                        "high": round(float(row["high"]), 2),
                        "low": round(float(row["low"]), 2),
                        "close": round(float(row["close"]), 2),
                        "volume": (
                            int(row["volume"]) if not pd.isna(row["volume"]) else 0
                        ),
                    }
                )

    # 買賣信號（用於 K 線圖標記）
    signals = []
    for t in trade_log:
        signals.append(
            {
                "date": t["date"],
                "type": "buy" if t["type"] == "open" else "sell",
                "price": t["price"],
            }
        )

    # 計算風險指標
    risk = _calc_risk_metrics(daily_returns, dates, max_dd, nav, periods_per_year=bpy)

    # 權益曲線深度分析
    equity_analysis = analyze_equity_curve(nav, dates, daily_returns)

    # 獲取漲跌停和 T+1 過濾結果
    limit_info = {}
    if enable_limit and hasattr(strat.analyzers, "limit_filter"):
        limit_info = strat.analyzers.limit_filter.get_analysis()

    t1_info = {}
    if enable_t1 and hasattr(strat.analyzers, "t1_filter"):
        t1_info = strat.analyzers.t1_filter.get_analysis()

    result = {
        "code": code,
        "strategy": strategy_name,
        "strategy_name": STRATEGY_NAMES.get(strategy_name, strategy_name),
        "timeframe": tf,
        "timeframe_label": tf_label,
        "bars_count": len(dates),
        "initial_cash": cash,
        "final_value": final_value,
        "total_return_pct": round(total_return, 4),
        "sharpe_ratio": round(final_sharpe, 4) if final_sharpe else 0,
        "max_drawdown_pct": round(max_dd, 4),
        "total_trades": total_trades,
        "won_trades": won,
        "lost_trades": lost,
        "win_rate_pct": round(win_rate, 2),
        "nav": [round(v, 6) for v in nav],
        "dates": [str(d) for d in dates],
        "equity_curve": [
            {"date": str(dates[i]), "value": round(float(nav[i]), 6)}
            for i in range(min(len(dates), len(nav)))
        ],
        "daily_returns": [round(r, 6) for r in daily_returns],
        "trade_details": paired_trades,
        "signals": signals,
        "kline": kline,
        "annual_return_pct": risk["annual_return_pct"],
        "var_95": risk["var_95"],
        "cvar_95": risk["cvar_95"],
        "sortino_ratio": risk["sortino_ratio"],
        "calmar_ratio": risk["calmar_ratio"],
        "max_drawdown_recovery_days": risk["max_drawdown_recovery_days"],
        "annual_volatility": risk["annual_volatility"],
        "monthly_win_rate": risk["monthly_win_rate"],
        "profit_loss_ratio": risk["profit_loss_ratio"],
        # 進階回測參數
        "slippage_pct": slippage_pct,
        "effective_slippage_pct": round(effective_slip_pct, 6),
        "volume_slippage": bool(use_volume_slip),
        "enable_t1": enable_t1,
        "enable_limit": enable_limit,
        # 漲跌停限制結果
        "limit_filter": limit_info,
        # T+1 限制結果
        "t1_filter": t1_info,
        # 權益曲線分析
        "equity_analysis": equity_analysis,
        # 用戶標記
        "user_id": user_id,
    }

    if (
        circuit_breaker_dd is not None
        and float(circuit_breaker_dd) > 0
        and nav
        and dates
    ):
        from src.core.risk_manager import drawdown_circuit_breaker

        cb = drawdown_circuit_breaker(
            nav, [str(d) for d in dates], float(circuit_breaker_dd)
        )
        result["risk_control"] = {
            "circuit_breaker_dd": float(circuit_breaker_dd),
            "circuit_breaker": cb,
            "stop_loss_pct": stop_loss_pct,
            "take_profit_pct": take_profit_pct,
            "trailing_stop_pct": trailing_stop_pct,
            "max_position_pct": max_position_pct,
        }

    # 持久化回測結果
    try:
        from src.core.db import save_backtest_result

        save_backtest_result(result)
    except Exception as e:
        logger.debug(f"保存回測結果跳過: {e}")

    logger.info(
        f"回測 {code}/{strategy_name}: "
        f"收益 {total_return:.2f}%, 回撤 {max_dd:.2f}%, "
        f"夏普 {final_sharpe:.4f}, 交易 {total_trades} 次"
    )

    if plot:
        cerebro.plot(style="candle", volume=True)

    # 基準對比（可選）
    if benchmark:
        try:
            from src.core.benchmark import compare_with_benchmark

            result["benchmark_comparison"] = compare_with_benchmark(result)
        except Exception as e:
            logger.debug(f"基準對比跳過: {e}")
            result["benchmark_comparison"] = None

    return result


def run_multi_strategy(
    code: str, plot: bool = False, task_id: str = None
) -> list[dict]:
    """對同一隻股票跑所有策略並對比（並行執行）"""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    from src.config import settings
    from src.core.compute_budget import get_thread_workers

    max_workers = get_thread_workers(
        getattr(settings, "multi_strategy_workers", 4),
        task_id=task_id,
        min_workers=1,
    )

    names = list(STRATEGIES.keys())
    total = len(names)
    results = []
    done = 0

    def _run_one(name: str):
        if task_id:
            from src.core.task_manager import is_task_cancelled

            if is_task_cancelled(task_id):
                raise RuntimeError("任務已取消")
        return run_backtest(code, strategy_name=name, plot=False, task_id=task_id)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_run_one, name): name for name in names}
        for future in as_completed(futures):
            name = futures[future]
            done += 1
            if task_id:
                from src.core.task_manager import is_task_cancelled, update_task

                if is_task_cancelled(task_id):
                    executor.shutdown(wait=False, cancel_futures=True)
                    raise RuntimeError("任務已取消")
                update_task(task_id, progress=min(95, int(done / total * 100)))
            try:
                r = future.result()
                results.append(r)
            except Exception as e:
                logger.error(f"策略 {name} 失敗: {e}")

    if results:
        logger.info(f"策略對比完成: {code}, {len(results)} 個策略")

    return results
