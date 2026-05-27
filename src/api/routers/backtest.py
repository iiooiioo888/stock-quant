"""回測與優化"""
import json
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends, Query, UploadFile, File, Request
from src.config import settings
from src.core.auth import require_auth, require_admin
from src.core.db import get_conn
from src.utils.logger import logger
from src.api.constants import STOCK_NAMES
from src.api.dispatch import dispatch_async_task

router = APIRouter()


@router.get("/api/backtest/timeframes")
async def list_backtest_timeframes():
    """回測可選 K 線週期"""
    from src.core.kline_timeframe import list_timeframes

    return {"timeframes": list_timeframes()}


@router.post("/api/backtest")
async def run_backtest_api(
    code: str,
    strategy: str = "dual_ma",
    params: dict = None,
    cash: float = None,
    stop_loss_pct: float = None,
    take_profit_pct: float = None,
    trailing_stop_pct: float = None,
    benchmark: bool = False,
    timeframe: str = "1d",
):
    """執行回測（自動去重：相同參數的回測不會重複執行）"""
    from src.core.backtest import run_backtest, STRATEGIES
    from src.core.kline_timeframe import normalize_timeframe
    from src.core.task_manager import create_task

    try:
        timeframe = normalize_timeframe(timeframe)
    except ValueError as e:
        raise HTTPException(400, str(e))

    if strategy not in STRATEGIES:
        raise HTTPException(400, f"未知策略: {strategy}，可選: {list(STRATEGIES.keys())}")

    force_refresh = False
    task_params = {
        "code": code, "strategy": strategy, "params": params, "cash": cash,
        "timeframe": timeframe,
        "stop_loss_pct": stop_loss_pct,
        "take_profit_pct": take_profit_pct,
        "trailing_stop_pct": trailing_stop_pct,
        "benchmark": benchmark,
    }
    task = create_task("backtest", task_params, title=f"回測 {code}/{strategy}", force_refresh=force_refresh)
    if task.get("is_duplicate"):
        return {"success": True, "task_id": task["task_id"], "is_duplicate": True,
                "message": "相同回測正在執行中，請等待完成", "async": True}

    task_id = task["task_id"]

    def _work():
        return run_backtest(
            code, strategy_name=strategy, params=params, cash=cash,
            stop_loss_pct=stop_loss_pct, take_profit_pct=take_profit_pct,
            trailing_stop_pct=trailing_stop_pct, benchmark=benchmark,
            timeframe=timeframe,
            task_id=task_id,
        )

    return dispatch_async_task(
        task_id, _work,
        cache_namespace="backtest", cache_params=task_params, cache_code=code,
    )


@router.post("/api/backtest/advanced")
async def run_advanced_backtest_api(body: dict):
    """
    進階回測 — 支持滑點、T+1、漲跌停控制（自動加入任務列表）

    請求體參數：
        code: 股票代碼
        strategy: 策略名稱（默認 dual_ma）
        params: 策略參數（可選）
        cash: 初始資金（可選）
        commission: 手續費率（可選）
        stop_loss_pct: 止損百分比（可選）
        take_profit_pct: 止盈百分比（可選）
        trailing_stop_pct: 移動止損百分比（可選）
        benchmark: 是否基準對比（默認 False）
        slippage_pct: 滑點百分比（默認 0.0，即 0%）
        enable_t1: 是否啟用 T+1 限制（默認 True）
        enable_limit: 是否啟用漲跌停限制（默認 True）
        timeframe: K 線週期 1d / 1h / 1m（默認 1d）
    """
    from src.core.backtest import run_backtest, STRATEGIES
    from src.core.kline_timeframe import normalize_timeframe
    from src.core.task_manager import create_task

    code = body.get("code", "")
    strategy = body.get("strategy", "dual_ma")
    params = body.get("params")
    cash = body.get("cash")
    commission = body.get("commission")
    stop_loss_pct = body.get("stop_loss_pct")
    take_profit_pct = body.get("take_profit_pct")
    trailing_stop_pct = body.get("trailing_stop_pct")
    benchmark = body.get("benchmark", False)
    slippage_pct = body.get("slippage_pct", 0.0)
    enable_t1 = body.get("enable_t1", True)
    enable_limit = body.get("enable_limit", True)
    timeframe = body.get("timeframe", "1d")

    if not code:
        raise HTTPException(400, "請提供股票代碼")
    try:
        timeframe = normalize_timeframe(timeframe)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if strategy not in STRATEGIES:
        raise HTTPException(400, f"未知策略: {strategy}，可選: {list(STRATEGIES.keys())}")

    force_refresh = bool(body.get("force_refresh") or body.get("force"))

    # 任務去重（params 須含全部影響回測的欄位，否則會命中錯誤的舊結果）
    task_params = {
        "code": code, "strategy": strategy, "params": params, "cash": cash,
        "commission": commission,
        "stop_loss_pct": stop_loss_pct,
        "take_profit_pct": take_profit_pct,
        "trailing_stop_pct": trailing_stop_pct,
        "benchmark": benchmark,
        "slippage_pct": slippage_pct, "enable_t1": enable_t1, "enable_limit": enable_limit,
        "timeframe": timeframe,
    }
    if force_refresh:
        from src.core.result_cache import drop_cached_compute
        drop_cached_compute("backtest_advanced", task_params, code=code)
    task = create_task(
        "backtest_advanced", task_params, title=f"進階回測 {code}/{strategy}",
        force_refresh=force_refresh,
    )
    if task.get("is_duplicate"):
        return {"success": True, "task_id": task["task_id"], "is_duplicate": True,
                "message": "相同進階回測正在執行中，請等待完成", "async": True}

    task_id = task["task_id"]

    def _work():
        return run_backtest(
            code, strategy_name=strategy, params=params, cash=cash,
            commission=commission, stop_loss_pct=stop_loss_pct,
            take_profit_pct=take_profit_pct, trailing_stop_pct=trailing_stop_pct,
            benchmark=benchmark, slippage_pct=slippage_pct,
            enable_t1=enable_t1, enable_limit=enable_limit,
            timeframe=timeframe,
            task_id=task_id,
        )

    return dispatch_async_task(
        task_id, _work,
        cache_namespace="backtest_advanced", cache_params=task_params, cache_code=code,
    )


