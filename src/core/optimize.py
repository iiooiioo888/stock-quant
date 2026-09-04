"""
參數優化模塊 — 網格搜索 + Optuna 貝葉斯優化（支持並行）
"""

import itertools
import sys
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed

import backtrader as bt
import pandas as pd

from src.config import settings
from src.core.backtest import STRATEGIES, prepare_data
from src.core.db import load_daily_kline
from src.utils.logger import logger

# 各策略參數搜索空間
PARAM_GRIDS = {
    "dual_ma": {"fast": [3, 5, 8, 10], "slow": [15, 20, 30, 40, 60]},
    "macd": {"fast": [8, 10, 12], "slow": [20, 26, 30], "signal": [7, 9, 11]},
    "bollinger": {"period": [10, 15, 20, 25, 30], "devfactor": [1.5, 2.0, 2.5, 3.0]},
    "kdj": {
        "period": [7, 9, 14, 19],
        "period_dfast": [3, 5],
        "period_dslow": [3, 5],
        "overbought": [70, 75, 80, 85],
        "oversold": [15, 20, 25, 30],
    },
    "rsi": {
        "period": [6, 10, 14, 20],
        "overbought": [65, 70, 75, 80],
        "oversold": [20, 25, 30, 35],
    },
    "grid": {"grid_pct": [1.0, 2.0, 3.0, 5.0], "position_pct": [0.05, 0.1, 0.15, 0.2]},
    "turtle": {
        "entry_period": [10, 15, 20, 30, 40],
        "exit_period": [5, 10, 15, 20],
        "atr_period": [10, 14, 20],
        "risk_pct": [0.5, 1.0, 1.5, 2.0],
    },
    "dual_thrust": {
        "period": [3, 4, 5, 7],
        "k_up": [0.3, 0.5, 0.7],
        "k_down": [0.3, 0.5, 0.7],
    },
    "momentum": {"lookback": [5, 10, 20, 30, 60], "hold_period": [3, 5, 10, 15]},
    "mean_reversion": {
        "period": [10, 15, 20, 30, 40],
        "entry_zscore": [-3.0, -2.5, -2.0, -1.5],
        "exit_zscore": [-0.5, 0.0, 0.5],
    },
    "volume_price": {
        "price_ma": [5, 10, 15, 20, 30],
        "volume_ma": [5, 10, 15, 20, 30],
        "volume_ratio": [1.5, 2.0, 2.5, 3.0],
    },
    "breakout": {
        "period": [20, 30, 40, 55, 70],
        "atr_period": [10, 14, 20],
        "atr_multiplier": [1.5, 2.0, 2.5, 3.0],
    },
    "composite": {
        "min_agreement": [2, 3, 4],
        "ma_fast": [3, 5, 8],
        "ma_slow": [15, 20, 30],
        "rsi_period": [10, 14, 20],
        "rsi_overbought": [65, 70, 80],
        "rsi_oversold": [20, 25, 35],
        "boll_period": [15, 20, 25],
        "boll_dev": [1.5, 2.0, 2.5],
    },
    "vwap": {"period": [10, 15, 20, 30], "deviation_pct": [0.5, 1.0, 1.5, 2.0]},
    "envelope": {"period": [10, 15, 20, 30, 40], "deviation_pct": [3, 5, 7, 10]},
    "parabolic_sar": {
        "af_start": [0.01, 0.02, 0.03],
        "af_step": [0.01, 0.02, 0.03],
        "af_max": [0.10, 0.15, 0.20, 0.25],
    },
    "obv": {"obv_ma_period": [10, 15, 20, 30], "price_ma_period": [10, 15, 20, 30]},
    "bollinger_squeeze": {
        "period": [15, 20, 25, 30],
        "devfactor": [1.5, 2.0, 2.5],
        "squeeze_threshold": [0.02, 0.03, 0.04, 0.05],
        "squeeze_lookback": [3, 5, 8],
    },
    "adx_trend": {
        "adx_period": [10, 14, 20, 28],
        "adx_threshold": [20, 25, 30, 35],
        "di_period": [10, 14, 20],
    },
    "ema_cross": {"fast": [8, 10, 12, 15], "slow": [20, 26, 30, 40]},
    "donchian": {"period": [10, 15, 20, 30, 40]},
    "williams_r": {
        "period": [10, 14, 20],
        "overbought": [-15, -20, -25],
        "oversold": [-75, -80, -85],
    },
    "cci": {
        "period": [14, 20, 28],
        "overbought": [80, 100, 120],
        "oversold": [-120, -100, -80],
    },
    "supertrend": {"period": [7, 10, 14], "multiplier": [2.0, 2.5, 3.0, 3.5]},
    "atr_trail": {
        "ma_period": [10, 20, 30],
        "atr_period": [10, 14, 20],
        "atr_mult": [2.0, 2.5, 3.0],
    },
    "ema_volume": {
        "fast": [8, 12],
        "slow": [20, 26],
        "vol_ma": [15, 20, 30],
        "vol_ratio": [1.1, 1.2, 1.5],
    },
    "triple_ma": {"fast": [5, 8, 10], "mid": [15, 20, 30], "slow": [50, 60, 90]},
    "macd_rsi": {
        "macd_fast": [10, 12],
        "macd_slow": [24, 26],
        "macd_signal": [7, 9],
        "rsi_period": [10, 14],
        "rsi_max": [65, 68, 72],
        "rsi_min": [30, 35, 40],
    },
    "pullback_ma": {"fast": [8, 10, 12], "slow": [40, 50, 60], "trend": [90, 120, 150]},
}

