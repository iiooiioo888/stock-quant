"""
參數優化模塊 — 網格搜索 + Optuna 貝葉斯優化（支持並行）
"""
import itertools
import backtrader as bt
import pandas as pd
from concurrent.futures import ProcessPoolExecutor, as_completed
from src.core.db import load_daily_kline
from src.config import settings
from src.core.backtest import STRATEGIES, prepare_data
from src.utils.logger import logger


# 各策略參數搜索空間
PARAM_GRIDS = {
    "dual_ma": {"fast": [3, 5, 8, 10], "slow": [15, 20, 30, 40, 60]},
    "macd": {"fast": [8, 10, 12], "slow": [20, 26, 30], "signal": [7, 9, 11]},
    "bollinger": {"period": [10, 15, 20, 25, 30], "devfactor": [1.5, 2.0, 2.5, 3.0]},
    "kdj": {"period": [7, 9, 14, 19], "period_dfast": [3, 5], "period_dslow": [3, 5],
            "overbought": [70, 75, 80, 85], "oversold": [15, 20, 25, 30]},
    "rsi": {"period": [6, 10, 14, 20], "overbought": [65, 70, 75, 80], "oversold": [20, 25, 30, 35]},
    "grid": {"grid_pct": [1.0, 2.0, 3.0, 5.0], "position_pct": [0.05, 0.1, 0.15, 0.2]},
    "turtle": {"entry_period": [10, 15, 20, 30, 40], "exit_period": [5, 10, 15, 20],
               "atr_period": [10, 14, 20], "risk_pct": [0.5, 1.0, 1.5, 2.0]},
    "dual_thrust": {"period": [3, 4, 5, 7], "k_up": [0.3, 0.5, 0.7], "k_down": [0.3, 0.5, 0.7]},
    "momentum": {"lookback": [5, 10, 20, 30, 60], "hold_period": [3, 5, 10, 15]},
    "mean_reversion": {"period": [10, 15, 20, 30, 40], "entry_zscore": [-3.0, -2.5, -2.0, -1.5], "exit_zscore": [-0.5, 0.0, 0.5]},
    "volume_price": {"price_ma": [5, 10, 15, 20, 30], "volume_ma": [5, 10, 15, 20, 30], "volume_ratio": [1.5, 2.0, 2.5, 3.0]},
    "breakout": {"period": [20, 30, 40, 55, 70], "atr_period": [10, 14, 20], "atr_multiplier": [1.5, 2.0, 2.5, 3.0]},
    "composite": {"min_agreement": [2, 3, 4], "ma_fast": [3, 5, 8], "ma_slow": [15, 20, 30],
                  "rsi_period": [10, 14, 20], "rsi_overbought": [65, 70, 80], "rsi_oversold": [20, 25, 35],
                  "boll_period": [15, 20, 25], "boll_dev": [1.5, 2.0, 2.5]},
    "vwap": {"period": [10, 15, 20, 30], "deviation_pct": [0.5, 1.0, 1.5, 2.0]},
    "envelope": {"period": [10, 15, 20, 30, 40], "deviation_pct": [3, 5, 7, 10]},
    "parabolic_sar": {"af_start": [0.01, 0.02, 0.03], "af_step": [0.01, 0.02, 0.03], "af_max": [0.10, 0.15, 0.20, 0.25]},
    "obv": {"obv_ma_period": [10, 15, 20, 30], "price_ma_period": [10, 15, 20, 30]},
    "bollinger_squeeze": {"period": [15, 20, 25, 30], "devfactor": [1.5, 2.0, 2.5],
                          "squeeze_threshold": [0.02, 0.03, 0.04, 0.05], "squeeze_lookback": [3, 5, 8]},
    "adx_trend": {"adx_period": [10, 14, 20, 28], "adx_threshold": [20, 25, 30, 35], "di_period": [10, 14, 20]},
}

