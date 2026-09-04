"""
向量化回測 — 均線 / MACD / RSI / 布林 / 動量等全倉多頭快路徑。

用於大規模日頻回測；繪圖、倉位上限、沙箱仍走 Backtrader。止損/止盈/移動止損在向量化路徑內處理。
停牌（成交量為 0）當日不開新倉、不強制平倉。
成交模擬走 Numba（無則同等 Python）。
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from src.config import settings
from src.core.indicators.fast_indicators import (
    compute_bollinger,
    compute_ema,
    compute_macd,
    compute_rsi,
    compute_sma,
)
from src.core.strategies import STRATEGY_NAMES
from src.core.vectorized_sim import simulate_long
from src.utils.logger import logger

VECTORIZED_STRATEGIES = frozenset(
    {"dual_ma", "macd", "rsi", "ema_cross", "bollinger", "momentum", "triple_ma"}
)


def can_use_vectorized(
    strategy_name: str,
    *,
    plot: bool = False,
    stop_loss_pct: Optional[float] = None,
    take_profit_pct: Optional[float] = None,
    trailing_stop_pct: Optional[float] = None,
    max_position_pct: Optional[float] = None,
    sandbox_mode: bool = False,
    engine: Optional[str] = None,
) -> bool:
    pref = (engine or getattr(settings, "backtest_engine", "auto") or "auto").lower()
    if pref == "backtrader":
        return False
    if strategy_name not in VECTORIZED_STRATEGIES:
        return False
    if plot or sandbox_mode:
        return False
    if max_position_pct is not None and 0 < float(max_position_pct) < 1:
        return False
    if pref == "vectorized":
        return True
    return True  # auto


def _limit_pct(code: str) -> float:
    c = str(code)
    if c.startswith("688") or c.startswith("300"):
        return 0.20
    return 0.10


def _cross(a: np.ndarray, b: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    up = (a > b) & (np.roll(a, 1) <= np.roll(b, 1))
    dn = (a < b) & (np.roll(a, 1) >= np.roll(b, 1))
    up[0] = False
    dn[0] = False
    nan = np.isnan(a) | np.isnan(b) | np.isnan(np.roll(a, 1)) | np.isnan(np.roll(b, 1))
    up[nan] = False
    dn[nan] = False
    return up, dn


def _signals(strategy: str, close: np.ndarray, params: dict) -> tuple[np.ndarray, np.ndarray]:
    """返回 (want_buy, want_sell) bool 陣列，長度 = n。"""
    n = len(close)
    buy = np.zeros(n, dtype=bool)
    sell = np.zeros(n, dtype=bool)
    p = params or {}
    if strategy == "dual_ma":
        buy, sell = _cross(compute_sma(close, int(p.get("fast", 5))), compute_sma(close, int(p.get("slow", 20))))
    elif strategy == "ema_cross":
        buy, sell = _cross(compute_ema(close, int(p.get("fast", 12))), compute_ema(close, int(p.get("slow", 26))))
    elif strategy == "triple_ma":
        f = compute_sma(close, int(p.get("fast", 5)))
        m = compute_sma(close, int(p.get("mid", 10)))
        s = compute_sma(close, int(p.get("slow", 20)))
        bull = (f > m) & (m > s)
        prev = np.roll(bull, 1)
        buy = bull & (~prev)
        sell = (~bull) & prev
        buy[0] = False
        sell[0] = False
    elif strategy == "macd":
        line, sig, _ = compute_macd(
            close, int(p.get("fast", 12)), int(p.get("slow", 26)), int(p.get("signal", 9))
        )
        buy, sell = _cross(line, sig)
    elif strategy == "rsi":
        period = int(p.get("period", 14))
        ob = float(p.get("overbought", 70))
        os_ = float(p.get("oversold", 30))
        rsi = compute_rsi(close, period)
        prev = np.roll(rsi, 1)
        buy = (prev < os_) & (rsi >= os_)
        sell = (prev > ob) & (rsi <= ob)
        buy[0] = False
        sell[0] = False
    elif strategy == "bollinger":
        up, _mid, lo = compute_bollinger(close, int(p.get("period", 20)), float(p.get("devfactor", 2.0)))
        buy = close < lo
        sell = close > up
        nan = np.isnan(lo) | np.isnan(up)
        buy[nan] = False
        sell[nan] = False
    elif strategy == "momentum":
        lb = int(p.get("lookback", 20))
        roc = np.full(n, np.nan)
        if lb > 0 and n > lb:
            roc[lb:] = close[lb:] / close[: n - lb] - 1.0
        prev = np.roll(roc, 1)
        buy = (prev <= 0) & (roc > 0)
        sell = (prev >= 0) & (roc < 0)
        buy[0] = False
        sell[0] = False
        nan = np.isnan(roc) | np.isnan(prev)
        buy[nan] = False
        sell[nan] = False
    return buy, sell


def run_vectorized_backtest(
    code: str,
    strategy_name: str = "dual_ma",
    params: dict = None,
    cash: float = None,
    commission: float = None,
    slippage_pct: float = 0.0,
    volume_slippage: bool = None,
    order_size_shares: int = 0,
    enable_t1: bool = True,
    enable_limit: bool = True,
    timeframe: str = "1d",
    adj: str = None,
    task_id: str = None,
    user_id: int = None,
    benchmark: bool = False,
    stop_loss_pct: float = None,
    take_profit_pct: float = None,
    trailing_stop_pct: float = None,
) -> dict:
    from src.core.backtest import (
        _calc_risk_metrics,
        _format_bar_datetime,
        _get_prepared_df,
        _max_drawdown_pct_from_nav,
        analyze_equity_curve,
    )
    from src.core.backtest_runtime import compute_volume_impact_slippage_pct
    from src.core.kline_timeframe import (
        bars_per_year as tf_bars_per_year,
    )
    from src.core.kline_timeframe import (
        normalize_adj,
        normalize_timeframe,
        timeframe_label,
    )

    tf = normalize_timeframe(timeframe)
    bpy = tf_bars_per_year(tf)
    tf_label = timeframe_label(tf)
    adj_n = normalize_adj(adj or getattr(settings, "backtest_adj", "qfq"))
    if cash is None:
        cash = settings.backtest_cash
    if commission is None:
        commission = settings.backtest_commission

    if task_id:
        from src.core.task_manager import is_task_cancelled, update_task

        if is_task_cancelled(task_id):
            raise RuntimeError("任務已取消")
        update_task(task_id, progress=15)

    df = _get_prepared_df(code, timeframe=tf, adj=adj_n)
    close = df["Close"].to_numpy(dtype=np.float64)
    high = df["High"].to_numpy(dtype=np.float64)
    low = df["Low"].to_numpy(dtype=np.float64)
    vol = df["Volume"].to_numpy(dtype=np.float64) if "Volume" in df.columns else np.ones(len(df))
    n = len(close)
    if n < 5:
        raise ValueError(f"數據不足：{code} 僅 {n} 條 K 線")

    want_buy, want_sell = _signals(strategy_name, close, params or {})

    use_volume_slip = (
        volume_slippage
        if volume_slippage is not None
        else getattr(settings, "volume_slippage_enabled", False)
    )
    slip = (slippage_pct / 100.0) if slippage_pct > 0 else 0.0
    part_cap = float(getattr(settings, "volume_slippage_participation_cap", 0.05) or 0.05)
    if use_volume_slip and slippage_pct > 0:
        bar_vol = float(vol[-1]) if n else 0.0
        est = float(order_size_shares or 100)
        effective_slip_pct = compute_volume_impact_slippage_pct(
            slippage_pct, est, bar_vol, participation_cap=part_cap
        )
    else:
        effective_slip_pct = slippage_pct
    lim = _limit_pct(code)
    dates = [_format_bar_datetime(df.index[i]) for i in range(n)]
    wb = want_buy.astype(np.int8)
    ws = want_sell.astype(np.int8)
    (
        equity,
        n_paired,
        buy_i,
        sell_i,
        buy_px,
        sell_px,
        sizes,
        pnls,
        blocked_buys,
        blocked_sells,
        t1_blocked,
        halt_bars,
        shares,
        _cash_end,
        _buy_bar_end,
    ) = simulate_long(
        close,
        vol,
        wb,
        ws,
        float(cash),
        float(commission),
        float(getattr(settings, "backtest_min_commission", 5.0) or 0),
        float(getattr(settings, "backtest_stamp_tax", 0.0005) or 0),
        float(getattr(settings, "backtest_transfer_fee", 0.00001) or 0),
        float(slip),
        np.int8(1 if use_volume_slip else 0),
        part_cap,
        2.0,
        np.int64(int(order_size_shares or 0)),
        np.int8(1 if enable_t1 else 0),
        np.int8(1 if enable_limit else 0),
        float(lim),
        high,
        low,
        float(stop_loss_pct or 0) / 100.0,
        float(take_profit_pct or 0) / 100.0,
        float(trailing_stop_pct or 0) / 100.0,
    )
    paired = []
    trade_log = []
    for k in range(int(n_paired)):
        bi = int(buy_i[k])
        si = int(sell_i[k])
        bp = float(buy_px[k])
        sp = float(sell_px[k])
        sz = int(sizes[k])
        pnl = float(pnls[k])
        trade_log.append({"date": dates[bi], "type": "open", "price": round(bp, 2), "size": sz})
        trade_log.append({"date": dates[si], "type": "close", "price": round(sp, 2), "size": sz})
        paired.append(
            {
                "buy_date": dates[bi],
                "buy_price": round(bp, 2),
                "sell_date": dates[si],
                "sell_price": round(sp, 2),
                "size": sz,
                "pnl": round(pnl, 2),
                "hold_days": si - bi,
                "return_pct": round(pnl / (bp * sz) * 100, 2) if bp and sz else 0,
            }
        )

    if task_id:
        from src.core.task_manager import update_task

        update_task(task_id, progress=80)

    initial = float(cash)
    final_value = float(equity[-1])
    total_return = (final_value - initial) / initial * 100
    nav = (equity / initial).tolist()
    daily_returns = [0.0]
    for i in range(1, n):
        prev_e = equity[i - 1]
        daily_returns.append(float((equity[i] - prev_e) / prev_e) if prev_e else 0.0)
    # nav 與 dates 對齊：第一根淨值已含當日權益
    max_dd = _max_drawdown_pct_from_nav(nav)
    if len(daily_returns) > 1:
        dr = np.array(daily_returns[1:], dtype=float)
        std = float(np.std(dr))
        mean = float(np.mean(dr))
        sharpe = (mean - 0.03 / bpy) / std * (bpy**0.5) if std > 0 else 0.0
    else:
        sharpe = 0.0

    won = sum(1 for t in paired if t["pnl"] > 0)
    lost = sum(1 for t in paired if t["pnl"] <= 0)
    total_trades = len(paired)
    win_rate = (won / total_trades * 100) if total_trades else 0
    risk = _calc_risk_metrics(daily_returns[1:] or daily_returns, dates[1:] or dates, max_dd, nav, periods_per_year=bpy)
    equity_analysis = analyze_equity_curve(nav, dates, daily_returns)

    kline = []
    start_k = max(0, n - 800)
    for i in range(start_k, n):
        row = df.iloc[i]
        kline.append(
            {
                "date": dates[i],
                "open": round(float(row["Open"]), 2),
                "high": round(float(high[i]), 2),
                "low": round(float(low[i]), 2),
                "close": round(float(close[i]), 2),
                "volume": int(vol[i]) if not np.isnan(vol[i]) else 0,
            }
        )

    signals = [
        {"date": t["date"], "type": "buy" if t["type"] == "open" else "sell", "price": t["price"]}
        for t in trade_log
    ]

    stamp_tax_rate = settings.backtest_stamp_tax
    result = {
        "code": code,
        "strategy": strategy_name,
        "strategy_name": STRATEGY_NAMES.get(strategy_name, strategy_name),
        "engine": "vectorized",
        "timeframe": tf,
        "timeframe_label": tf_label,
        "adj": adj_n,
        "commission": commission,
        "min_commission": float(getattr(settings, "backtest_min_commission", 5.0) or 0),
        "stamp_tax": stamp_tax_rate,
        "transfer_fee": float(getattr(settings, "backtest_transfer_fee", 0.00001) or 0),
        "bars_count": n,
        "initial_cash": cash,
        "final_value": round(final_value, 4),
        "total_return_pct": round(total_return, 4),
        "sharpe_ratio": round(sharpe, 4),
        "max_drawdown_pct": round(max_dd, 4),
        "total_trades": total_trades,
        "won_trades": won,
        "lost_trades": lost,
        "win_rate_pct": round(win_rate, 2),
        "nav": [round(v, 6) for v in nav],
        "dates": dates,
        "equity_curve": [{"date": dates[i], "value": round(float(nav[i]), 6)} for i in range(n)],
        "daily_returns": [round(r, 6) for r in daily_returns],
        "trade_details": paired,
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
        "slippage_pct": slippage_pct,
        "effective_slippage_pct": round(effective_slip_pct, 6),
        "volume_slippage": bool(use_volume_slip),
        "enable_t1": enable_t1,
        "enable_limit": enable_limit,
        "limit_filter": {
            "blocked_buys": int(blocked_buys),
            "blocked_sells": int(blocked_sells),
            "limit_pct": lim,
        },
        "t1_filter": {"blocked_sells": int(t1_blocked), "tracked_positions": 1 if int(shares) else 0},
        "halt_bars": int(halt_bars),
        "equity_analysis": equity_analysis,
        "user_id": user_id,
    }

    try:
        from src.core.db import save_backtest_result

        save_backtest_result(result)
    except Exception as e:
        logger.debug(f"保存回測結果跳過: {e}")

    if benchmark:
        try:
            from src.core.benchmark import compare_with_benchmark

            result["benchmark"] = compare_with_benchmark(result)
        except Exception as e:
            logger.debug(f"基準對比跳過: {e}")

    logger.info(
        f"向量化回測 {code}/{strategy_name}: 收益 {total_return:.2f}%, 回撤 {max_dd:.2f}%, 交易 {total_trades} 次"
    )
    return result