PARAM_RANGES = {
    "dual_ma": {"fast": (3, 15), "slow": (15, 80)},
    "macd": {"fast": (5, 15), "slow": (18, 35), "signal": (5, 15)},
    "bollinger": {"period": (8, 40), "devfactor": (1.0, 3.5)},
    "kdj": {
        "period": (5, 25),
        "period_dfast": (2, 7),
        "period_dslow": (2, 7),
        "overbought": (65, 90),
        "oversold": (10, 35),
    },
    "rsi": {"period": (5, 25), "overbought": (60, 85), "oversold": (15, 40)},
    "grid": {"grid_pct": (0.5, 8.0), "position_pct": (0.03, 0.3)},
    "turtle": {
        "entry_period": (8, 50),
        "exit_period": (4, 25),
        "atr_period": (8, 30),
        "risk_pct": (0.3, 3.0),
    },
    "dual_thrust": {"period": (2, 10), "k_up": (0.2, 1.0), "k_down": (0.2, 1.0)},
    "momentum": {"lookback": (3, 80), "hold_period": (2, 20)},
    "mean_reversion": {
        "period": (8, 50),
        "entry_zscore": (-3.5, -1.0),
        "exit_zscore": (-1.0, 1.0),
    },
    "volume_price": {
        "price_ma": (3, 40),
        "volume_ma": (3, 40),
        "volume_ratio": (1.2, 4.0),
    },
    "breakout": {
        "period": (10, 90),
        "atr_period": (8, 30),
        "atr_multiplier": (1.0, 4.0),
    },
    "composite": {
        "min_agreement": (2, 4),
        "ma_fast": (3, 12),
        "ma_slow": (15, 40),
        "rsi_period": (8, 25),
        "rsi_overbought": (60, 85),
        "rsi_oversold": (15, 40),
        "boll_period": (10, 30),
        "boll_dev": (1.0, 3.0),
    },
    "vwap": {"period": (5, 40), "deviation_pct": (0.3, 3.0)},
    "envelope": {"period": (5, 50), "deviation_pct": (2, 15)},
    "parabolic_sar": {
        "af_start": (0.005, 0.05),
        "af_step": (0.005, 0.05),
        "af_max": (0.05, 0.35),
    },
    "obv": {"obv_ma_period": (5, 40), "price_ma_period": (5, 40)},
    "bollinger_squeeze": {
        "period": (10, 40),
        "devfactor": (1.0, 3.5),
        "squeeze_threshold": (0.01, 0.08),
        "squeeze_lookback": (2, 10),
    },
    "adx_trend": {
        "adx_period": (8, 35),
        "adx_threshold": (15, 40),
        "di_period": (8, 35),
    },
    "ema_cross": {"fast": (5, 20), "slow": (15, 60)},
    "donchian": {"period": (8, 60)},
    "williams_r": {"period": (8, 28), "overbought": (-30, -10), "oversold": (-90, -70)},
    "cci": {"period": (10, 40), "overbought": (60, 150), "oversold": (-150, -60)},
    "supertrend": {"period": (5, 20), "multiplier": (1.5, 4.5)},
    "atr_trail": {"ma_period": (8, 40), "atr_period": (8, 28), "atr_mult": (1.5, 4.0)},
    "ema_volume": {
        "fast": (5, 20),
        "slow": (15, 50),
        "vol_ma": (10, 40),
        "vol_ratio": (1.0, 2.0),
    },
    "triple_ma": {"fast": (3, 15), "mid": (10, 35), "slow": (40, 120)},
    "macd_rsi": {
        "macd_fast": (8, 16),
        "macd_slow": (20, 35),
        "macd_signal": (5, 12),
        "rsi_period": (8, 21),
        "rsi_max": (60, 75),
        "rsi_min": (25, 45),
    },
    "pullback_ma": {"fast": (5, 20), "slow": (30, 80), "trend": (60, 200)},
}


