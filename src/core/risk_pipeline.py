"""
信號→風控→交易 管道

連接 SignalEngine（信號計算）、RiskManager（倉位/風控）、
和交易執行層，提供完整的「信號觸發 → 倉位計算 → 風險檢查 → 下單」流程。

核心類:
  RiskPipeline — 主管道，協調信號→風控→交易全流程
  TradeSignal  — 標準化的交易信號數據結構
  TradeOrder   — 經過風控後的最終下單指令
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

from src.config import settings
from src.core.risk_manager import (
    DrawdownProtector,
    PositionSizer,
    RiskBudget,
    calculate_atr,
    calculate_volatility,
)
from src.core.signals import SignalEngine
from src.utils.logger import logger

# ============================================================
# 數據結構
# ============================================================


class SignalType(str, Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class RiskRejectionReason(str, Enum):
    """風控拒絕原因"""

    DRAWDOWN_STOP = "drawdown_stop"  # 回撤觸發停止交易
    DRAWDOWN_REDUCE = "drawdown_reduce"  # 回撤觸發減倉
    BUDGET_EXCEEDED = "budget_exceeded"  # 風險預算超限
    POSITION_TOO_LARGE = "position_too_large"  # 單筆倉位過大
    INSUFFICIENT_FUNDS = "insufficient_funds"  # 資金不足
    MIN_LOT_NOT_MET = "min_lot_not_met"  # 不滿足最小交易單位
    SIGNAL_TOO_WEAK = "signal_too_weak"  # 信號強度不足
    KELLY_NEGATIVE = "kelly_negative"  # Kelly 倉位為負


@dataclass
class TradeSignal:
    """標準化交易信號"""

    code: str
    strategy: str
    signal: SignalType
    price: float
    strength: float = 0.0  # -100 ~ +100
    triggered_at: str = ""
    params: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict) -> "TradeSignal":
        return cls(
            code=d["code"],
            strategy=d["strategy"],
            signal=SignalType(d.get("signal", "hold")),
            price=float(d.get("price", 0)),
            strength=float(d.get("strength", 0)),
            triggered_at=d.get("triggered_at", ""),
            params=d.get("params", {}),
        )


@dataclass
class TradeOrder:
    """經過風控審核的最終下單指令"""

    code: str
    side: OrderSide
    shares: int  # 股數（A 股 100 的倍數）
    price: float  # 參考價格
    strategy: str  # 觸發策略
    signal_strength: float  # 原始信號強度
    position_value: float  # 倉位金額
    risk_status: str = "approved"  # approved / reduced / rejected
    rejection_reason: Optional[str] = None
    adjustments: dict = field(default_factory=dict)  # 風控調整明細
    created_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@dataclass
class PortfolioState:
    """當前組合狀態快照"""

    total_capital: float
    cash: float
    positions: dict = field(
        default_factory=dict
    )  # {code: {"shares": N, "value": X, "cost": C}}
    nav: float = 0.0
    current_drawdown_pct: float = 0.0
    peak_nav: float = 0.0

    @property
    def invested_value(self) -> float:
        return sum(p.get("value", 0) for p in self.positions.values())

    def update_nav(self, current_prices: dict[str, float]):
        """根據最新價格更新淨值"""
        invested = 0.0
        for code, pos in self.positions.items():
            price = current_prices.get(code, pos.get("cost", 0))
            pos["value"] = pos["shares"] * price
            invested += pos["value"]
        self.nav = self.cash + invested
        if self.nav > self.peak_nav:
            self.peak_nav = self.nav
        if self.peak_nav > 0:
            self.current_drawdown_pct = (self.peak_nav - self.nav) / self.peak_nav * 100


# ============================================================
# RiskPipeline — 核心管道
# ============================================================


class RiskPipeline:
    """
    信號→風控→交易 管道。

    流程:
      1. 接收多策略信號
      2. 信號聚合（加權投票）
      3. 倉位計算（ATR / Kelly / 波動率目標）
      4. 風險檢查（預算 / 回撤 / 最小單位）
      5. 輸出 TradeOrder

    用法:
        pipeline = RiskPipeline(total_capital=100000)
        orders = pipeline.process_signals(signals, current_prices)
    """

    def __init__(
        self,
        total_capital: float = None,
        max_risk_per_trade: float = 0.02,
        max_portfolio_risk: float = 0.15,
        max_single_risk: float = 0.05,
        max_drawdown_pct: float = 20.0,
        warning_drawdown_pct: float = 10.0,
        min_signal_strength: float = 10.0,
        sizing_method: str = "atr",  # atr / kelly / fixed / volatility
        fixed_fraction: float = 0.1,
        stamp_tax: float = None,
    ):
        self.total_capital = total_capital or settings.backtest_cash
        self.min_signal_strength = min_signal_strength
        self.sizing_method = sizing_method
        self.fixed_fraction = fixed_fraction
        self.stamp_tax = (
            stamp_tax if stamp_tax is not None else settings.backtest_stamp_tax
        )

        # 子組件
        self.sizer = PositionSizer(
            total_capital=self.total_capital,
            max_risk_per_trade=max_risk_per_trade,
        )
        self.risk_budget = RiskBudget(
            max_portfolio_risk=max_portfolio_risk,
            max_single_risk=max_single_risk,
        )
        self.drawdown_protector = DrawdownProtector(
            max_drawdown_pct=max_drawdown_pct,
            warning_pct=warning_drawdown_pct,
        )

        # 組合狀態
        self.portfolio = PortfolioState(
            total_capital=self.total_capital,
            cash=self.total_capital,
        )

        # 歷史統計（用於 Kelly）
        self._trade_stats: dict[str, dict] = (
            {}
        )  # strategy -> {wins, losses, total_pnl, ...}

    # ------ 主入口 ------

    def process_signals(
        self,
        signals: list[TradeSignal | dict],
        current_prices: dict[str, float],
        position_vols: dict[str, float] = None,
    ) -> list[TradeOrder]:
        """
        處理一批信號，輸出交易訂單。

        參數:
            signals: 多策略信號列表
            current_prices: {code: 當前價格}
            position_vols: {code: 年化波動率}（可選，用於風險預算）

        返回:
            TradeOrder 列表（含 approved / reduced / rejected）
        """
        if position_vols is None:
            position_vols = {}

        # 更新組合淨值
        self.portfolio.update_nav(current_prices)

        # 更新回撤保護器
        dd_state = self.drawdown_protector.update(self.portfolio.nav)

        orders = []

        # 按股票分組
        signals_by_code: dict[str, list[TradeSignal]] = {}
        for sig in signals:
            if isinstance(sig, dict):
                sig = TradeSignal.from_dict(sig)
            if sig.code not in signals_by_code:
                signals_by_code[sig.code] = []
            signals_by_code[sig.code].append(sig)

        for code, code_signals in signals_by_code.items():
            price = current_prices.get(code, 0)
            if price <= 0:
                continue

            # Step 1: 信號聚合
            aggregated = self._aggregate_signals(code_signals)
            if aggregated is None:
                continue

            signal_type, composite_strength, trigger_strategy = aggregated

            # Step 2: 回撤保護檢查
            if dd_state["status"] == "停止":
                if signal_type == SignalType.BUY:
                    orders.append(
                        TradeOrder(
                            code=code,
                            side=OrderSide.BUY,
                            shares=0,
                            price=price,
                            strategy=trigger_strategy,
                            signal_strength=composite_strength,
                            position_value=0,
                            risk_status="rejected",
                            rejection_reason=RiskRejectionReason.DRAWDOWN_STOP,
                            adjustments={"drawdown_pct": dd_state["current_dd"]},
                        )
                    )
                    continue

            # Step 3: 信號強度過濾
            if abs(composite_strength) < self.min_signal_strength:
                if signal_type != SignalType.HOLD:
                    orders.append(
                        TradeOrder(
                            code=code,
                            side=(
                                OrderSide.BUY
                                if signal_type == SignalType.BUY
                                else OrderSide.SELL
                            ),
                            shares=0,
                            price=price,
                            strategy=trigger_strategy,
                            signal_strength=composite_strength,
                            position_value=0,
                            risk_status="rejected",
                            rejection_reason=RiskRejectionReason.SIGNAL_TOO_WEAK,
                        )
                    )
                continue

            # Step 4: 計算倉位
            vol = position_vols.get(code, 0)
            position_value = self._calculate_position_size(
                code=code,
                price=price,
                signal_type=signal_type,
                strength=composite_strength,
                vol=vol,
                drawdown_multiplier=dd_state.get("position_multiplier", 1.0),
            )

            # Step 5: 風險預算檢查
            position_value = self._apply_risk_budget(code, position_value, vol)

            # Step 6: 轉換為股數，檢查最小單位
            if signal_type == SignalType.BUY:
                shares = int(position_value / price / 100) * 100
                if shares < 100:
                    orders.append(
                        TradeOrder(
                            code=code,
                            side=OrderSide.BUY,
                            shares=0,
                            price=price,
                            strategy=trigger_strategy,
                            signal_strength=composite_strength,
                            position_value=0,
                            risk_status="rejected",
                            rejection_reason=RiskRejectionReason.MIN_LOT_NOT_MET,
                            adjustments={
                                "calculated_value": position_value,
                                "min_lot": 100 * price,
                            },
                        )
                    )
                    continue
                # 檢查資金
                cost = shares * price * (1 + settings.backtest_commission)
                if cost > self.portfolio.cash:
                    shares = (
                        int(
                            self.portfolio.cash
                            / price
                            / (1 + settings.backtest_commission)
                            / 100
                        )
                        * 100
                    )
                    if shares < 100:
                        orders.append(
                            TradeOrder(
                                code=code,
                                side=OrderSide.BUY,
                                shares=0,
                                price=price,
                                strategy=trigger_strategy,
                                signal_strength=composite_strength,
                                position_value=0,
                                risk_status="rejected",
                                rejection_reason=RiskRejectionReason.INSUFFICIENT_FUNDS,
                            )
                        )
                        continue

                actual_value = shares * price
                reduction_applied = actual_value < position_value * 0.95

                order = TradeOrder(
                    code=code,
                    side=OrderSide.BUY,
                    shares=shares,
                    price=price,
                    strategy=trigger_strategy,
                    signal_strength=composite_strength,
                    position_value=actual_value,
                    risk_status="reduced" if reduction_applied else "approved",
                    adjustments={
                        "sizing_method": self.sizing_method,
                        "drawdown_multiplier": dd_state.get("position_multiplier", 1.0),
                        "original_value": round(position_value, 2),
                    },
                )
                orders.append(order)

            elif signal_type == SignalType.SELL:
                # 賣出：檢查是否持有
                pos = self.portfolio.positions.get(code)
                if not pos or pos.get("shares", 0) <= 0:
                    continue  # 無持倉，忽略賣出信號

                sell_shares = pos["shares"]
                # 印花稅（賣出時）
                commission = sell_shares * price * settings.backtest_commission
                stamp = sell_shares * price * self.stamp_tax
                sell_shares * price - commission - stamp

                order = TradeOrder(
                    code=code,
                    side=OrderSide.SELL,
                    shares=sell_shares,
                    price=price,
                    strategy=trigger_strategy,
                    signal_strength=composite_strength,
                    position_value=sell_shares * price,
                    risk_status="approved",
                    adjustments={
                        "commission": round(commission, 2),
                        "stamp_tax": round(stamp, 2),
                    },
                )
                orders.append(order)

        return orders

    # ------ 執行訂單（更新組合狀態）------

    def execute_order(self, order: TradeOrder):
        """
        執行已批准的訂單，更新組合狀態。
        在回測/模擬模式中直接調用；實盤模式中應在券商 API 確認後調用。
        """
        if order.risk_status == "rejected":
            return

        if order.side == OrderSide.BUY:
            cost = order.shares * order.price * (1 + settings.backtest_commission)
            self.portfolio.cash -= cost
            if order.code in self.portfolio.positions:
                pos = self.portfolio.positions[order.code]
                old_cost = pos["shares"] * pos["cost"]
                new_cost = order.shares * order.price
                pos["shares"] += order.shares
                pos["cost"] = (
                    (old_cost + new_cost) / pos["shares"] if pos["shares"] > 0 else 0
                )
            else:
                self.portfolio.positions[order.code] = {
                    "shares": order.shares,
                    "value": order.shares * order.price,
                    "cost": order.price,
                }

        elif order.side == OrderSide.SELL:
            commission = order.shares * order.price * settings.backtest_commission
            stamp = order.shares * order.price * self.stamp_tax
            proceeds = order.shares * order.price - commission - stamp
            self.portfolio.cash += proceeds
            pos = self.portfolio.positions.get(order.code)
            if pos:
                pos["shares"] -= order.shares
                if pos["shares"] <= 0:
                    del self.portfolio.positions[order.code]

        # 更新淨值
        self.portfolio.update_nav({})

    # ------ 內部方法 ------

    def _aggregate_signals(self, signals: list[TradeSignal]) -> Optional[tuple]:
        """
        聚合多策略信號。
        返回: (signal_type, composite_strength, trigger_strategy) 或 None
        """
        if not signals:
            return None

        # 加權投票
        buy_strength = sum(s.strength for s in signals if s.signal == SignalType.BUY)
        sell_strength = sum(
            abs(s.strength) for s in signals if s.signal == SignalType.SELL
        )

        buy_count = sum(1 for s in signals if s.signal == SignalType.BUY)
        sell_count = sum(1 for s in signals if s.signal == SignalType.SELL)

        # 一致性要求：至少 2 個策略同向，或單策略強度 > 60
        if buy_count > sell_count and buy_strength > 0:
            composite = min(
                100.0,
                buy_strength
                / max(buy_count, 1)
                * (0.5 + 0.5 * buy_count / len(signals)),
            )
            trigger = max(
                (s for s in signals if s.signal == SignalType.BUY),
                key=lambda s: s.strength,
            )
            return SignalType.BUY, round(composite, 2), trigger.strategy
        elif sell_count > buy_count and sell_strength > 0:
            composite = min(
                100.0,
                sell_strength
                / max(sell_count, 1)
                * (0.5 + 0.5 * sell_count / len(signals)),
            )
            trigger = max(
                (s for s in signals if s.signal == SignalType.SELL),
                key=lambda s: abs(s.strength),
            )
            return SignalType.SELL, round(-composite, 2), trigger.strategy
        else:
            return SignalType.HOLD, 0.0, ""

    def _calculate_position_size(
        self,
        code: str,
        price: float,
        signal_type: SignalType,
        strength: float,
        vol: float,
        drawdown_multiplier: float,
    ) -> float:
        """計算倉位金額"""
        if signal_type == SignalType.SELL:
            # 賣出時返回當前持倉價值
            pos = self.portfolio.positions.get(code)
            return pos["shares"] * price if pos else 0

        # 買入倉位計算
        base_value = 0.0

        if self.sizing_method == "atr":
            atr = calculate_atr(code)
            if atr > 0:
                risk_multiplier = max(
                    0.5, 2.0 - abs(strength) / 100.0
                )  # 信號越強，止損越緊
                shares = self.sizer.atr_based(atr, risk_multiplier)
                base_value = shares * price
            else:
                base_value = self.sizer.fixed_fraction(self.fixed_fraction)

        elif self.sizing_method == "kelly":
            stats = self._trade_stats.get(code, {})
            win_rate = stats.get("win_rate", 0.5)
            avg_win = stats.get("avg_win", 1.0)
            avg_loss = stats.get("avg_loss", 1.0)
            base_value = self.sizer.kelly_position(win_rate, avg_win, avg_loss)

        elif self.sizing_method == "volatility":
            if vol > 0:
                target_vol = 0.15
                current_position = self.portfolio.invested_value
                base_value = self.sizer.volatility_target(
                    target_vol, vol, current_position
                )
            else:
                base_value = self.sizer.fixed_fraction(self.fixed_fraction)

        else:  # fixed
            base_value = self.sizer.fixed_fraction(self.fixed_fraction)

        # 應用回撤縮放
        base_value *= drawdown_multiplier

        # 信號強度調整：強度越高，倉位越大（0.5x ~ 1.5x）
        strength_multiplier = 0.5 + abs(strength) / 100.0
        base_value *= strength_multiplier

        return base_value

    def _apply_risk_budget(self, code: str, position_value: float, vol: float) -> float:
        """風險預算檢查，必要時縮減倉位"""
        if vol <= 0:
            vol = calculate_volatility(code)
        if vol <= 0:
            return position_value  # 無法獲取波動率，跳過檢查

        # 構建當前持倉列表
        positions = []
        for c, pos in self.portfolio.positions.items():
            v = calculate_volatility(c)
            positions.append(
                {"code": c, "value": pos["shares"] * pos.get("cost", 0), "vol": v}
            )

        # 添加待建倉位
        positions.append({"code": code, "value": position_value, "vol": vol})

        # 檢查單個持倉
        total_value = self.portfolio.nav
        check = self.risk_budget.check_position(position_value, total_value, vol)

        if check.get("exceeds_limit"):
            reduction = check.get("suggested_reduction", 0)
            position_value = max(0, position_value - reduction)
            logger.debug(f"風險預算縮減 {code}: -{reduction:.0f}")

        return position_value

    # ------ 統計更新 ------

    def update_trade_stats(self, strategy: str, pnl: float):
        """更新策略交易統計（用於 Kelly 公式）"""
        if strategy not in self._trade_stats:
            self._trade_stats[strategy] = {
                "wins": 0,
                "losses": 0,
                "total_win": 0,
                "total_loss": 0,
            }
        stats = self._trade_stats[strategy]
        if pnl > 0:
            stats["wins"] += 1
            stats["total_win"] += pnl
        else:
            stats["losses"] += 1
            stats["total_loss"] += abs(pnl)

        total = stats["wins"] + stats["losses"]
        stats["win_rate"] = stats["wins"] / total if total > 0 else 0.5
        stats["avg_win"] = (
            stats["total_win"] / stats["wins"] if stats["wins"] > 0 else 1.0
        )
        stats["avg_loss"] = (
            stats["total_loss"] / stats["losses"] if stats["losses"] > 0 else 1.0
        )

    def get_state(self) -> dict:
        """返回當前管道狀態（用於 API / 調試）"""
        return {
            "total_capital": self.total_capital,
            "cash": round(self.portfolio.cash, 2),
            "nav": round(self.portfolio.nav, 2),
            "invested": round(self.portfolio.invested_value, 2),
            "drawdown_pct": round(self.portfolio.current_drawdown_pct, 2),
            "positions": {
                k: {
                    kk: round(vv, 2) if isinstance(vv, float) else vv
                    for kk, vv in v.items()
                }
                for k, v in self.portfolio.positions.items()
            },
            "drawdown_state": self.drawdown_protector.update(self.portfolio.nav),
            "sizing_method": self.sizing_method,
        }


# ============================================================
# 便捷函數
# ============================================================


def run_signal_pipeline(
    codes: list[str] = None,
    total_capital: float = None,
    sizing_method: str = "atr",
) -> dict:
    """
    一次性運行完整信號管道（便捷入口）。

    1. 計算所有股票的多策略信號
    2. 過管道風控
    3. 返回訂單列表 + 管道狀態

    用於 API 或定時任務。
    """
    if codes is None:
        codes = settings.watchlist
    if total_capital is None:
        total_capital = settings.backtest_cash

    # 計算信號
    engine = SignalEngine()
    engine.update_weights_from_backtest()
    raw_signals = engine.compute_signals(codes)

    # 獲取當前價格（從最新 K 線）
    from src.core.db import load_daily_kline

    current_prices = {}
    position_vols = {}
    for code in codes:
        df = load_daily_kline(code)
        if not df.empty:
            current_prices[code] = float(df.iloc[-1]["close"])
            position_vols[code] = calculate_volatility(code)

    # 過管道
    pipeline = RiskPipeline(
        total_capital=total_capital,
        sizing_method=sizing_method,
    )

    # 載入已有持倉（如有）
    orders = pipeline.process_signals(raw_signals, current_prices, position_vols)

    # 模擬執行 approved 訂單
    for order in orders:
        if order.risk_status in ("approved", "reduced"):
            pipeline.execute_order(order)

    return {
        "signals_count": len(raw_signals),
        "orders": [
            {
                "code": o.code,
                "side": o.side.value,
                "shares": o.shares,
                "price": o.price,
                "strategy": o.strategy,
                "strength": o.signal_strength,
                "value": round(o.position_value, 2),
                "status": o.risk_status,
                "rejection": o.rejection_reason,
                "adjustments": o.adjustments,
            }
            for o in orders
        ],
        "pipeline_state": pipeline.get_state(),
    }
