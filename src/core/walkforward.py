"""
Walk-Forward 分析 — 滾動窗口訓練+測試，檢測過擬合
使用內存 DataFrame 直接回測，避免重複寫 DB
"""

import backtrader as bt
import numpy as np
import pandas as pd

from src.core.backtest import STRATEGIES
from src.core.db import load_daily_kline
from src.core.optimize import PARAM_RANGES
from src.utils.logger import logger


def _run_backtest_on_df(
    df: pd.DataFrame, strategy_name: str, params: dict, cash: float = 100000
) -> dict:
    """直接在 DataFrame 上跑回測（不經過 DB）"""
    strategy_cls = STRATEGIES[strategy_name]
    cerebro = bt.Cerebro()
    cerebro.addstrategy(strategy_cls, **params)

    # 直接用 DataFrame 構建 data feed
    bt_df = df[["open", "high", "low", "close", "volume"]].copy()
    bt_df.columns = ["Open", "High", "Low", "Close", "Volume"]
    bt_df.index = pd.to_datetime(
        bt_df.index if bt_df.index.name == "date" else df["date"]
    )
    data_feed = bt.feeds.PandasData(dataname=bt_df)
    cerebro.adddata(data_feed)

    cerebro.broker.setcash(cash)
    cerebro.broker.setcommission(commission=0.001)
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe", riskfreerate=0.03)
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")

    initial_value = cerebro.broker.getvalue()
    results = cerebro.run()
    final_value = cerebro.broker.getvalue()
    strat = results[0]

    sharpe = strat.analyzers.sharpe.get_analysis()
    drawdown = strat.analyzers.drawdown.get_analysis()
    trades = strat.analyzers.trades.get_analysis()

    total_return = (final_value - initial_value) / initial_value * 100
    max_dd = drawdown.get("max", {}).get("drawdown", 0)
    total_trades = trades.get("total", {}).get("total", 0)
    won = trades.get("won", {}).get("total", 0)
    win_rate = (won / total_trades * 100) if total_trades > 0 else 0
    sharpe_val = sharpe.get("sharperatio", 0) or 0

    return {
        "total_return_pct": round(total_return, 4),
        "sharpe_ratio": sharpe_val,
        "max_drawdown_pct": round(max_dd, 4),
        "total_trades": total_trades,
        "win_rate_pct": round(win_rate, 2),
    }


def _optuna_on_df(
    df: pd.DataFrame,
    strategy_name: str,
    param_ranges: dict,
    objective: str,
    n_trials: int,
) -> dict:
    """在 DataFrame 上做 Optuna 優化（不經過 DB）"""
    import optuna

    def _objective(trial):
        params = {}
        for name, (lo, hi) in param_ranges.items():
            if isinstance(lo, int) and isinstance(hi, int):
                params[name] = trial.suggest_int(name, lo, hi)
            else:
                params[name] = trial.suggest_float(name, lo, hi)

        # 約束
        if "fast" in params and "slow" in params and params["fast"] >= params["slow"]:
            return float("-inf")
        if (
            "entry_period" in params
            and "exit_period" in params
            and params["entry_period"] <= params["exit_period"]
        ):
            return float("-inf")
        if (
            "overbought" in params
            and "oversold" in params
            and params["overbought"] <= params["oversold"]
        ):
            return float("-inf")

        try:
            r = _run_backtest_on_df(df, strategy_name, params)
            if r["total_trades"] == 0:
                return float("-inf")
            if objective == "sharpe":
                return r["sharpe_ratio"]
            elif objective == "return":
                return r["total_return_pct"]
            elif objective == "calmar":
                return (
                    r["total_return_pct"] / r["max_drawdown_pct"]
                    if r["max_drawdown_pct"] > 0
                    else r["total_return_pct"]
                )
            return r["sharpe_ratio"]
        except Exception:
            return float("-inf")

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    study = optuna.create_study(direction="maximize")
    study.optimize(_objective, n_trials=n_trials, show_progress_bar=False)

    best = study.best_params
    for k, v in best.items():
        if k in param_ranges:
            lo, hi = param_ranges[k]
            if isinstance(lo, int) and isinstance(hi, int):
                best[k] = int(v)
    return best