def _run_single(
    code: str,
    strategy_name: str,
    params: dict,
    run_ctx: dict | None = None,
    data_feed=None,
) -> dict:
    """用指定參數跑一次回測（可選風控上下文；可傳入預建 data feed 做多保真度評估）。"""
    from src.core.risk_backtest import RiskRunConfig, attach_risk_to_cerebro

    strategy_cls = STRATEGIES[strategy_name]
    risk_cfg = RiskRunConfig.from_dict(run_ctx) if run_ctx else RiskRunConfig()

    cerebro = bt.Cerebro()
    cerebro.addstrategy(strategy_cls, **params)

    data = data_feed if data_feed is not None else prepare_data(code)
    cerebro.adddata(data)

    cerebro.broker.setcash(settings.backtest_cash)
    attach_risk_to_cerebro(cerebro, risk_cfg)

    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe", riskfreerate=0.03)
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")

    from src.core.backtest_runtime import dispose_cerebro

    initial_value = cerebro.broker.getvalue()
    results = None
    try:
        results = cerebro.run()
        final_value = cerebro.broker.getvalue()
        strat = results[0]
    finally:
        dispose_cerebro(cerebro, results)

    sharpe = strat.analyzers.sharpe.get_analysis()
    drawdown = strat.analyzers.drawdown.get_analysis()
    trades = strat.analyzers.trades.get_analysis()

    total_return = (final_value - initial_value) / initial_value * 100
    max_dd = drawdown.get("max", {}).get("drawdown", 0)
    total_trades = trades.get("total", {}).get("total", 0)
    won = trades.get("won", {}).get("total", 0)
    win_rate = (won / total_trades * 100) if total_trades > 0 else 0
    sharpe_val = sharpe.get("sharperatio")

    out = {
        "params": params,
        "total_return_pct": round(total_return, 4),
        "sharpe_ratio": sharpe_val if sharpe_val is not None else 0.0,
        "max_drawdown_pct": round(max_dd, 4),
        "total_trades": total_trades,
        "win_rate_pct": round(win_rate, 2),
        "final_value": final_value,
    }
    if risk_cfg.has_sltp() or risk_cfg.circuit_breaker_dd or risk_cfg.max_position_pct:
        out["risk_enabled"] = True
    return out


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


def _score_and_risk(
    result: dict,
    objective: str,
    run_ctx: dict | None = None,
) -> dict:
    """計算評分並套用風控熔斷懲罰。"""
    from src.core.risk_backtest import RiskRunConfig, apply_risk_score_adjustment

    result["score"] = _score(result, objective)
    cfg = RiskRunConfig.from_dict(run_ctx) if run_ctx else RiskRunConfig()
    if cfg.circuit_breaker_dd is not None and cfg.circuit_breaker_dd > 0:
        apply_risk_score_adjustment(result, cfg)
    elif cfg.has_sltp() or cfg.max_position_pct or cfg.slippage_pct:
        result["risk"] = cfg.to_dict()
    return result


def _resolve_grid_backend() -> str:
    """網格並行後端：auto 在非 Windows 且已安裝 joblib 時優先 joblib。"""
    raw = str(getattr(settings, "optimize_parallel_backend", "auto") or "auto").lower()
    if raw in ("joblib", "futures"):
        return raw
    if sys.platform == "win32":
        return "futures"
    try:
        import joblib  # noqa: F401

        return "joblib"
    except ImportError:
        return "futures"


