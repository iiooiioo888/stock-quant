"""依 task_type + params 重建異步任務 worker（供任務重試）。"""
from __future__ import annotations

from typing import Callable

from src.config import settings
class RetryWorkerError(ValueError):
    """無法為該任務類型建立重試 worker。"""


def build_retry_worker(task_type: str, params: dict, task_id: str) -> Callable[[], object]:
    """根據原任務類型與參數建立可提交至 task_manager 的 work_fn。"""
    params = params or {}
    builders = {
        "backtest": _retry_backtest,
        "backtest_advanced": _retry_backtest_advanced,
        "backtest_multi": _retry_backtest_multi,
        "optimize": _retry_optimize,
        "portfolio": _retry_portfolio,
        "walkforward": _retry_walkforward,
        "auto_optimize": _retry_auto_optimize,
        "stock_universe_sync": _retry_stock_universe_sync,
        "stock_universe_intro": _retry_stock_universe_intro,
        "data_download": _retry_data_download,
        "data_download_all": _retry_data_download_all,
        "data_incremental": _retry_data_incremental,
        "polymarket_sync": _retry_polymarket_sync,
    }
    builder = builders.get(task_type)
    if not builder:
        raise RetryWorkerError(f"不支援重試的任務類型: {task_type}")
    return lambda: builder(params, task_id)


def _retry_backtest(params: dict, task_id: str):
    from src.core.backtest import run_backtest

    return run_backtest(
        params["code"],
        strategy_name=params.get("strategy", "dual_ma"),
        params=params.get("params"),
        cash=params.get("cash"),
        timeframe=params.get("timeframe", "1d"),
        task_id=task_id,
    )


def _retry_backtest_advanced(params: dict, task_id: str):
    from src.core.backtest import run_backtest

    return run_backtest(
        params["code"],
        strategy_name=params.get("strategy", "dual_ma"),
        params=params.get("params"),
        cash=params.get("cash"),
        slippage_pct=params.get("slippage_pct"),
        enable_t1=params.get("enable_t1", True),
        enable_limit=params.get("enable_limit", True),
        timeframe=params.get("timeframe", "1d"),
        task_id=task_id,
    )


def _retry_backtest_multi(params: dict, task_id: str):
    from src.core.backtest import run_multi_strategy

    return run_multi_strategy(params["code"], task_id=task_id)


def _retry_optimize(params: dict, task_id: str):
    from src.core.optimize import grid_search, optuna_search, optimize_all

    code = params["code"]
    strategy = params.get("strategy", "all")
    method = params.get("method", "grid")
    objective = params.get("objective", "sharpe")
    n_trials = params.get("n_trials", 100)
    top_n = params.get("top_n", 10)

    if strategy == "all":
        results = optimize_all(
            code,
            objective=objective,
            method=method,
            n_trials=n_trials,
            top_n=top_n,
            task_id=task_id,
        )
        return {
            name: [{k: v for k, v in r.items()} for r in res_list]
            for name, res_list in results.items()
        }
    if method == "optuna":
        return optuna_search(
            code, strategy, objective=objective, n_trials=n_trials, task_id=task_id,
        )
    return grid_search(code, strategy, objective=objective, top_n=top_n, task_id=task_id)


def _retry_walkforward(params: dict, task_id: str):
    from src.core.walkforward import walk_forward

    return walk_forward(
        code=params["code"],
        strategy_name=params.get("strategy", "dual_ma"),
        train_days=params.get("train_days", 750),
        test_days=params.get("test_days", 250),
        step_days=params.get("step_days", 250),
        objective=params.get("objective", "sharpe"),
        n_trials=params.get("n_trials", 50),
    )


def _retry_auto_optimize(params: dict, task_id: str):
    from src.core.auto_optimize import auto_optimize_watchlist

    return auto_optimize_watchlist(
        codes=params.get("codes"),
        strategies=params.get("strategies"),
        method=params.get("method", "optuna"),
        n_trials=params.get("n_trials", 50),
        objective=params.get("objective", "sharpe"),
    )


def _retry_stock_universe_sync(params: dict, task_id: str):
    from src.core.stock_universe import sync_stock_universe

    cap = params.get("max_count") or settings.stock_universe_max_count
    return sync_stock_universe(max_count=cap, task_id=task_id)


def _retry_stock_universe_intro(params: dict, task_id: str):
    from src.core.stock_universe import enrich_universe_intros

    cap = params.get("limit") or settings.stock_universe_intro_enrich_limit
    return enrich_universe_intros(limit=cap, task_id=task_id)


def _resolve_market_codes(market: str, codes: list | None) -> list:
    from src.core.global_market import MARKET_CATALOG

    if codes:
        return codes
    if market == "crypto":
        return list(settings.crypto_watchlist)
    if market == "forex":
        return list(settings.forex_watchlist)
    if market in MARKET_CATALOG:
        return list(MARKET_CATALOG[market]["symbols"].keys())
    return list(settings.watchlist)