@router.post("/api/backtest/multi")
async def run_multi_backtest_api(code: str):
    """所有策略對比（自動加入任務列表）"""
    from src.core.backtest import run_multi_strategy
    from src.core.task_manager import create_task

    if not code:
        raise HTTPException(400, "請提供股票代碼")

    task_params = {"code": code}
    task = create_task("backtest_multi", task_params, title=f"多策略對比 {code}")
    if task.get("is_duplicate"):
        return {"success": True, "task_id": task["task_id"], "is_duplicate": True,
                "message": "相同多策略對比正在執行中，請等待完成", "async": True}

    task_id = task["task_id"]
    return dispatch_async_task(
        task_id,
        lambda: run_multi_strategy(code, task_id=task_id),
        cache_namespace="backtest_multi",
        cache_params=task_params,
        cache_code=code,
    )


# ====== 優化 ======

@router.post("/api/optimize")
async def run_optimize_api(
    code: str,
    strategy: str = "all",
    method: str = "grid",
    objective: str = "sharpe",
    n_trials: int = 100,
    top_n: int = 10,
):
    """參數優化（自動加入任務列表）"""
    from src.core.optimize import grid_search, optuna_search, optimize_all
    from src.core.task_manager import create_task

    if not code:
        raise HTTPException(400, "請提供股票代碼")

    task_params = {"code": code, "strategy": strategy, "method": method, "objective": objective, "n_trials": n_trials}
    display_strategy = strategy if strategy != "all" else "全部策略"
    task = create_task("optimize", task_params, title=f"參數優化 {code}/{display_strategy}")
    if task.get("is_duplicate"):
        return {"success": True, "task_id": task["task_id"], "is_duplicate": True,
                "message": "相同優化正在執行中，請等待完成", "async": True}

    task_id = task["task_id"]

    def _work():
        if strategy == "all":
            results = optimize_all(
                code, objective=objective, method=method,
                n_trials=n_trials, top_n=top_n, task_id=task_id,
            )
            serialized = {}
            for name, res_list in results.items():
                serialized[name] = [{k: v for k, v in r.items()} for r in res_list]
            return serialized
        if method == "optuna":
            return optuna_search(code, strategy, objective=objective, n_trials=n_trials, task_id=task_id)
        return grid_search(code, strategy, objective=objective, top_n=top_n, task_id=task_id)

    task_params["top_n"] = top_n
    return dispatch_async_task(
        task_id, _work,
        cache_namespace="optimize", cache_params=task_params, cache_code=code,
    )


# ====== 組合 ======

@router.post("/api/portfolio")
async def run_portfolio_api(
    allocations: list[dict],
    weights: list[float] = None,
    rebalance: str = "none",
    rebalance_freq_days: int = 20,
    cash: float = None,
):
    """組合回測（自動加入任務列表）"""
    from src.core.portfolio import run_portfolio
    from src.core.task_manager import create_task

    if not allocations:
        raise HTTPException(400, "請提供組合配置")

    codes = [a.get("code", "") for a in allocations]
    task_params = {
        "method": "basic",
        "allocations": allocations,
        "codes": codes,
        "weights": weights,
        "rebalance": rebalance,
        "rebalance_freq_days": rebalance_freq_days,
        "cash": cash,
        "count": len(allocations),
    }
    task = create_task("portfolio", task_params, title=f"組合回測 · 基礎等權 ({len(allocations)}子)")
    if task.get("is_duplicate"):
        return {"success": True, "task_id": task["task_id"], "is_duplicate": True,
                "message": "相同組合回測正在執行中，請等待完成", "async": True}

    task_id = task["task_id"]

    def _work():
        return run_portfolio(
            allocations=allocations,
            weights=weights,
            rebalance=rebalance,
            rebalance_freq_days=rebalance_freq_days,
            cash=cash,
        )

    return dispatch_async_task(
        task_id, _work,
        cache_namespace="portfolio", cache_params=task_params, cache_code=codes[0] if codes else None,
    )