def _add_oos_validation(
    results: list[dict], code: str, strategy_name: str, oos_ratio: float = 0.2
) -> list[dict]:
    """
    對優化結果的 top N 做樣本外（Out-of-Sample）驗證。

    將數據按 oos_ratio 分為訓練集和測試集，在測試集上重新回測，
    添加 oos_return_pct、oos_sharpe、is_oos_positive 標注。
    """
    if not results:
        return results

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
            # 過濾掉策略不支持的參數（避免 TypeError: unexpected keyword argument）
            if hasattr(strategy_cls, "params"):
                valid_keys = {name for name, _ in strategy_cls.params._getpairs()}
                params = {k: v for k, v in params.items() if k in valid_keys}
            cerebro.addstrategy(strategy_cls, **params)

            bt_df = oos_df[["open", "high", "low", "close", "volume"]].copy()
            bt_df.columns = ["Open", "High", "Low", "Close", "Volume"]
            data_feed = bt.feeds.PandasData(dataname=bt_df)
            cerebro.adddata(data_feed)

            cerebro.broker.setcash(100000)
            cerebro.broker.setcommission(commission=0.001)
            cerebro.addanalyzer(
                bt.analyzers.SharpeRatio, _name="sharpe", riskfreerate=0.03
            )
            cerebro.addanalyzer(bt.analyzers.Returns, _name="returns")

            from src.core.backtest_runtime import dispose_cerebro

            initial = cerebro.broker.getvalue()
            try:
                res = cerebro.run()
                final = cerebro.broker.getvalue()
                strat = res[0]
            finally:
                dispose_cerebro(cerebro, res)

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


def _resolve_grid_workers(task_id: str = None) -> int:
    from src.core.compute_budget import get_process_workers

    return get_process_workers(per_job_cap=8, task_id=task_id, min_workers=1)


def _resolve_optuna_jobs(task_id: str = None) -> int:
    j = getattr(settings, "optuna_n_jobs", 0)
    if j and j > 0:
        return j
    from src.core.compute_budget import get_process_workers

    return get_process_workers(per_job_cap=4, task_id=task_id, min_workers=1)


def grid_search(
    code: str,
    strategy_name: str,
    objective: str = "sharpe",
    param_grid: dict = None,
    top_n: int = 10,
    verbose: bool = True,
    task_id: str = None,
    run_ctx: dict | None = None,
) -> list[dict]:
    """網格搜索（可選並行）"""
    if strategy_name not in STRATEGIES:
        raise ValueError(f"未知策略: {strategy_name}")

    if getattr(settings, "task_parallel_grid", True):
        return grid_search_parallel(
            code,
            strategy_name,
            objective=objective,
            param_grid=param_grid,
            top_n=top_n,
            max_workers=_resolve_grid_workers(task_id),
            verbose=verbose,
            task_id=task_id,
            run_ctx=run_ctx,
        )

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
        if (
            "entry_period" in p
            and "exit_period" in p
            and p["entry_period"] <= p["exit_period"]
        ):
            continue
        if "overbought" in p and "oversold" in p and p["overbought"] <= p["oversold"]:
            continue
        if (
            "rsi_overbought" in p
            and "rsi_oversold" in p
            and p["rsi_overbought"] <= p["rsi_oversold"]
        ):
            continue
        if "min_agreement" in p and p["min_agreement"] > 4:
            continue
        valid_combos.append(p)

    total = len(valid_combos)
    logger.info(f"網格搜索 {code}/{strategy_name}: {total} 種組合, 目標={objective}")

    results = []
    for i, params in enumerate(valid_combos, 1):
        if task_id:
            from src.core.task_manager import is_task_cancelled, update_task

            if is_task_cancelled(task_id):
                raise RuntimeError("任務已取消")
            update_task(task_id, progress=min(95, int(i / total * 100)))
        try:
            r = _run_single(code, strategy_name, params, run_ctx)
            _score_and_risk(r, objective, run_ctx)
            results.append(r)
            if verbose and i % 10 == 0:
                logger.info(f"  進度: {i}/{total}")
        except Exception as e:
            logger.warning(f"  組合 {params} 失敗: {e}")

    results.sort(key=lambda x: x["score"], reverse=True)
    top_results = results[:top_n]

    # 樣本外驗證：對 top 結果在最後 20% 數據上重新回測（強制篩選條件）
    try:
        top_results = _add_oos_validation(top_results, code, strategy_name)
        # 強制要求 OOS 收益為正，否則視為過擬合而剔除
        filtered_results = [r for r in top_results if r.get("is_oos_positive") is True]
        if len(filtered_results) < top_n and len(filtered_results) > 0:
            logger.info(
                f"OOS 驗證篩選：{len(top_results)} → {len(filtered_results)} 組（剔除過擬合策略）"
            )
            # 補充不足的名額（從剩餘中取最佳）
            remaining = [r for r in top_results if r not in filtered_results]
            needed = top_n - len(filtered_results)
            top_results = filtered_results + remaining[:needed]
        elif len(filtered_results) == 0:
            logger.warning(
                f"OOS 驗證失敗：所有 {len(top_results)} 組策略均未通過樣本外測試，返回原始結果（需人工審核）"
            )
    except Exception as e:
        logger.debug(f"OOS 驗證跳過: {e}")

    return top_results


