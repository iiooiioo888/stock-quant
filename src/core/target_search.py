"""
目標搜索模塊 — 循環回測直至找到達成目標收益/夏普等指標的參數
支持 Optuna (貝葉斯), Random (隨機), Grid (網格) 搜索
"""

from __future__ import annotations

import itertools
import time
from typing import Any, Optional

from src.core.backtest import STRATEGIES
from src.core.optimize import PARAM_GRIDS, PARAM_RANGES, _run_single
from src.utils.logger import logger


def _check_constraints(params: dict) -> bool:
    """檢查參數邏輯約束"""
    if "fast" in params and "slow" in params and params["fast"] >= params["slow"]:
        return False
    if (
        "ma_fast" in params
        and "ma_slow" in params
        and params["ma_fast"] >= params["ma_slow"]
    ):
        return False
    if (
        "entry_period" in params
        and "exit_period" in params
        and params["entry_period"] <= params["exit_period"]
    ):
        return False
    if (
        "overbought" in params
        and "oversold" in params
        and params["overbought"] <= params["oversold"]
    ):
        return False
    if (
        "rsi_overbought" in params
        and "rsi_oversold" in params
        and params["rsi_overbought"] <= params["rsi_oversold"]
    ):
        return False
    if "min_agreement" in params and params["min_agreement"] > 4:
        return False
    return True


def _sentinel_score(objective: str) -> float:
    return float("-inf") if objective == "maximize" else float("inf")