def _retry_data_download(params: dict, task_id: str):
    from src.core.download_tasks import run_market_download, run_stocks_download

    market = params.get("market", "a_share")
    codes = params.get("codes")
    if market and market != "a_share":
        codes = _resolve_market_codes(market, codes)
        return run_market_download(market, codes, task_id=task_id)
    if codes is None:
        codes = settings.watchlist
    return run_stocks_download(codes, task_id=task_id)


def _retry_data_download_all(params: dict, task_id: str):
    from src.core.download_tasks import run_download_all

    return run_download_all(task_id=task_id)


def _retry_data_incremental(params: dict, task_id: str):
    from src.core.download_tasks import run_incremental

    return run_incremental(
        codes=params.get("codes"),
        force=params.get("force", False),
        task_id=task_id,
    )


def _retry_polymarket_sync(params: dict, task_id: str):
    from src.core.polymarket.service import get_polymarket_service

    cap = params.get("limit") or settings.polymarket_default_limit
    return get_polymarket_service().sync_snapshots(limit=cap)


def _retry_portfolio(params: dict, task_id: str):
    method = params.get("method", "basic")
    allocations = params.get("allocations") or []
    cash = params.get("cash")

    handlers = {
        "basic": _portfolio_basic,
        "preset": _portfolio_preset,
        "dynamic": _portfolio_dynamic,
        "kelly": _portfolio_kelly,
        "degradation": _portfolio_degradation,
        "arbitrate": _portfolio_arbitrate,
        "risk-parity": _portfolio_risk_parity,
        "mvo": _portfolio_mvo,
        "vol-target": _portfolio_vol_target,
        "max-diversification": _portfolio_max_diversification,
        "anti-correlation": _portfolio_anti_correlation,
        "regime-switch": _portfolio_regime_switch,
        "black-litterman": _portfolio_black_litterman,
        "hrp": _portfolio_hrp,
        "cvar-optimize": _portfolio_cvar,
        "multi-timeframe": _portfolio_multi_timeframe,
        "dynamic-rebalance": _portfolio_dynamic_rebalance,
        "sector-limit": _portfolio_sector_limit,
        "voting": _portfolio_voting,
        "momentum-of-momentum": _portfolio_momentum_of_momentum,
        "adaptive-regime": _portfolio_adaptive_regime,
        "frontier": _portfolio_frontier,
    }
    handler = handlers.get(method)
    if not handler:
        raise RetryWorkerError(f"不支援重試的組合方法: {method}")
    return handler(params, task_id)


def _portfolio_basic(params: dict, _task_id: str):
    from src.core.portfolio import run_portfolio

    return run_portfolio(
        allocations=params.get("allocations") or [],
        weights=params.get("weights"),
        rebalance=params.get("rebalance", "none"),
        rebalance_freq_days=params.get("rebalance_freq_days", 20),
        cash=params.get("cash"),
    )


def _portfolio_preset(params: dict, _task_id: str):
    from src.core.portfolio import run_portfolio

    preset_name = params.get("preset_name")
    preset = settings.portfolio_presets.get(preset_name) if preset_name else None
    if not preset:
        raise RetryWorkerError(f"預設組合不存在: {preset_name}")
    return run_portfolio(
        allocations=preset["allocations"],
        rebalance=preset.get("rebalance", "none"),
        rebalance_freq_days=preset.get("rebalance_freq_days", 20),
        cash=params.get("cash"),
    )


def _portfolio_dynamic(params: dict, _task_id: str):
    from src.core.portfolio import dynamic_weight_portfolio

    return dynamic_weight_portfolio(
        allocations=params.get("allocations") or [],
        rolling_window=params.get("rolling_window", 60),
        rebalance_freq_days=params.get("rebalance_freq_days", 20),
        cash=params.get("cash"),
    )


def _portfolio_kelly(params: dict, _task_id: str):
    from src.core.portfolio import kelly_criterion

    return kelly_criterion(
        allocations=params.get("allocations") or [],
        cash=params.get("cash"),
        fraction_limit=params.get("fraction_limit", 0.5),
    )


def _portfolio_degradation(params: dict, _task_id: str):
    from src.core.portfolio import detect_degradation

    return detect_degradation(
        allocations=params.get("allocations") or [],
        lookback_days=params.get("lookback_days", 30),
        threshold_days=params.get("threshold_days", 5),
        weight_reduction=params.get("weight_reduction", 0.5),
        cash=params.get("cash"),
    )


def _portfolio_arbitrate(params: dict, _task_id: str):
    from src.core.portfolio import arbitrate_signals

    return arbitrate_signals(
        strategy_signals=params.get("strategy_signals") or [],
        allocations=params.get("allocations"),
        rolling_window=params.get("rolling_window", 60),
        cash=params.get("cash"),
    )