# ============================================================
# 多保真度優化（Multi-fidelity + Pruner）
# ============================================================

#: 支援的剪枝器名稱
PRUNER_CHOICES = ("none", "median", "percentile", "hyperband")

#: 各剪枝器對應的保真度階梯（數據比例）；最後一階必為 1.0（全量）
_FIDELITY_RUNGS: dict[str, tuple[float, ...]] = {
    "median": (0.5, 1.0),
    "percentile": (0.5, 1.0),
    "hyperband": (0.34, 0.67, 1.0),
}

#: 數據量少於此門檻時不做多保真度（子集太短指標無法收斂）
_MF_MIN_BARS = 400


def _build_pruner(name: str):
    """依名稱建立 Optuna pruner；none/未知 → None"""
    import optuna

    key = (name or "none").strip().lower()
    if key in ("", "none"):
        return None
    if key == "median":
        return optuna.pruners.MedianPruner(n_startup_trials=5, n_warmup_steps=0)
    if key == "percentile":
        return optuna.pruners.PercentilePruner(
            percentile=25.0, n_startup_trials=5, n_warmup_steps=0
        )
    if key == "hyperband":
        rungs = _FIDELITY_RUNGS["hyperband"]
        return optuna.pruners.HyperbandPruner(
            min_resource=1, max_resource=len(rungs), reduction_factor=3
        )
    logger.warning(f"未知 pruner「{name}」，回退為 none")
    return None


def _resolve_pruner_name(pruner: str | None) -> str:
    """參數未指定時讀全局設定。"""
    if pruner is not None:
        return (pruner or "none").strip().lower()
    return str(getattr(settings, "optuna_pruner", "none") or "none").strip().lower()


