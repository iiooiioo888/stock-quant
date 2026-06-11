"""
全自動策略參數優化 — 對 watchlist 中所有股票運行 Optuna，
找到共識最佳參數（跨股票的中位數），報告推薦但不自動寫回 config
"""

import numpy as np

from src.config import settings
from src.core.backtest import STRATEGIES
from src.core.optimize import PARAM_RANGES, _run_single, _score
from src.utils.logger import logger


def auto_optimize_watchlist(
    codes: list[str] = None,
    strategies: list[str] = None,
    method: str = "optuna",
    n_trials: int = 50,
    objective: str = "sharpe",
) -> dict:
    """
    對指定股票 × 策略運行 Optuna 優化，找到共識最佳參數。

    返回:
    {
        "strategies": {
            "dual_ma": {
                "current_defaults": {...},
                "recommended": {...},
                "per_stock": { "000001": {...}, "600519": {...} },
                "improvement_pct": 12.5,
            },
            ...
        },
        "summary": "..."
    }
    """

    if codes is None:
        codes = settings.watchlist

    if strategies is None:
        strategies = list(STRATEGIES.keys())

    results = {}

    for strat_name in strategies:
        if strat_name not in STRATEGIES:
            logger.warning(f"跳過未知策略: {strat_name}")
            continue

        param_ranges = PARAM_RANGES.get(strat_name)
        if not param_ranges:
            logger.warning(f"策略 {strat_name} 無搜索範圍")
            continue

        logger.info(f"自動優化策略: {strat_name}, 股票: {codes}")

        current_defaults = settings.strategy_params.get(strat_name, {})
        per_stock = {}

        for code in codes:
            logger.info(f"  優化 {code}/{strat_name}...")
            try:
                if method == "optuna":
                    best_params = _optuna_for_stock(
                        code, strat_name, param_ranges, objective, n_trials
                    )
                else:
                    best_params = _grid_for_stock(
                        code, strat_name, param_ranges, objective
                    )
                per_stock[code] = best_params
            except Exception as e:
                logger.error(f"  {code}/{strat_name} 失敗: {e}")

        if not per_stock:
            results[strat_name] = {
                "current_defaults": current_defaults,
                "recommended": current_defaults,
                "per_stock": {},
                "improvement_pct": 0,
            }
            continue

        # 計算共識參數（中位數）
        recommended = _consensus_params(per_stock, param_ranges)

        # 計算改善幅度: 用推薦參數在第一個股票上跑一次 vs 默認參數
        improvement = 0
        test_code = codes[0]
        try:
            default_result = _run_single(test_code, strat_name, current_defaults)
            recommended_result = _run_single(test_code, strat_name, recommended)
            default_score = _score(default_result, objective)
            recommended_score = _score(recommended_result, objective)
            if default_score != 0:
                improvement = (
                    (recommended_score - default_score) / abs(default_score) * 100
                )
        except Exception:
            pass

        results[strat_name] = {
            "current_defaults": current_defaults,
            "recommended": recommended,
            "per_stock": per_stock,
            "improvement_pct": round(improvement, 2),
        }

    # 生成摘要
    summary_lines = ["=== 自動優化報告 ==="]
    for strat_name, info in results.items():
        summary_lines.append(f"\n📊 {strat_name}:")
        summary_lines.append(f"  當前默認: {info['current_defaults']}")
        summary_lines.append(f"  推薦參數: {info['recommended']}")
        summary_lines.append(f"  改善幅度: {info['improvement_pct']:+.2f}%")
        for code, params in info.get("per_stock", {}).items():
            summary_lines.append(f"    {code}: {params}")

    summary = "\n".join(summary_lines)

    return {
        "strategies": results,
        "summary": summary,
        "codes": codes,
        "method": method,
        "objective": objective,
        "n_trials": n_trials,
    }


def _optuna_for_stock(
    code: str, strategy_name: str, param_ranges: dict, objective: str, n_trials: int
) -> dict:
    """對單個股票做 Optuna 優化"""
    import optuna

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
            r = _run_single(code, strategy_name, params)
            return _score(r, objective)
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


def _grid_for_stock(
    code: str, strategy_name: str, param_ranges: dict, objective: str
) -> dict:
    """對單個股票做網格搜索（較快但粗糙）"""
    from src.core.optimize import grid_search

    results = grid_search(
        code, strategy_name, objective=objective, top_n=1, verbose=False
    )
    if results:
        return results[0]["params"]
    return {}


def _consensus_params(per_stock: dict, param_ranges: dict) -> dict:
    """計算跨股票的共識參數（中位數，取整到合理精度）"""
    if not per_stock:
        return {}

    all_params = list(per_stock.values())
    consensus = {}

    for key in all_params[0].keys():
        values = [p.get(key) for p in all_params if key in p]
        if not values:
            continue

        median_val = float(np.median(values))

        lo, hi = param_ranges.get(key, (None, None))
        if lo is not None and isinstance(lo, int) and isinstance(hi, int):
            consensus[key] = int(round(median_val))
        else:
            consensus[key] = round(median_val, 2)

    # 約束修正
    if "fast" in consensus and "slow" in consensus:
        if consensus["fast"] >= consensus["slow"]:
            consensus["fast"] = max(3, consensus["slow"] - 5)
    if "entry_period" in consensus and "exit_period" in consensus:
        if consensus["entry_period"] <= consensus["exit_period"]:
            consensus["entry_period"] = consensus["exit_period"] + 5
    if "overbought" in consensus and "oversold" in consensus:
        if consensus["overbought"] <= consensus["oversold"]:
            consensus["overbought"] = consensus["oversold"] + 10

    return consensus