PARAM_RANGES = {
    "dual_ma": {"fast": (3, 15), "slow": (15, 80)},
    "macd": {"fast": (5, 15), "slow": (18, 35), "signal": (5, 15)},
    "bollinger": {"period": (8, 40), "devfactor": (1.0, 3.5)},
    "kdj": {"period": (5, 25), "period_dfast": (2, 7), "period_dslow": (2, 7),
            "overbought": (65, 90), "oversold": (10, 35)},
    "rsi": {"period": (5, 25), "overbought": (60, 85), "oversold": (15, 40)},
    "grid": {"grid_pct": (0.5, 8.0), "position_pct": (0.03, 0.3)},
    "turtle": {"entry_period": (8, 50), "exit_period": (4, 25), "atr_period": (8, 30), "risk_pct": (0.3, 3.0)},
    "dual_thrust": {"period": (2, 10), "k_up": (0.2, 1.0), "k_down": (0.2, 1.0)},
    "momentum": {"lookback": (3, 80), "hold_period": (2, 20)},
    "mean_reversion": {"period": (8, 50), "entry_zscore": (-3.5, -1.0), "exit_zscore": (-1.0, 1.0)},
    "volume_price": {"price_ma": (3, 40), "volume_ma": (3, 40), "volume_ratio": (1.2, 4.0)},
    "breakout": {"period": (10, 90), "atr_period": (8, 30), "atr_multiplier": (1.0, 4.0)},
    "composite": {"min_agreement": (2, 4), "ma_fast": (3, 12), "ma_slow": (15, 40),
                  "rsi_period": (8, 25), "rsi_overbought": (60, 85), "rsi_oversold": (15, 40),
                  "boll_period": (10, 30), "boll_dev": (1.0, 3.0)},
    "vwap": {"period": (5, 40), "deviation_pct": (0.3, 3.0)},
    "envelope": {"period": (5, 50), "deviation_pct": (2, 15)},
    "parabolic_sar": {"af_start": (0.005, 0.05), "af_step": (0.005, 0.05), "af_max": (0.05, 0.35)},
    "obv": {"obv_ma_period": (5, 40), "price_ma_period": (5, 40)},
    "bollinger_squeeze": {"period": (10, 40), "devfactor": (1.0, 3.5),
                          "squeeze_threshold": (0.01, 0.08), "squeeze_lookback": (2, 10)},
    "adx_trend": {"adx_period": (8, 35), "adx_threshold": (15, 40), "di_period": (8, 35)},
}


def _run_single(code: str, strategy_name: str, params: dict) -> dict:
    """用指定參數跑一次回測"""
    strategy_cls = STRATEGIES[strategy_name]
    cerebro = bt.Cerebro()
    cerebro.addstrategy(strategy_cls, **params)

    data = prepare_data(code)
    cerebro.adddata(data)

    cerebro.broker.setcash(settings.backtest_cash)
    cerebro.broker.setcommission(commission=settings.backtest_commission)

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
    sharpe_val = sharpe.get("sharperatio")

    return {
        "params": params,
        "total_return_pct": round(total_return, 4),
        "sharpe_ratio": sharpe_val if sharpe_val is not None else 0.0,
        "max_drawdown_pct": round(max_dd, 4),
        "total_trades": total_trades,
        "win_rate_pct": round(win_rate, 2),
        "final_value": final_value,
    }


def _score(result: dict, objective: str = "sharpe") -> float:
    """評分函數 — 0 交易返回大負數"""
    if result["total_trades"] == 0:
        return -9999.0

    if objective == "sharpe":
        return result["sharpe_ratio"]
    elif objective == "return":
        return result["total_return_pct"]
    elif objective == "calmar":
        dd = result["max_drawdown_pct"]
        if dd <= 0:
            return result["total_return_pct"]
        return result["total_return_pct"] / dd
    elif objective == "win_rate":
        return result["win_rate_pct"]
    return result["sharpe_ratio"]


def _add_oos_validation(results: list[dict], code: str, strategy_name: str, oos_ratio: float = 0.2) -> list[dict]:
    """
    對優化結果的 top N 做樣本外（Out-of-Sample）驗證。

    將數據按 oos_ratio 分為訓練集和測試集，在測試集上重新回測，
    添加 oos_return_pct、oos_sharpe、is_oos_positive 標注。
    """
    if not results:
        return results

    from src.core.db import load_daily_kline
    import pandas as pd

    df = load_daily_kline(code)
    if df.empty or len(df) < 100:
        return results

    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").set_index("date")

    split_idx = int(len(df) * (1 - oos_ratio))
    oos_df = df.iloc[split_idx:].copy()

    if len(oos_df) < 20:
        return results

    for r in results:
        params = r.get("params", {})
        try:
            from src.core.backtest import STRATEGIES
            strategy_cls = STRATEGIES[strategy_name]
            cerebro = bt.Cerebro()
            cerebro.addstrategy(strategy_cls, **params)

            bt_df = oos_df[["open", "high", "low", "close", "volume"]].copy()
            bt_df.columns = ["Open", "High", "Low", "Close", "Volume"]
            data_feed = bt.feeds.PandasData(dataname=bt_df)
            cerebro.adddata(data_feed)

            cerebro.broker.setcash(100000)
            cerebro.broker.setcommission(commission=0.001)
            cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe", riskfreerate=0.03)
            cerebro.addanalyzer(bt.analyzers.Returns, _name="returns")

            initial = cerebro.broker.getvalue()
            res = cerebro.run()
            final = cerebro.broker.getvalue()
            strat = res[0]

            oos_return = (final - initial) / initial * 100
            sharpe_data = strat.analyzers.sharpe.get_analysis()
            oos_sharpe = sharpe_data.get("sharperatio", 0) or 0

            r["oos_return_pct"] = round(oos_return, 4)
            r["oos_sharpe"] = round(oos_sharpe, 4)
            r["is_oos_positive"] = oos_return > 0
            r["oos_data_points"] = len(oos_df)
        except Exception:
            r["oos_return_pct"] = None
            r["oos_sharpe"] = None
            r["is_oos_positive"] = None
            r["oos_data_points"] = 0

    return results