def optuna_search(
    code: str,
    strategy_name: str,
    objective: str = "sharpe",
    n_trials: int = 100,
    param_ranges: dict = None,
    verbose: bool = True,
    task_id: str = None,
    run_ctx: dict | None = None,
    pruner: str | None = None,
) -> list[dict]:
    """Optuna 貝葉斯優化（可選多保真度剪枝：低保真子集先篩，壞參數提前剪枝）"""
    import threading

    import optuna

    if strategy_name not in STRATEGIES:
        raise ValueError(f"未知策略: {strategy_name}")

    if param_ranges is None:
        param_ranges = PARAM_RANGES.get(strategy_name)
        if param_ranges is None:
            raise ValueError(f"策略 {strategy_name} 無默認搜索範圍")

    optuna.logging.set_verbosity(
        optuna.logging.INFO if verbose else optuna.logging.WARNING
    )

    pruner_name = _resolve_pruner_name(pruner)
    pruner_obj = _build_pruner(pruner_name)

    # 多保真度前置：載入完整數據（進程內緩存，只載一次），過短則退回單保真度
    mf_df = None
    rungs: tuple[float, ...] = ()
    if pruner_obj is not None:
        try:
            from src.core.backtest import _get_prepared_df

            full_df = _get_prepared_df(code)
            if len(full_df) >= _MF_MIN_BARS:
                mf_df = full_df
                rungs = _FIDELITY_RUNGS.get(pruner_name, (0.5, 1.0))
            else:
                logger.info(
                    f"多保真度跳過：{code} 僅 {len(full_df)} 根 K 線（<{_MF_MIN_BARS}）"
                )
                pruner_obj = None
                pruner_name = "none"
        except Exception as e:
            logger.warning(f"多保真度數據載入失敗，退回單保真度: {e}")
            pruner_obj = None
            pruner_name = "none"

    logger.info(
        f"Optuna 優化 {code}/{strategy_name}: {n_trials} 次試驗, 目標={objective}"
        + (f", pruner={pruner_name}（保真度階梯 {rungs}）" if pruner_obj else "")
    )

    all_results = []
    results_lock = threading.Lock()
    prune_counter = {"n": 0}

    def _objective(trial):
        params = {}
        for name, (lo, hi) in param_ranges.items():
            if isinstance(lo, int) and isinstance(hi, int):
                params[name] = trial.suggest_int(name, lo, hi)
            else:
                params[name] = trial.suggest_float(name, lo, hi)

        if "fast" in params and "slow" in params and params["fast"] >= params["slow"]:
            return float("-inf")
        if (
            "ma_fast" in params
            and "ma_slow" in params
            and params["ma_fast"] >= params["ma_slow"]
        ):
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
        if (
            "rsi_overbought" in params
            and "rsi_oversold" in params
            and params["rsi_overbought"] <= params["rsi_oversold"]
        ):
            return float("-inf")
        if "min_agreement" in params and params["min_agreement"] > 4:
            return float("-inf")

        try:
            if mf_df is not None and rungs:
                # 多保真度：逐階梯用子集評估並上報中間分，壞參數提前剪枝
                n_bars = len(mf_df)
                for step, frac in enumerate(rungs[:-1]):
                    cut = max(60, int(n_bars * frac))
                    sub_feed = bt.feeds.PandasData(dataname=mf_df.iloc[:cut].copy())
                    sub_r = _run_single(
                        code, strategy_name, params, run_ctx, data_feed=sub_feed
                    )
                    sub_score = _score(sub_r, objective)
                    trial.report(sub_score, step=step + 1)
                    if trial.should_prune():
                        with results_lock:
                            prune_counter["n"] += 1
                        raise optuna.TrialPruned(
                            f"低保真度（{frac:.0%} 數據）評分 {sub_score:.4f} 被剪枝"
                        )

            r = _run_single(code, strategy_name, params, run_ctx)
            _score_and_risk(r, objective, run_ctx)
            with results_lock:
                all_results.append(r)
            return r["score"]
        except optuna.TrialPruned:
            raise
        except Exception:
            return float("-inf")

    n_jobs = _resolve_optuna_jobs(task_id)
    study = optuna.create_study(direction="maximize", pruner=pruner_obj)
    study.optimize(
        _objective, n_trials=n_trials, show_progress_bar=verbose, n_jobs=n_jobs
    )
    if pruner_obj is not None:
        logger.info(
            f"多保真度剪枝統計：{prune_counter['n']}/{n_trials} 次試驗被提前剪枝"
        )
    if task_id:
        from src.core.task_manager import update_task

        update_task(task_id, progress=90)

    seen = set()
    unique_results = []
    for r in sorted(all_results, key=lambda x: x["score"], reverse=True):
        key = str(sorted(r["params"].items()))
        if key not in seen:
            seen.add(key)
            unique_results.append(r)

    logger.info(f"Optuna 完成：{len(unique_results)} 組唯一結果")
    top_results = unique_results[:10]

    # 樣本外驗證：對 top 結果在最後 20% 數據上重新回測（強制篩選條件）
    try:
        top_results = _add_oos_validation(top_results, code, strategy_name)
        # 強制要求 OOS 收益為正，否則視為過擬合而剔除
        filtered_results = [r for r in top_results if r.get("is_oos_positive") is True]
        if len(filtered_results) < 10 and len(filtered_results) > 0:
            logger.info(
                f"OOS 驗證篩選：{len(top_results)} → {len(filtered_results)} 組（剔除過擬合策略）"
            )
            # 補充不足的名額（從剩餘中取最佳）
            remaining = [r for r in top_results if r not in filtered_results]
            needed = 10 - len(filtered_results)
            top_results = filtered_results + remaining[:needed]
        elif len(filtered_results) == 0:
            logger.warning(
                f"OOS 驗證失敗：所有 {len(top_results)} 組策略均未通過樣本外測試，返回原始結果（需人工審核）"
            )
    except Exception as e:
        logger.debug(f"OOS 驗證跳過：{e}")

    return top_results


