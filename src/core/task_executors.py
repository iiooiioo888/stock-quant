"""
可序列化任務執行器 — 供 Celery Worker 與線程池共用（依 task_type + params 重放）。
"""

from __future__ import annotations

from typing import Any, Callable

from src.utils.logger import logger

ExecutorFn = Callable[[dict, str], Any]

_EXECUTORS: dict[str, ExecutorFn] = {}


def register_executor(task_type: str, fn: ExecutorFn) -> None:
    _EXECUTORS[task_type] = fn


def has_executor(task_type: str) -> bool:
    return task_type in _EXECUTORS


def list_executor_types() -> list[str]:
    return sorted(_EXECUTORS.keys())


def execute_task(task_id: str) -> Any:
    from src.core.task_manager import get_task

    task = get_task(task_id)
    if not task:
        raise ValueError(f"任務不存在: {task_id}")
    task_type = task.get("task_type") or ""
    params = task.get("params") or {}
    fn = _EXECUTORS.get(task_type)
    if fn is None:
        raise ValueError(f"未註冊執行器: {task_type}")
    return fn(params, task_id)


def _register_defaults() -> None:
    if _EXECUTORS:
        return

    def _backtest(p: dict, task_id: str):
        from src.core.backtest import run_backtest

        return run_backtest(
            p["code"],
            strategy_name=p.get("strategy", "dual_ma"),
            params=p.get("params"),
            cash=p.get("cash"),
            stop_loss_pct=p.get("stop_loss_pct"),
            take_profit_pct=p.get("take_profit_pct"),
            trailing_stop_pct=p.get("trailing_stop_pct"),
            benchmark=bool(p.get("benchmark")),
            timeframe=p.get("timeframe", "1d"),
            task_id=task_id,
            circuit_breaker_dd=p.get("circuit_breaker_dd"),
            max_position_pct=p.get("max_position_pct"),
        )

    def _backtest_advanced(p: dict, task_id: str):
        from src.core.backtest import run_backtest

        return run_backtest(
            p["code"],
            strategy_name=p.get("strategy", "dual_ma"),
            params=p.get("params"),
            cash=p.get("cash"),
            commission=p.get("commission"),
            stop_loss_pct=p.get("stop_loss_pct"),
            take_profit_pct=p.get("take_profit_pct"),
            trailing_stop_pct=p.get("trailing_stop_pct"),
            benchmark=bool(p.get("benchmark")),
            slippage_pct=float(p.get("slippage_pct") or 0),
            volume_slippage=p.get("volume_slippage"),
            order_size_shares=int(p.get("order_size_shares") or 0),
            enable_t1=bool(p.get("enable_t1", True)),
            enable_limit=bool(p.get("enable_limit", True)),
            timeframe=p.get("timeframe", "1d"),
            task_id=task_id,
            circuit_breaker_dd=p.get("circuit_breaker_dd"),
            max_position_pct=p.get("max_position_pct"),
        )

    def _backtest_multi(p: dict, task_id: str):
        from src.core.backtest import run_multi_strategy

        return run_multi_strategy(p["code"], plot=False, task_id=task_id)

    def _optimize(p: dict, task_id: str):
        from src.core.optimize import grid_search, optimize_all, optuna_search
        from src.core.risk_backtest import parse_risk_params

        code = p["code"]
        strategy = p.get("strategy", "dual_ma")
        method = p.get("method", "grid")
        objective = p.get("objective", "sharpe")
        n_trials = int(p.get("n_trials", 100))
        top_n = int(p.get("top_n", 10))
        run_ctx = parse_risk_params(p).to_dict()
        if strategy == "all":
            results = optimize_all(
                code,
                objective=objective,
                method=method,
                n_trials=n_trials,
                top_n=top_n,
                task_id=task_id,
                run_ctx=run_ctx,
            )
            return {
                name: [{k: v for k, v in r.items()} for r in res_list]
                for name, res_list in results.items()
            }
        if method == "optuna":
            return optuna_search(
                code,
                strategy,
                objective=objective,
                n_trials=n_trials,
                task_id=task_id,
                run_ctx=run_ctx,
            )
        return grid_search(
            code,
            strategy,
            objective=objective,
            top_n=top_n,
            task_id=task_id,
            run_ctx=run_ctx,
        )

    def _portfolio(p: dict, task_id: str):
        from src.core.portfolio import run_portfolio

        return run_portfolio(
            allocations=p.get("allocations") or [],
            weights=p.get("weights"),
            rebalance=p.get("rebalance", "none"),
            rebalance_freq_days=int(p.get("rebalance_freq_days") or 20),
            cash=p.get("cash"),
        )

    def _walkforward(p: dict, task_id: str):
        from src.core.walkforward import walk_forward

        return walk_forward(
            code=p["code"],
            strategy_name=p.get("strategy", "dual_ma"),
            train_days=int(p.get("train_days", 750)),
            test_days=int(p.get("test_days", 250)),
            step_days=int(p.get("step_days", 250)),
            objective=p.get("objective", "sharpe"),
            n_trials=int(p.get("n_trials", 50)),
        )

    def _auto_optimize(p: dict, task_id: str):
        from src.core.auto_optimize import auto_optimize_watchlist

        return auto_optimize_watchlist(
            codes=p.get("codes"),
            strategies=p.get("strategies"),
            method=p.get("method", "optuna"),
            n_trials=int(p.get("n_trials", 50)),
            objective=p.get("objective", "sharpe"),
        )

    def _target_search(p: dict, task_id: str):
        from src.core.target_search import target_search

        return target_search(
            code=p["code"],
            strategy_name=p.get("strategy", "dual_ma"),
            target_metric=p.get("target_metric", "sharpe_ratio"),
            target_value=float(p.get("target_value", 1.5)),
            method=p.get("method", "optuna"),
            max_iter=int(p.get("max_iter", 500)),
            timeout_seconds=int(p.get("timeout_seconds", 3600)),
            objective=p.get("objective", "maximize"),
            task_id=task_id,
        )

    def _stock_universe_sync(p: dict, task_id: str):
        from src.core.stock_universe import sync_stock_universe

        return sync_stock_universe(
            max_count=int(p.get("max_count", 20000)), task_id=task_id
        )

    def _stock_universe_intro(p: dict, task_id: str):
        from src.core.stock_universe import enrich_universe_intros

        return enrich_universe_intros(limit=int(p.get("limit", 500)), task_id=task_id)

    def _data_download(p: dict, task_id: str):
        from src.core.history import download_one

        code = p.get("code")
        if not code:
            raise ValueError("缺少 code")
        n = download_one(code, start_date=p.get("start_date"), market=p.get("market"))
        return {"code": code, "rows": n}

    def _data_download_all(p: dict, task_id: str):
        from src.core.download_tasks import run_download_all

        return run_download_all(task_id=task_id)

    def _data_download_market(p: dict, task_id: str):
        from src.core.download_tasks import run_market_download

        return run_market_download(
            p.get("market"),
            p.get("codes") or [],
            task_id=task_id,
        )

    register_executor("backtest", _backtest)
    register_executor("backtest_advanced", _backtest_advanced)
    register_executor("backtest_multi", _backtest_multi)
    register_executor("optimize", _optimize)
    register_executor("portfolio", _portfolio)
    register_executor("walkforward", _walkforward)
    register_executor("auto_optimize", _auto_optimize)
    register_executor("target_search", _target_search)
    register_executor("stock_universe_sync", _stock_universe_sync)
    register_executor("stock_universe_intro", _stock_universe_intro)
    register_executor("data_download", _data_download_market)
    register_executor("data_download_all", _data_download_all)
    logger.debug(f"任務執行器已註冊: {len(_EXECUTORS)} 種")


_register_defaults()
