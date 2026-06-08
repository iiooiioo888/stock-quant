"""
高級風險管理模塊 — 倉位計算、風險預算、回撤保護

提供 PositionSizer（倉位管理）、RiskBudget（風險預算）、
DrawdownProtector（回撤保護）三個核心類，以及 drawdown_circuit_breaker 函數。
"""

import math

import numpy as np

from src.core.db import load_daily_kline
from src.utils.logger import logger

# ============================================================
# PositionSizer — 倉位管理器
# ============================================================


class PositionSizer:
    """倉位管理器 — 根據風險計算每筆交易的倉位大小"""

    def __init__(self, total_capital: float, max_risk_per_trade: float = 0.02):
        """
        初始化倉位管理器。

        參數:
            total_capital: 總資金
            max_risk_per_trade: 每筆交易最大風險比例，默認 2%
        """
        self.total_capital = total_capital
        self.max_risk_per_trade = max_risk_per_trade

    def fixed_fraction(self, fraction: float) -> float:
        """
        固定比例倉位 — 按總資金的固定比例分配。

        參數:
            fraction: 資金比例（如 0.1 表示 10%）

        返回:
            倉位金額
        """
        if fraction <= 0 or fraction > 1:
            raise ValueError("fraction 必須在 (0, 1] 之間")
        return self.total_capital * fraction

    def atr_based(self, atr: float, risk_multiplier: float = 1.0) -> int:
        """
        ATR 倉位 sizing — 根據 ATR（平均真實波幅）計算倉位股數。

        公式: 股數 = (總資金 × 最大風險) / (ATR × 風險乘數)

        參數:
            atr: 平均真實波幅（絕對值，如 2.5 元）
            risk_multiplier: ATR 風險乘數，越大止損越寬，倉位越小

        返回:
            可買入股數（向下取整到 100 股的倍數，A 股最小交易單位）
        """
        if atr <= 0:
            raise ValueError("ATR 必須大於 0")

        risk_amount = self.total_capital * self.max_risk_per_trade
        shares = risk_amount / (atr * risk_multiplier)

        # A 股最小交易單位為 100 股
        shares = int(shares // 100) * 100
        return max(100, shares)  # 至少 100 股

    def kelly_position(self, win_rate: float, avg_win: float, avg_loss: float) -> float:
        """
        Kelly 公式倉位 — 根據歷史勝率和盈虧比計算最優倉位比例。

        公式: f* = (p × b - q) / b
        其中 p=勝率, q=1-p, b=盈虧比(avg_win/avg_loss)

        為了安全，使用 Half-Kelly（實際倉位 = Kelly 倉位 / 2）。

        參數:
            win_rate: 勝率（0-1 之間）
            avg_win: 平均盈利金額
            avg_loss: 平均虧損金額（正數）

        返回:
            推薦倉位金額（Half-Kelly）
        """
        if win_rate <= 0 or win_rate >= 1:
            raise ValueError("勝率必須在 (0, 1) 之間")
        if avg_win <= 0 or avg_loss <= 0:
            raise ValueError("平均盈利和虧損必須大於 0")

        # 計算盈虧比
        b = avg_win / avg_loss
        p = win_rate
        q = 1.0 - p

        # Kelly 公式
        kelly_f = (p * b - q) / b

        # 限制範圍：Kelly 為負說明不該交易
        if kelly_f <= 0:
            return 0.0

        # 使用 Half-Kelly 更保守
        half_kelly = kelly_f / 2.0

        # 限制最大倉位為 25%
        half_kelly = min(half_kelly, 0.25)

        return self.total_capital * half_kelly

    def volatility_target(
        self, target_vol: float, current_vol: float, current_position: float
    ) -> float:
        """
        波動率目標倉位 — 根據目標波動率調整持倉。

        公式: 新倉位 = 當前倉位 × (目標波動率 / 當前波動率)

        參數:
            target_vol: 目標年化波動率（如 0.15 表示 15%）
            current_vol: 當前年化波動率
            current_position: 當前持倉金額

        返回:
            調整後倉位金額
        """
        if current_vol <= 0:
            raise ValueError("當前波動率必須大於 0")
        if target_vol <= 0:
            raise ValueError("目標波動率必須大於 0")

        # 計算調整比例
        adjustment = target_vol / current_vol

        # 限制調整幅度在 [0.1, 2.0] 之間，避免極端倉位
        adjustment = max(0.1, min(2.0, adjustment))

        new_position = current_position * adjustment

        # 不超過總資金
        return min(new_position, self.total_capital)

    def drawdown_adjusted(self, current_dd_pct: float, base_size: float) -> float:
        """
        回撤調整倉位 — 回撤越大，倉位越小。

        策略:
          - 回撤 < 5%: 不調整
          - 回撤 5%-10%: 線性縮減到 75%
          - 回撤 10%-20%: 線性縮減到 50%
          - 回撤 >= 20%: 縮減到 25%

        參數:
            current_dd_pct: 當前回撤百分比（正數，如 15 表示 -15%）
            base_size: 基礎倉位金額

        返回:
            調整後倉位金額
        """
        if current_dd_pct < 0:
            current_dd_pct = abs(current_dd_pct)

        if current_dd_pct < 5:
            multiplier = 1.0
        elif current_dd_pct < 10:
            # 5%-10%: 線性從 1.0 縮減到 0.75
            multiplier = 1.0 - (current_dd_pct - 5) * 0.05
        elif current_dd_pct < 20:
            # 10%-20%: 線性從 0.75 縮減到 0.5
            multiplier = 0.75 - (current_dd_pct - 10) * 0.025
        else:
            # >= 20%: 縮減到 25%
            multiplier = 0.25

        return base_size * max(0.1, multiplier)


# ============================================================
# RiskBudget — 風險預算管理
# ============================================================


class RiskBudget:
    """風險預算管理 — 監控組合和單個持倉的風險暴露"""

    def __init__(self, max_portfolio_risk: float = 0.15, max_single_risk: float = 0.05):
        """
        初始化風險預算管理器。

        參數:
            max_portfolio_risk: 組合最大風險比例（默認 15%）
            max_single_risk: 單個持倉最大風險比例（默認 5%）
        """
        self.max_portfolio_risk = max_portfolio_risk
        self.max_single_risk = max_single_risk

    def check_position(
        self, position_value: float, total_value: float, position_vol: float
    ) -> dict:
        """
        檢查單個持倉是否超限。

        參數:
            position_value: 持倉市值
            total_value: 組合總市值
            position_vol: 該持倉年化波動率

        返回:
            {
                "position_pct": 持倉佔比,
                "risk_contribution": 風險貢獻（持倉佔比 × 波動率）,
                "exceeds_limit": 是否超限,
                "suggested_reduction": 建議減倉金額（如超限）,
                "status": "正常" / "警告" / "超限"
            }
        """
        if total_value <= 0:
            return {"error": "總市值必須大於 0"}

        position_pct = position_value / total_value
        risk_contribution = position_pct * position_vol
        exceeds_limit = risk_contribution > self.max_single_risk

        result = {
            "position_pct": round(position_pct, 4),
            "risk_contribution": round(risk_contribution, 4),
            "max_allowed_risk": self.max_single_risk,
            "exceeds_limit": exceeds_limit,
            "suggested_reduction": 0.0,
            "status": "正常",
        }

        if exceeds_limit:
            # 計算需要減倉多少才能達到風險上限
            target_risk_contribution = self.max_single_risk * 0.9  # 留 10% 緩衝
            target_pct = (
                target_risk_contribution / position_vol if position_vol > 0 else 0
            )
            target_value = total_value * target_pct
            reduction = position_value - target_value
            result["suggested_reduction"] = round(max(0, reduction), 2)
            result["status"] = "超限"
        elif risk_contribution > self.max_single_risk * 0.8:
            result["status"] = "警告"

        return result

    def portfolio_risk_budget(self, positions: list[dict]) -> dict:
        """
        計算組合風險預算使用情況。

        參數:
            positions: 持倉列表，每個元素為:
                {"value": 持倉市值, "vol": 年化波動率, "code": 股票代碼(可選)}

        返回:
            {
                "total_value": 總市值,
                "total_risk": 總風險,
                "risk_budget_used_pct": 風險預算使用率,
                "positions": 各持倉風險明細,
                "status": 整體狀態
            }
        """
        if not positions:
            return {"error": "持倉列表為空"}

        total_value = sum(p.get("value", 0) for p in positions)
        if total_value <= 0:
            return {"error": "總市值為 0"}

        position_details = []
        total_risk = 0.0

        for p in positions:
            value = p.get("value", 0)
            vol = p.get("vol", 0)
            code = p.get("code", "未知")
            pct = value / total_value
            risk_contrib = pct * vol
            total_risk += risk_contrib

            position_details.append(
                {
                    "code": code,
                    "value": round(value, 2),
                    "weight_pct": round(pct * 100, 2),
                    "vol": round(vol, 4),
                    "risk_contribution": round(risk_contrib, 4),
                }
            )

        budget_used_pct = (
            total_risk / self.max_portfolio_risk if self.max_portfolio_risk > 0 else 0
        )

        if budget_used_pct > 1.0:
            status = "超限"
        elif budget_used_pct > 0.8:
            status = "警告"
        else:
            status = "正常"

        return {
            "total_value": round(total_value, 2),
            "total_risk": round(total_risk, 4),
            "max_portfolio_risk": self.max_portfolio_risk,
            "risk_budget_used_pct": round(budget_used_pct * 100, 2),
            "positions": position_details,
            "status": status,
        }

    def suggest_rebalance(self, positions: list[dict]) -> list[dict]:
        """
        建議減倉/加倉操作 — 基於風險預算計算每個持倉的調整建議。

        參數:
            positions: 持倉列表，同 portfolio_risk_budget

        返回:
            建議列表，每個元素:
                {"code": 代碼, "action": "減倉"/"加倉"/"保持", "current_risk": ..., "target_risk": ..., "adjustment": 金額}
        """
        if not positions:
            return []

        total_value = sum(p.get("value", 0) for p in positions)
        if total_value <= 0:
            return []

        # 計算目標：等風險貢獻
        n = len(positions)
        target_risk_per_position = self.max_portfolio_risk / n

        suggestions = []
        for p in positions:
            value = p.get("value", 0)
            vol = p.get("vol", 0)
            code = p.get("code", "未知")

            current_weight = value / total_value
            current_risk = current_weight * vol

            if vol <= 0:
                suggestions.append(
                    {
                        "code": code,
                        "action": "保持",
                        "current_risk": 0,
                        "target_risk": 0,
                        "adjustment": 0,
                    }
                )
                continue

            # 目標權重 = 目標風險 / 波動率
            target_weight = target_risk_per_position / vol
            target_value = total_value * target_weight
            adjustment = target_value - value

            if adjustment > total_value * 0.01:
                action = "加倉"
            elif adjustment < -total_value * 0.01:
                action = "減倉"
            else:
                action = "保持"

            suggestions.append(
                {
                    "code": code,
                    "action": action,
                    "current_risk": round(current_risk, 4),
                    "target_risk": round(target_risk_per_position, 4),
                    "adjustment": round(adjustment, 2),
                }
            )

        return suggestions


# ============================================================
# DrawdownProtector — 回撤保護器
# ============================================================


class DrawdownProtector:
    """回撤保護器 — 監控淨值回撤並自動調整倉位"""

    def __init__(self, max_drawdown_pct: float = 20.0, warning_pct: float = 10.0):
        """
        初始化回撤保護器。

        參數:
            max_drawdown_pct: 最大回撤百分比（觸發停止交易），默認 20%
            warning_pct: 警告回撤百分比（開始減倉），默認 10%
        """
        self.max_drawdown_pct = max_drawdown_pct
        self.warning_pct = warning_pct
        self.peak_value = 0.0

    def update(self, current_value: float) -> dict:
        """
        更新淨值並檢查回撤狀態。

        參數:
            current_value: 當前淨值

        返回:
            {
                "status": "正常" / "警告" / "危險" / "停止",
                "current_dd": 當前回撤百分比,
                "peak_value": 歷史最高淨值,
                "action": "正常交易" / "減倉" / "大幅減倉" / "停止交易",
                "position_multiplier": 倉位縮放因子 (0-1)
            }
        """
        # 更新歷史最高淨值
        if current_value > self.peak_value:
            self.peak_value = current_value

        if self.peak_value <= 0:
            return {
                "status": "正常",
                "current_dd": 0.0,
                "peak_value": 0.0,
                "action": "正常交易",
                "position_multiplier": 1.0,
            }

        # 計算當前回撤
        current_dd = (self.peak_value - current_value) / self.peak_value * 100

        # 確定狀態和動作
        multiplier = self.get_position_multiplier(current_dd)

        if current_dd >= self.max_drawdown_pct:
            status = "停止"
            action = "停止交易"
        elif current_dd >= self.warning_pct * 1.5:
            status = "危險"
            action = "大幅減倉"
        elif current_dd >= self.warning_pct:
            status = "警告"
            action = "減倉"
        else:
            status = "正常"
            action = "正常交易"

        return {
            "status": status,
            "current_dd": round(current_dd, 2),
            "peak_value": round(self.peak_value, 2),
            "action": action,
            "position_multiplier": round(multiplier, 2),
        }

    def get_position_multiplier(self, current_dd: float) -> float:
        """
        根據回撤深度返回倉位縮放因子。

        策略:
          - dd < warning: 1.0（不調整）
          - dd < max: 線性從 1.0 遞減到 0.5
          - dd >= max: 0（停止交易）

        參數:
            current_dd: 當前回撤百分比

        返回:
            縮放因子 (0-1)
        """
        if current_dd < self.warning_pct:
            return 1.0
        elif current_dd >= self.max_drawdown_pct:
            return 0.0
        else:
            # 線性插值: 從 warning 到 max，因子從 1.0 到 0.5
            ratio = (current_dd - self.warning_pct) / (
                self.max_drawdown_pct - self.warning_pct
            )
            return 1.0 - ratio * 0.5


# ============================================================
# drawdown_circuit_breaker — 回撤熔斷分析
# ============================================================


def drawdown_circuit_breaker(nav: list, dates: list, max_dd: float = 20.0) -> dict:
    """
    分析回測結果，識別回撤熔斷觸發點。

    參數:
        nav: 淨值序列（list of float）
        dates: 對應日期序列（list of str）
        max_dd: 最大允許回撤百分比，默認 20%

    返回:
        {
            "max_drawdown_pct": 實際最大回撤,
            "max_dd_date": 最大回撤日期,
            "circuit_breakers": [{
                "date": 觸發日期,
                "drawdown_pct": 觸發時回撤,
                "peak_date": 峰值日期,
                "peak_value": 峰值,
                "current_value": 觸發時淨值,
                "recovery_date": 恢復日期（如已恢復）,
                "recovery_days": 恢復天數
            }, ...],
            "total_triggers": 觸發次數,
            "would_stop_trading": 是否會觸發停止交易
        }
    """
    if not nav or not dates or len(nav) != len(dates):
        return {"error": "淨值和日期序列為空或長度不匹配"}

    nav_arr = np.array(nav, dtype=float)

    # 計算回撤序列
    peak = np.maximum.accumulate(nav_arr)
    drawdowns = (peak - nav_arr) / peak * 100

    # 找到所有超過 max_dd 的區間
    circuit_breakers = []
    in_breaker = False
    breaker_start_idx = None
    peak_idx = 0

    for i in range(len(drawdowns)):
        if drawdowns[i] >= max_dd and not in_breaker:
            # 觸發熔斷
            in_breaker = True
            breaker_start_idx = i
            # 找到此次回撤的峰值
            peak_idx = np.argmax(nav_arr[: i + 1])

        elif drawdowns[i] < max_dd and in_breaker:
            # 恢復（回撤降到 max_dd 以下）
            in_breaker = False
            recovery_days = i - breaker_start_idx

            circuit_breakers.append(
                {
                    "date": dates[breaker_start_idx],
                    "drawdown_pct": round(float(drawdowns[breaker_start_idx]), 2),
                    "peak_date": dates[peak_idx],
                    "peak_value": round(float(nav_arr[peak_idx]), 2),
                    "current_value": round(float(nav_arr[breaker_start_idx]), 2),
                    "recovery_date": dates[i],
                    "recovery_days": recovery_days,
                }
            )

    # 如果到最後還在熔斷狀態
    if in_breaker and breaker_start_idx is not None:
        circuit_breakers.append(
            {
                "date": dates[breaker_start_idx],
                "drawdown_pct": round(float(drawdowns[breaker_start_idx]), 2),
                "peak_date": dates[peak_idx],
                "peak_value": round(float(nav_arr[peak_idx]), 2),
                "current_value": round(float(nav_arr[breaker_start_idx]), 2),
                "recovery_date": None,
                "recovery_days": None,
            }
        )

    # 整體最大回撤
    max_dd_idx = int(np.argmax(drawdowns))
    max_dd_pct = float(drawdowns[max_dd_idx])

    return {
        "max_drawdown_pct": round(max_dd_pct, 2),
        "max_dd_date": dates[max_dd_idx],
        "circuit_breakers": circuit_breakers,
        "total_triggers": len(circuit_breakers),
        "would_stop_trading": max_dd_pct >= max_dd,
    }


# ============================================================
# 輔助函數 — 計算 ATR
# ============================================================


def calculate_atr(code: str, period: int = 14) -> float:
    """
    計算指定股票的 ATR（平均真實波幅）。

    參數:
        code: 股票代碼
        period: ATR 計算週期，默認 14 天

    返回:
        最新 ATR 值（如計算失敗返回 0）
    """
    try:
        from src.core.indicator_cache import cached_latest_atr

        return cached_latest_atr(code, period=period)
    except Exception as e:
        logger.debug(f"計算 ATR 失敗 {code}: {e}")
        return 0.0


def calculate_volatility(code: str, period: int = 20) -> float:
    """
    計算指定股票的年化波動率。

    參數:
        code: 股票代碼
        period: 計算週期，默認 20 天

    返回:
        年化波動率（如計算失敗返回 0）
    """
    try:
        df = load_daily_kline(code)
        if df.empty or len(df) < period + 1:
            return 0.0

        # 計算日收益率
        df = df.tail(period + 1).copy()
        returns = df["close"].pct_change().dropna()

        if len(returns) < period:
            return 0.0

        # 年化波動率 = 日波動率 × sqrt(252)
        daily_vol = float(returns.std())
        annual_vol = daily_vol * math.sqrt(252)
        return round(annual_vol, 4)
    except Exception as e:
        logger.debug(f"計算波動率失敗 {code}: {e}")
        return 0.0