def optimize_all(
    code: str,
    objective: str = "sharpe",
    method: str = "grid",
    n_trials: int = 80,
    top_n: int = 5,
    verbose: bool = True,
    task_id: str = None,
    run_ctx: dict | None = None,
    pruner: str | None = None,
) -> dict:
    """對所有策略做參數優化（默認串行策略 + 每策略進程池，可選策略級並行）"""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    from src.core.compute_budget import (
        get_thread_workers,
        should_parallelize_optimize_all,
    )

    names = list(STRATEGIES.keys())
    total = len(names)
    all_results = {}
    done = 0
    parallel_strategies = should_parallelize_optimize_all(task_id)
    workers = 1
    if parallel_strategies:
        workers = get_thread_workers(
            getattr(settings, "optimize_all_workers", 2),
            task_id=task_id,
            min_workers=1,
        )
    logger.info(
        f"全策略優化 {code}: {'並行' if parallel_strategies else '串行'}策略 workers={workers}"
    )

    def _opt_one(name: str):
        if task_id:
            from src.core.task_manager import is_task_cancelled

            if is_task_cancelled(task_id):
                raise RuntimeError("任務已取消")
        if method == "optuna":
            return name, optuna_search(
                code,
                name,
                objective=objective,
                n_trials=n_trials,
                verbose=verbose,
                task_id=task_id,
                run_ctx=run_ctx,
                pruner=pruner,
            )
        return name, grid_search(
            code,
            name,
            objective=objective,
            top_n=top_n,
            verbose=verbose,
            task_id=task_id,
            run_ctx=run_ctx,
        )

    if workers <= 1:
        for i, name in enumerate(names, 1):
            if task_id:
                from src.core.task_manager import is_task_cancelled, update_task

                if is_task_cancelled(task_id):
                    raise RuntimeError("任務已取消")
                update_task(task_id, progress=min(95, int(i / total * 100)))
            try:
                strat_name, results = _opt_one(name)
                all_results[strat_name] = results
            except Exception as e:
                logger.error(f"{name} 優化失敗: {e}")
                all_results[name] = []
        return all_results

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(_opt_one, name): name for name in names}
        for future in as_completed(futures):
            name = futures[future]
            done += 1
            if task_id:
                from src.core.task_manager import is_task_cancelled, update_task

                if is_task_cancelled(task_id):
                    raise RuntimeError("任務已取消")
                update_task(task_id, progress=min(95, int(done / total * 100)))
            try:
                strat_name, results = future.result()
                all_results[strat_name] = results
            except Exception as e:
                logger.error(f"{name} 優化失敗: {e}")
                all_results[name] = []

    return all_results


# ============================================================
# 並行網格搜索（ProcessPoolExecutor）
# ============================================================


def _run_single_worker(args):
    """Worker 函數，用於並行網格搜索"""
    if len(args) >= 4:
        code, strategy_name, params, run_ctx = args[0], args[1], args[2], args[3]
    else:
        code, strategy_name, params = args
        run_ctx = None
    try:
        return _run_single(code, strategy_name, params, run_ctx)
    except Exception as e:
        logger.warning(f"網格 worker 失敗 {code}/{strategy_name}: {e}")
        return None


def _grid_executor_class():
    """Windows 子進程無法穩定打開 SQLite，改用線程池"""
    if sys.platform == "win32":
        return ThreadPoolExecutor
    return ProcessPoolExecutor


def _grid_parallel_joblib(
    tasks: list,
    max_workers: int,
    objective: str,
    run_ctx: dict | None,
    verbose: bool,
    task_id: str | None,
    total: int,
) -> list[dict]:
    from joblib import Parallel, delayed

    def _one(task_args):
        r = _run_single_worker(task_args)
        if r is None:
            return None
        return _score_and_risk(r, objective, run_ctx)

    batch = Parallel(n_jobs=max_workers, backend="loky", prefer="processes")(
        delayed(_one)(t) for t in tasks
    )
    results = [r for r in batch if r is not None]
    if verbose and total:
        logger.info(f"  Joblib 網格完成: {len(results)}/{total} 組有效結果")
    if task_id:
        from src.core.task_manager import update_task

        update_task(task_id, progress=95)
    return results