def _portfolio_risk_parity(params: dict, _task_id: str):
    from src.core.portfolio import risk_parity_portfolio

    return risk_parity_portfolio(
        allocations=params.get("allocations") or [],
        cash=params.get("cash"),
    )


def _portfolio_mvo(params: dict, _task_id: str):
    from src.core.portfolio import mean_variance_optimize

    return mean_variance_optimize(
        allocations=params.get("allocations") or [],
        objective=params.get("objective", "max_sharpe"),
        cash=params.get("cash"),
        n_simulations=params.get("n_simulations", 5000),
    )


def _portfolio_vol_target(params: dict, _task_id: str):
    from src.core.portfolio import volatility_targeting

    return volatility_targeting(
        allocations=params.get("allocations") or [],
        target_vol=params.get("target_vol", 0.15),
        lookback_days=params.get("lookback_days", 20),
        cash=params.get("cash"),
    )


def _portfolio_max_diversification(params: dict, _task_id: str):
    from src.core.portfolio import max_diversification_portfolio

    return max_diversification_portfolio(
        allocations=params.get("allocations") or [],
        cash=params.get("cash"),
        n_simulations=params.get("n_simulations", 5000),
    )


def _portfolio_anti_correlation(params: dict, _task_id: str):
    from src.core.portfolio import anti_correlation_portfolio

    return anti_correlation_portfolio(
        allocations=params.get("allocations") or [],
        cash=params.get("cash"),
        n_simulations=params.get("n_simulations", 5000),
    )


def _portfolio_regime_switch(params: dict, _task_id: str):
    from src.core.portfolio import regime_switch_portfolio

    return regime_switch_portfolio(
        allocations=params.get("allocations") or [],
        regime_method=params.get("regime_method", "volatility"),
        lookback_days=params.get("lookback_days", 60),
        cash=params.get("cash"),
    )


def _portfolio_black_litterman(params: dict, _task_id: str):
    from src.core.portfolio import black_litterman_portfolio

    return black_litterman_portfolio(
        allocations=params.get("allocations") or [],
        views=params.get("views") or {},
        confidence=params.get("confidence") or {},
        cash=params.get("cash"),
    )


def _portfolio_hrp(params: dict, _task_id: str):
    from src.core.portfolio import hierarchical_risk_parity

    return hierarchical_risk_parity(
        allocations=params.get("allocations") or [],
        cash=params.get("cash"),
    )


def _portfolio_cvar(params: dict, _task_id: str):
    from src.core.portfolio import cvar_optimize

    return cvar_optimize(
        allocations=params.get("allocations") or [],
        alpha=params.get("alpha", 0.05),
        cash=params.get("cash"),
    )


def _portfolio_multi_timeframe(params: dict, _task_id: str):
    from src.core.portfolio import multi_timeframe_signal

    return multi_timeframe_signal(
        allocations=params.get("allocations") or [],
        windows=params.get("windows", [5, 20, 60]),
        cash=params.get("cash"),
    )


def _portfolio_dynamic_rebalance(params: dict, _task_id: str):
    from src.core.portfolio import dynamic_rebalance_trigger

    return dynamic_rebalance_trigger(
        allocations=params.get("allocations") or [],
        threshold_pct=params.get("threshold_pct", 5.0),
        vol_window=params.get("vol_window", 20),
        cash=params.get("cash"),
    )


def _portfolio_sector_limit(params: dict, _task_id: str):
    from src.core.portfolio import sector_exposure_limit

    return sector_exposure_limit(
        allocations=params.get("allocations") or [],
        max_sector_pct=params.get("max_sector_pct", 40.0),
        cash=params.get("cash"),
    )


def _portfolio_voting(params: dict, _task_id: str):
    from src.core.portfolio import strategy_voting_portfolio

    return strategy_voting_portfolio(
        allocations=params.get("allocations") or [],
        min_votes=params.get("min_votes", 2),
        cash=params.get("cash"),
    )


def _portfolio_momentum_of_momentum(params: dict, _task_id: str):
    from src.core.portfolio import momentum_of_momentum

    return momentum_of_momentum(
        allocations=params.get("allocations") or [],
        lookback=params.get("lookback", 60),
        cash=params.get("cash"),
    )


def _portfolio_adaptive_regime(params: dict, _task_id: str):
    from src.core.portfolio import adaptive_regime_portfolio

    return adaptive_regime_portfolio(
        allocations=params.get("allocations") or [],
        cash=params.get("cash"),
    )


def _portfolio_frontier(params: dict, _task_id: str):
    from src.core.portfolio import efficient_frontier

    return efficient_frontier(
        allocations=params.get("allocations") or [],
        n_points=params.get("n_points", 20),
    )