def walk_forward(
    code: str,
    strategy_name: str,
    train_days: int = 750,
    test_days: int = 250,
    step_days: int = 250,
    objective: str = "sharpe",
    n_trials: int = 50,
) -> dict:
    """
    Walk-Forward 分析

    1. 將數據分割為滾動窗口 [train_start, train_end, test_start, test_end]
    2. 每個窗口: 在訓練集上做 Optuna 優化，在測試集上評估
    3. 全程使用內存 DataFrame，不寫 DB
    """
    if strategy_name not in STRATEGIES:
        raise ValueError(f"未知策略: {strategy_name}")

    param_ranges = PARAM_RANGES.get(strategy_name)
    if not param_ranges:
        raise ValueError(f"策略 {strategy_name} 無搜索範圍")

    # 獲取所有數據
    df = load_daily_kline(code)
    if df.empty:
        raise ValueError(f"股票 {code} 無數據")

    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").set_index("date")
    total_days = len(df)

    if total_days < train_days + test_days:
        raise ValueError(
            f"數據不足: 需要 {train_days + test_days} 天，只有 {total_days} 天"
        )

    # 生成滾動窗口
    windows = []
    start_idx = 0
    dates = df.index.tolist()
    while start_idx + train_days + test_days <= total_days:
        windows.append(
            {
                "train_start": str(dates[start_idx].date()),
                "train_end": str(dates[start_idx + train_days - 1].date()),
                "test_start": str(dates[start_idx + train_days].date()),
                "test_end": str(
                    dates[
                        min(start_idx + train_days + test_days - 1, total_days - 1)
                    ].date()
                ),
                "train_slice": slice(start_idx, start_idx + train_days),
                "test_slice": slice(
                    start_idx + train_days, start_idx + train_days + test_days
                ),
            }
        )
        start_idx += step_days

    if not windows:
        raise ValueError("無法生成有效窗口")

    logger.info(f"Walk-Forward {code}/{strategy_name}: {len(windows)} 個窗口")

    window_results = []

    for wi, w in enumerate(windows):
        logger.info(
            f"  窗口 {wi+1}/{len(windows)}: train={w['train_start']}~{w['train_end']}, test={w['test_start']}~{w['test_end']}"
        )

        train_df = df.iloc[w["train_slice"]].copy()
        test_df = df.iloc[w["test_slice"]].copy()

        # 在訓練集上做 Optuna（直接用 DataFrame，不寫 DB）
        best_params = _optuna_on_df(
            train_df, strategy_name, param_ranges, objective, n_trials
        )

        # 在測試集上評估
        test_result = _run_backtest_on_df(test_df, strategy_name, best_params)

        window_results.append(
            {
                "window": wi + 1,
                "train_period": f"{w['train_start']} ~ {w['train_end']}",
                "test_period": f"{w['test_start']} ~ {w['test_end']}",
                "best_params": best_params,
                "train_score": None,
                "test_return_pct": test_result["total_return_pct"],
                "test_sharpe": test_result["sharpe_ratio"],
                "test_max_dd_pct": test_result["max_drawdown_pct"],
                "test_trades": test_result["total_trades"],
                "test_win_rate": test_result["win_rate_pct"],
            }
        )

    # 聚合結果
    test_returns = [w["test_return_pct"] for w in window_results]
    test_sharpes = [w["test_sharpe"] for w in window_results if w["test_sharpe"]]

    avg_oos_return = float(np.mean(test_returns)) if test_returns else 0
    avg_oos_sharpe = float(np.mean(test_sharpes)) if test_sharpes else 0
    std_oos_return = float(np.std(test_returns)) if len(test_returns) > 1 else 0

    if abs(avg_oos_return) > 0:
        stability = max(0, min(1, 1 - std_oos_return / abs(avg_oos_return)))
    else:
        stability = 0

    positive_windows = sum(1 for r in test_returns if r > 0)
    overfit_ratio = 1 - (positive_windows / len(test_returns)) if test_returns else 1

    result = {
        "code": code,
        "strategy": strategy_name,
        "train_days": train_days,
        "test_days": test_days,
        "step_days": step_days,
        "objective": objective,
        "n_windows": len(windows),
        "windows": window_results,
        "avg_oos_return_pct": round(avg_oos_return, 4),
        "avg_oos_sharpe": round(avg_oos_sharpe, 4),
        "std_oos_return_pct": round(std_oos_return, 4),
        "stability_score": round(stability, 4),
        "overfit_ratio": round(overfit_ratio, 4),
        "positive_windows": positive_windows,
        "total_windows": len(test_returns),
    }

    logger.info(
        f"Walk-Forward 完成: avg_oos={avg_oos_return:.2f}%, "
        f"stability={stability:.2f}, overfit={overfit_ratio:.2f}"
    )

    return result