def grid_search_parallel(
    code: str,
    strategy_name: str,
    objective: str = "sharpe",
    param_grid: dict = None,
    top_n: int = 10,
    max_workers: int = 4,
    verbose: bool = True,
    task_id: str = None,
    run_ctx: dict | None = None,
) -> list[dict]:
    """並行網格搜索 — futures 或 joblib"""
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
        if (
            "entry_period" in p
            and "exit_period" in p
            and p["entry_period"] <= p["exit_period"]
        ):
            continue
        if "overbought" in p and "oversold" in p and p["overbought"] <= p["oversold"]:
            continue
        if (
            "rsi_overbought" in p
            and "rsi_oversold" in p
            and p["rsi_overbought"] <= p["rsi_oversold"]
        ):
            continue
        if "min_agreement" in p and p["min_agreement"] > 4:
            continue
        valid_combos.append(p)

    total = len(valid_combos)
    if max_workers > total:
        max_workers = max(1, total)
    logger.info(
        f"並行網格搜索 {code}/{strategy_name}: {total} 種組合, workers={max_workers}"
    )

    ctx = run_ctx or {}
    tasks = [(code, strategy_name, p, ctx) for p in valid_combos]
    backend = _resolve_grid_backend()
    if backend == "joblib" and sys.platform != "win32":
        logger.info(f"  並行後端: joblib (loky), workers={max_workers}")
        results = _grid_parallel_joblib(
            tasks,
            max_workers,
            objective,
            run_ctx,
            verbose,
            task_id,
            total,
        )
    else:
        results = []
        done = 0
        last_logged_pct = -1
        executor_cls = _grid_executor_class()
        pool_kind = "thread" if executor_cls is ThreadPoolExecutor else "process"
        logger.info(f"  並行後端: {pool_kind} pool, workers={max_workers}")

        with executor_cls(max_workers=max_workers) as executor:
            futures = {executor.submit(_run_single_worker, t): t for t in tasks}
            for future in as_completed(futures):
                done += 1
                if task_id:
                    from src.core.task_manager import is_task_cancelled, update_task

                    if is_task_cancelled(task_id):
                        executor.shutdown(wait=False, cancel_futures=True)
                        raise RuntimeError("任務已取消")
                    pct = min(95, int(done / total * 100))
                    update_task(task_id, progress=pct)
                try:
                    r = future.result()
                    if r is not None:
                        _score_and_risk(r, objective, run_ctx)
                        results.append(r)
                except Exception as e:
                    logger.debug(f"  Worker 失敗: {e}")

                if verbose and total > 0:
                    pct = int(done / total * 100)
                    if pct >= last_logged_pct + 10 or done == total:
                        last_logged_pct = pct
                        logger.info(f"  並行網格進度: {done}/{total} ({pct}%)")

    results.sort(key=lambda x: x["score"], reverse=True)
    top_results = results[:top_n]

    # 樣本外驗證：對 top 結果在最後 20% 數據上重新回測（強制篩選條件）
    try:
        top_results = _add_oos_validation(top_results, code, strategy_name)
        # 強制要求 OOS 收益為正，否則視為過擬合而剔除
        filtered_results = [r for r in top_results if r.get("is_oos_positive") is True]
        if len(filtered_results) < top_n and len(filtered_results) > 0:
            logger.info(
                f"OOS 驗證篩選：{len(top_results)} → {len(filtered_results)} 組（剔除過擬合策略）"
            )
            # 補充不足的名額（從剩餘中取最佳）
            remaining = [r for r in top_results if r not in filtered_results]
            needed = top_n - len(filtered_results)
            top_results = filtered_results + remaining[:needed]
        elif len(filtered_results) == 0:
            logger.warning(
                f"OOS 驗證失敗：所有 {len(top_results)} 組策略均未通過樣本外測試，返回原始結果（需人工審核）"
            )
    except Exception as e:
        logger.debug(f"OOS 驗證跳過：{e}")
    return top_results