def grid_search(
    code: str,
    strategy_name: str,
    objective: str = "sharpe",
    param_grid: dict = None,
    top_n: int = 10,
    verbose: bool = True,
) -> list[dict]:
    """網格搜索"""
    if strategy_name not in STRATEGIES:
        raise ValueError(f"未知策略: {strategy_name}")

    if param_grid is None:
        param_grid = PARAM_GRIDS.get(strategy_name)
        if param_grid is None:
            raise ValueError(f"策略 {strategy_name} 無默認搜索空間")

    keys = list(param_grid.keys())
    combos = list(itertools.product(*param_grid.values()))

    valid_combos = []
    for vals in combos:
        p = dict(zip(keys, vals))
        if "fast" in p and "slow" in p and p["fast"] >= p["slow"]:
            continue
        if "ma_fast" in p and "ma_slow" in p and p["ma_fast"] >= p["ma_slow"]:
            continue
        if "entry_period" in p and "exit_period" in p and p["entry_period"] <= p["exit_period"]:
            continue
        if "overbought" in p and "oversold" in p and p["overbought"] <= p["oversold"]:
            continue
        if "rsi_overbought" in p and "rsi_oversold" in p and p["rsi_overbought"] <= p["rsi_oversold"]:
            continue
        if "min_agreement" in p and p["min_agreement"] > 4:
            continue
        valid_combos.append(p)

    total = len(valid_combos)
    logger.info(f"網格搜索 {code}/{strategy_name}: {total} 種組合, 目標={objective}")

    results = []
    for i, params in enumerate(valid_combos, 1):
        try:
            r = _run_single(code, strategy_name, params)
            r["score"] = _score(r, objective)
            results.append(r)
            if verbose and i % 10 == 0:
                logger.info(f"  進度: {i}/{total}")
        except Exception as e:
            logger.warning(f"  組合 {params} 失敗: {e}")

    results.sort(key=lambda x: x["score"], reverse=True)
    top_results = results[:top_n]

    # 樣本外驗證：對 top 結果在最後 20% 數據上重新回測
    try:
        top_results = _add_oos_validation(top_results, code, strategy_name)
    except Exception as e:
        logger.debug(f"OOS 驗證跳過: {e}")

    return top_results


def optuna_search(
    code: str,
    strategy_name: str,
    objective: str = "sharpe",
    n_trials: int = 100,
    param_ranges: dict = None,
    verbose: bool = True,
) -> list[dict]:
    """Optuna 貝葉斯優化"""
    import optuna
    import threading

    if strategy_name not in STRATEGIES:
        raise ValueError(f"未知策略: {strategy_name}")

    if param_ranges is None:
        param_ranges = PARAM_RANGES.get(strategy_name)
        if param_ranges is None:
            raise ValueError(f"策略 {strategy_name} 無默認搜索範圍")

    optuna.logging.set_verbosity(
        optuna.logging.INFO if verbose else optuna.logging.WARNING
    )

    logger.info(f"Optuna 優化 {code}/{strategy_name}: {n_trials} 次試驗, 目標={objective}")

    all_results = []
    results_lock = threading.Lock()

    def _objective(trial):
        params = {}
        for name, (lo, hi) in param_ranges.items():
            if isinstance(lo, int) and isinstance(hi, int):
                params[name] = trial.suggest_int(name, lo, hi)
            else:
                params[name] = trial.suggest_float(name, lo, hi)

        if "fast" in params and "slow" in params and params["fast"] >= params["slow"]:
            return float("-inf")
        if "ma_fast" in params and "ma_slow" in params and params["ma_fast"] >= params["ma_slow"]:
            return float("-inf")
        if "entry_period" in params and "exit_period" in params and params["entry_period"] <= params["exit_period"]:
            return float("-inf")
        if "overbought" in params and "oversold" in params and params["overbought"] <= params["oversold"]:
            return float("-inf")
        if "rsi_overbought" in params and "rsi_oversold" in params and params["rsi_overbought"] <= params["rsi_oversold"]:
            return float("-inf")
        if "min_agreement" in params and params["min_agreement"] > 4:
            return float("-inf")

        try:
            r = _run_single(code, strategy_name, params)
            r["score"] = _score(r, objective)
            with results_lock:
                all_results.append(r)
            return r["score"]
        except Exception:
            return float("-inf")

    study = optuna.create_study(direction="maximize")
    study.optimize(_objective, n_trials=n_trials, show_progress_bar=verbose, n_jobs=2)

    seen = set()
    unique_results = []
    for r in sorted(all_results, key=lambda x: x["score"], reverse=True):
        key = str(sorted(r["params"].items()))
        if key not in seen:
            seen.add(key)
            unique_results.append(r)

    logger.info(f"Optuna 完成: {len(unique_results)} 組唯一結果")
    top_results = unique_results[:10]

    # 樣本外驗證：對 top 結果在最後 20% 數據上重新回測
    try:
        top_results = _add_oos_validation(top_results, code, strategy_name)
    except Exception as e:
        logger.debug(f"OOS 驗證跳過: {e}")

    return top_results