def target_search(
    code: str,
    strategy_name: str,
    target_metric: str = "sharpe_ratio",  # "sharpe_ratio", "total_return_pct", "win_rate_pct", "max_drawdown_pct"
    target_value: float = 1.5,
    method: str = "optuna",  # "optuna" (貝葉斯), "random" (隨機), "grid" (網格)
    max_iter: int = 500,
    timeout_seconds: int = 3600,
    objective: str = "maximize",  # "maximize" or "minimize"
    task_id: str | None = None,
) -> dict:
    """循環回測直至找到達成目標的參數，或達到最大迭代次數/超時"""
    import optuna

    from src.core.task_manager import is_task_cancelled, update_task, update_task_meta

    if strategy_name not in STRATEGIES:
        raise ValueError(f"未知策略: {strategy_name}")
    if objective not in ("maximize", "minimize"):
        raise ValueError("objective 必須為 maximize 或 minimize")
    if method not in ("optuna", "random", "grid"):
        raise ValueError("method 必須為 optuna / random / grid")
    if max_iter <= 0:
        raise ValueError("max_iter 必須 > 0")
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds 必須 > 0")

    param_ranges = PARAM_RANGES.get(strategy_name, {}) or {}
    param_grid = PARAM_GRIDS.get(strategy_name, {}) or {}

    if not param_ranges and not param_grid:
        raise ValueError(f"策略 {strategy_name} 無搜索空間")

    start_time = time.time()
    found_result: Optional[dict[str, Any]] = None
    all_results: list[dict[str, Any]] = []

    logger.info(
        f"開始目標搜索: {code}/{strategy_name} - 目標: {target_metric} {objective} {target_value} (method={method})"
    )
    if task_id:
        update_task(task_id, progress=1)
        update_task_meta(task_id, message=f"目標搜索初始化：{method}")

    def _time_up() -> bool:
        return (time.time() - start_time) > timeout_seconds

    def is_target_met(val: Any) -> bool:
        if val is None:
            return False
        try:
            f = float(val)
        except Exception:
            return False
        return f >= target_value if objective == "maximize" else f <= target_value

    # Optuna (貝葉斯) / Random (隨機)
    if method in ("optuna", "random"):
        if not param_ranges:
            raise ValueError(f"策略 {strategy_name} 無連續搜索範圍，請改用 grid")

        sampler = (
            optuna.samplers.TPESampler()
            if method == "optuna"
            else optuna.samplers.RandomSampler()
        )
        study = optuna.create_study(direction=objective, sampler=sampler)

        def stop_callback(study: optuna.study.Study, trial: optuna.trial.FrozenTrial):
            nonlocal found_result
            if task_id and is_task_cancelled(task_id):
                study.stop()
                return
            if _time_up():
                study.stop()
                return
            if trial.value is not None and is_target_met(trial.value):
                found_result = trial.user_attrs.get("result")
                if found_result:
                    logger.info(
                        f"達成目標：{target_metric}={trial.value} params={found_result.get('params')}"
                    )
                study.stop()

        def _objective(trial: optuna.trial.Trial):
            if task_id and is_task_cancelled(task_id):
                study.stop()
                return _sentinel_score(objective)
            if _time_up():
                study.stop()
                return _sentinel_score(objective)

            params = {}
            for name, (lo, hi) in param_ranges.items():
                if isinstance(lo, int) and isinstance(hi, int):
                    params[name] = trial.suggest_int(name, lo, hi)
                else:
                    params[name] = trial.suggest_float(name, float(lo), float(hi))

            if not _check_constraints(params):
                return _sentinel_score(objective)

            try:
                r = _run_single(code, strategy_name, params)
                all_results.append(r)
                score = r.get(target_metric)
                if score is None:
                    score = _sentinel_score(objective)
                trial.set_user_attr("result", r)

                if task_id:
                    done = len(all_results)
                    update_task(task_id, progress=min(95, int(done / max_iter * 100)))
                    if done % 5 == 0:
                        update_task_meta(
                            task_id,
                            message=f"已試 {done}/{max_iter} 組，最新 {target_metric}={r.get(target_metric)}",
                        )

                return float(score)
            except Exception:
                return _sentinel_score(objective)

        optuna.logging.set_verbosity(optuna.logging.WARNING)
        study.optimize(
            _objective,
            n_trials=max_iter,
            callbacks=[stop_callback],
            show_progress_bar=False,
        )

    # Grid (網格)
    else:
        if not param_grid:
            raise ValueError(
                f"策略 {strategy_name} 無網格搜索空間，請改用 optuna/random"
            )

        keys = list(param_grid.keys())
        combos = list(itertools.product(*param_grid.values()))
        total = len(combos)
        for i, vals in enumerate(combos, 1):
            if i > max_iter:
                break
            if task_id and is_task_cancelled(task_id):
                break
            if _time_up():
                break

            params = dict(zip(keys, vals))
            if not _check_constraints(params):
                continue

            try:
                r = _run_single(code, strategy_name, params)
                all_results.append(r)
                if task_id:
                    update_task(
                        task_id,
                        progress=min(95, int(i / max(1, min(total, max_iter)) * 100)),
                    )
                    if i % 10 == 0:
                        update_task_meta(
                            task_id,
                            message=f"網格進度 {i}/{min(total, max_iter)}，最新 {target_metric}={r.get(target_metric)}",
                        )

                if is_target_met(r.get(target_metric)):
                    found_result = r
                    logger.info(f"達成目標：params={found_result.get('params')}")
                    break
            except Exception:
                continue

    # 排序與回退：若未達標，回傳歷史最佳
    sort_reverse = objective == "maximize"

    def _key(x: dict) -> float:
        v = x.get(target_metric)
        if v is None:
            return _sentinel_score(objective)
        try:
            return float(v)
        except Exception:
            return _sentinel_score(objective)

    all_results.sort(key=_key, reverse=sort_reverse)
    best_overall = all_results[0] if all_results else None

    if not found_result and best_overall:
        logger.warning("未達成目標（達到上限/超時/取消），返回歷史最佳結果。")
        found_result = best_overall

    return {
        "status": "success" if found_result else "failed",
        "target_metric": target_metric,
        "target_value": target_value,
        "objective": objective,
        "method": method,
        "iterations": len(all_results),
        "elapsed_seconds": round(time.time() - start_time, 2),
        "found_params": found_result.get("params") if found_result else None,
        "found_metrics": (
            {k: v for k, v in found_result.items() if k != "params"}
            if found_result
            else None
        ),
        "best_overall": best_overall,
    }