# ====== 預警 ======


@router.get("/api/backtest/history")
async def backtest_history(
    code: str = None,
    strategy: str = None,
    limit: int = 50,
    offset: int = 0,
    page_size: int = None,
):
    """查詢回測歷史（limit/offset 或 page_size 分頁）"""
    from src.core.db import count_backtest_history, get_backtest_history

    page_limit = page_size if page_size is not None else limit
    page_limit = max(1, min(int(page_limit), 100))
    page_offset = max(0, int(offset))
    total = count_backtest_history(code=code, strategy=strategy)
    results = get_backtest_history(
        code=code, strategy=strategy, limit=page_limit, offset=page_offset,
    )
    return {
        "results": results,
        "total": total,
        "limit": page_limit,
        "offset": page_offset,
        "has_more": page_offset + len(results) < total,
    }


@router.get("/api/backtest/compare")
async def backtest_compare(ids: str = ""):
    """對比指定回測結果"""
    from src.core.db import get_backtest_by_ids
    if not ids:
        return {"results": []}
    id_list = [int(x.strip()) for x in ids.split(",") if x.strip().isdigit()]
    results = get_backtest_by_ids(id_list)
    return {"results": results, "total": len(results)}


@router.get("/api/backtest/result/{result_id}")
async def get_backtest_result_detail(result_id: int):
    """按歷史 ID 取回測詳情；優先從計算緩存還原完整結果（含 K 線/淨值）。"""
    from src.core.db import get_backtest_by_ids
    from src.core.result_cache import get_cached_compute

    rows = get_backtest_by_ids([result_id])
    if not rows:
        raise HTTPException(404, "回測記錄不存在")
    row = rows[0]
    params = row.get("params") if isinstance(row.get("params"), dict) else {}
    code = row.get("code") or ""
    strategy = row.get("strategy") or ""
    cache_params = {
        "code": code,
        "strategy": strategy,
        "params": params.get("params") if isinstance(params.get("params"), dict) else params,
        "cash": params.get("cash"),
        "timeframe": params.get("timeframe", "1d"),
    }
    full = None
    for ns, p in (
        ("backtest", cache_params),
        ("backtest_advanced", {**cache_params, **params}),
        ("backtest", params),
    ):
        hit = get_cached_compute(ns, p, code=code)
        if hit and isinstance(hit, dict):
            full = hit
            break
    if full and isinstance(full, dict):
        merged = {**full, "id": result_id}
        return {"success": True, "full": True, "result": merged, "summary": row}
    return {"success": True, "full": False, "result": row, "summary": row}


# ====== Walk-Forward ======

@router.post("/api/walkforward")
async def run_walkforward(
    code: str,
    strategy: str = "dual_ma",
    train_days: int = 750,
    test_days: int = 250,
    step_days: int = 250,
    objective: str = "sharpe",
    n_trials: int = 50,
):
    """Walk-Forward 分析（自動加入任務列表）"""
    from src.core.walkforward import walk_forward
    from src.core.task_manager import create_task

    if not code:
        raise HTTPException(400, "請提供股票代碼")

    task_params = {"code": code, "strategy": strategy, "train_days": train_days, "test_days": test_days}
    task = create_task("walkforward", task_params, title=f"Walk-Forward {code}/{strategy}")
    if task.get("is_duplicate"):
        return {"success": True, "task_id": task["task_id"], "is_duplicate": True,
                "message": "相同 Walk-Forward 正在執行中，請等待完成", "async": True}

    task_id = task["task_id"]

    def _work():
        return walk_forward(
            code=code, strategy_name=strategy,
            train_days=train_days, test_days=test_days, step_days=step_days,
            objective=objective, n_trials=n_trials,
        )

    return dispatch_async_task(
        task_id, _work,
        cache_namespace="walkforward", cache_params=task_params, cache_code=code,
    )


# ====== 自動優化 ======

@router.post("/api/auto-optimize")
async def run_auto_optimize(body: dict = None):
    """自動參數優化（自動加入任務列表）"""
    from src.core.auto_optimize import auto_optimize_watchlist
    from src.core.task_manager import create_task

    if body is None:
        body = {}

    task_params = {"codes": body.get("codes"), "strategies": body.get("strategies"), "method": body.get("method", "optuna")}
    task = create_task("auto_optimize", task_params, title="全自動參數優化")
    if task.get("is_duplicate"):
        return {"success": True, "task_id": task["task_id"], "is_duplicate": True,
                "message": "全自動優化正在執行中，請等待完成", "async": True}

    task_id = task["task_id"]

    def _work():
        return auto_optimize_watchlist(
            codes=body.get("codes"),
            strategies=body.get("strategies"),
            method=body.get("method", "optuna"),
            n_trials=body.get("n_trials", 50),
            objective=body.get("objective", "sharpe"),
        )

    return dispatch_async_task(
        task_id, _work,
        cache_namespace="auto_optimize", cache_params=task_params,
    )