def optimize_all(
    code: str,
    objective: str = "sharpe",
    method: str = "grid",
    n_trials: int = 80,
    top_n: int = 5,
    verbose: bool = True,
) -> dict:
    """對所有策略做參數優化"""
    all_results = {}

    for name in STRATEGIES:
        logger.info(f"優化策略: {name}")
        try:
            if method == "optuna":
                results = optuna_search(code, name, objective=objective, n_trials=n_trials, verbose=verbose)
            else:
                results = grid_search(code, name, objective=objective, top_n=top_n, verbose=verbose)
            all_results[name] = results
        except Exception as e:
            logger.error(f"{name} 優化失敗: {e}")
            all_results[name] = []

    return all_results


# ============================================================
# 並行網格搜索（ProcessPoolExecutor）
# ============================================================

def _run_single_worker(args):
    """Worker 函數，用於 ProcessPoolExecutor"""
    code, strategy_name, params = args
    try:
        r = _run_single(code, strategy_name, params)
        return r
    except Exception:
        return None


def grid_search_parallel(
    code: str,
    strategy_name: str,
    objective: str = "sharpe",
    param_grid: dict = None,
    top_n: int = 10,
    max_workers: int = 4,
    verbose: bool = True,
) -> list[dict]:
    """並行網格搜索 — 使用 ProcessPoolExecutor"""
    if strategy_name not in STRATEGIES:
        raise ValueError(f"未知策略: {strategy_name}")

    if param_grid is None:
        param_grid = PARAM_GRIDS.get(strategy_name)
        if param_grid is None:
            raise ValueError(f"策略 {strategy_name} 無默認搜索空間")

    keys = list(param_grid.keys())
    combos = list(itertools.product(*param_grid.values()))

    valid_combos = []
    for vals in combos:
        p = dict(zip(keys, vals))
        if "fast" in p and "slow" in p and p["fast"] >= p["slow"]:
            continue
        if "ma_fast" in p and "ma_slow" in p and p["ma_fast"] >= p["ma_slow"]:
            continue
        if "entry_period" in p and "exit_period" in p and p["entry_period"] <= p["exit_period"]:
            continue
        if "overbought" in p and "oversold" in p and p["overbought"] <= p["oversold"]:
            continue
        if "rsi_overbought" in p and "rsi_oversold" in p and p["rsi_overbought"] <= p["rsi_oversold"]:
            continue
        if "min_agreement" in p and p["min_agreement"] > 4:
            continue
        valid_combos.append(p)

    total = len(valid_combos)
    logger.info(f"並行網格搜索 {code}/{strategy_name}: {total} 種組合, workers={max_workers}")

    tasks = [(code, strategy_name, p) for p in valid_combos]
    results = []
    done = 0

    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_run_single_worker, t): t for t in tasks}
        for future in as_completed(futures):
            done += 1
            try:
                r = future.result()
                if r is not None:
                    r["score"] = _score(r, objective)
                    results.append(r)
            except Exception as e:
                logger.debug(f"  Worker 失敗: {e}")

            if verbose and done % 50 == 0:
                logger.info(f"  並行網格進度: {done}/{total}")

    results.sort(key=lambda x: x["score"], reverse=True)
    top_results = results[:top_n]

    # 樣本外驗證
    try:
        top_results = _add_oos_validation(top_results, code, strategy_name)
    except Exception as e:
        logger.debug(f"OOS 驗證跳過: {e}")

    return top_results