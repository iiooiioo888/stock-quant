"""回測與優化"""

import json
from datetime import datetime
from fastapi import (
    APIRouter,
    HTTPException,
    Depends,
    Query,
    UploadFile,
    File,
    Request,
    Body,
)
from src.config import settings
from src.core.auth import require_auth, require_admin, get_current_user
from src.core.db import get_conn
from src.utils.logger import logger
from src.api.constants import STOCK_NAMES
from src.api.dispatch import dispatch_async_task

router = APIRouter()


def _normalize_code(code: str) -> str:
    """清洗股票代碼：strip + A股6位補零；空值拋 400"""
    code = str(code).strip()
    if not code:
        raise HTTPException(400, "股票代碼不能為空")
    if code.isdigit() and len(code) < 6:
        code = code.zfill(6)
    return code


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
    user=Depends(get_current_user),
):
    """執行回測（自動去重：相同參數的回測不會重複執行）"""
    from src.core.backtest import run_backtest, STRATEGIES
    from src.core.entitlements import gate_backtest_submit
    from src.core.kline_timeframe import normalize_timeframe
    from src.core.task_manager import create_task

    gate_backtest_submit(user, advanced=False)
    if user:
        from src.core.entitlements import gate_concurrent_tasks

        gate_concurrent_tasks(user)

    try:
        timeframe = normalize_timeframe(timeframe)
    except ValueError as e:
        raise HTTPException(400, str(e))

    if strategy not in STRATEGIES:
        raise HTTPException(
            400, f"未知策略: {strategy}，可選: {list(STRATEGIES.keys())}"
        )

    force_refresh = False
    task_params = {
        "code": code,
        "strategy": strategy,
        "params": params,
        "cash": cash,
        "timeframe": timeframe,
        "stop_loss_pct": stop_loss_pct,
        "take_profit_pct": take_profit_pct,
        "trailing_stop_pct": trailing_stop_pct,
        "benchmark": benchmark,
    }
    task = create_task(
        "backtest",
        task_params,
        title=f"回測 {code}/{strategy}",
        force_refresh=force_refresh,
        user_id=user.id if user else None,
    )
    if task.get("is_duplicate"):
        return {
            "success": True,
            "task_id": task["task_id"],
            "is_duplicate": True,
            "message": "相同回測正在執行中，請等待完成",
            "async": True,
        }

    task_id = task["task_id"]

    def _work():
        return run_backtest(
            code,
            strategy_name=strategy,
            params=params,
            cash=cash,
            stop_loss_pct=stop_loss_pct,
            take_profit_pct=take_profit_pct,
            trailing_stop_pct=trailing_stop_pct,
            benchmark=benchmark,
            timeframe=timeframe,
            task_id=task_id,
            user_id=user.id if user else None,
        )

    return dispatch_async_task(
        task_id,
        _work,
        cache_namespace="backtest",
        cache_params=task_params,
        cache_code=code,
    )


@router.post("/api/backtest/advanced")
async def run_advanced_backtest_api(body: dict, user=Depends(require_auth)):
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
    from src.core.entitlements import gate_backtest_submit
    from src.core.kline_timeframe import normalize_timeframe
    from src.core.task_manager import create_task

    gate_backtest_submit(user, advanced=True)
    from src.core.entitlements import gate_concurrent_tasks

    gate_concurrent_tasks(user)

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
    circuit_breaker_dd = body.get("circuit_breaker_dd")
    max_position_pct = body.get("max_position_pct")

    if not code:
        raise HTTPException(400, "請提供股票代碼")
    try:
        timeframe = normalize_timeframe(timeframe)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if strategy not in STRATEGIES:
        raise HTTPException(
            400, f"未知策略: {strategy}，可選: {list(STRATEGIES.keys())}"
        )

    force_refresh = bool(body.get("force_refresh") or body.get("force"))

    # 任務去重（params 須含全部影響回測的欄位，否則會命中錯誤的舊結果）
    task_params = {
        "code": code,
        "strategy": strategy,
        "params": params,
        "cash": cash,
        "commission": commission,
        "stop_loss_pct": stop_loss_pct,
        "take_profit_pct": take_profit_pct,
        "trailing_stop_pct": trailing_stop_pct,
        "benchmark": benchmark,
        "slippage_pct": slippage_pct,
        "enable_t1": enable_t1,
        "enable_limit": enable_limit,
        "timeframe": timeframe,
        "circuit_breaker_dd": circuit_breaker_dd,
        "max_position_pct": max_position_pct,
    }
    if force_refresh:
        from src.core.result_cache import drop_cached_compute

        drop_cached_compute("backtest_advanced", task_params, code=code)
    task = create_task(
        "backtest_advanced",
        task_params,
        title=f"進階回測 {code}/{strategy}",
        force_refresh=force_refresh,
        user_id=user.id,
    )
    if task.get("is_duplicate"):
        return {
            "success": True,
            "task_id": task["task_id"],
            "is_duplicate": True,
            "message": "相同進階回測正在執行中，請等待完成",
            "async": True,
        }

    task_id = task["task_id"]

    def _work():
        return run_backtest(
            code,
            strategy_name=strategy,
            params=params,
            cash=cash,
            commission=commission,
            stop_loss_pct=stop_loss_pct,
            take_profit_pct=take_profit_pct,
            trailing_stop_pct=trailing_stop_pct,
            benchmark=benchmark,
            slippage_pct=slippage_pct,
            enable_t1=enable_t1,
            enable_limit=enable_limit,
            timeframe=timeframe,
            task_id=task_id,
            circuit_breaker_dd=circuit_breaker_dd,
            max_position_pct=max_position_pct,
            user_id=user.id,
        )

    return dispatch_async_task(
        task_id,
        _work,
        cache_namespace="backtest_advanced",
        cache_params=task_params,
        cache_code=code,
    )


@router.post("/api/backtest/multi")
async def run_multi_backtest_api(code: str):
    """所有策略對比（自動加入任務列表）"""
    from src.core.backtest import run_multi_strategy
    from src.core.task_manager import create_task

    code = _normalize_code(code)

    task_params = {"code": code}
    task = create_task("backtest_multi", task_params, title=f"多策略對比 {code}")
    if task.get("is_duplicate"):
        return {
            "success": True,
            "task_id": task["task_id"],
            "is_duplicate": True,
            "message": "相同多策略對比正在執行中，請等待完成",
            "async": True,
        }

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
    stop_loss_pct: float = None,
    take_profit_pct: float = None,
    trailing_stop_pct: float = None,
    circuit_breaker_dd: float = None,
    max_position_pct: float = None,
    slippage_pct: float = None,
    body: dict = Body(default=None),
    user=Depends(require_auth),
):
    """
    參數優化（自動加入任務列表）。
    查詢參數與 JSON body 可並用；風控亦可嵌套 risk: { ... }。
    """
    from src.core.entitlements import gate_optimize_submit
    from src.core.optimize import grid_search, optuna_search, optimize_all
    from src.core.risk_backtest import parse_risk_params
    from src.core.task_manager import create_task

    if not code:
        raise HTTPException(400, "請提供股票代碼")

    gate_optimize_submit(user)
    from src.core.entitlements import gate_concurrent_tasks

    gate_concurrent_tasks(user)

    merged = {
        "code": code,
        "strategy": strategy,
        "method": method,
        "objective": objective,
        "n_trials": n_trials,
        "top_n": top_n,
        "stop_loss_pct": stop_loss_pct,
        "take_profit_pct": take_profit_pct,
        "trailing_stop_pct": trailing_stop_pct,
        "circuit_breaker_dd": circuit_breaker_dd,
        "max_position_pct": max_position_pct,
        "slippage_pct": slippage_pct,
    }
    if body:
        merged.update({k: v for k, v in body.items() if v is not None})

    risk_cfg = parse_risk_params(merged)
    task_params = {**merged, **risk_cfg.to_dict()}
    display_strategy = strategy if strategy != "all" else "全部策略"
    task = create_task(
        "optimize",
        task_params,
        title=f"參數優化 {code}/{display_strategy}",
        user_id=user.id,
    )
    if task.get("is_duplicate"):
        return {
            "success": True,
            "task_id": task["task_id"],
            "is_duplicate": True,
            "message": "相同優化正在執行中，請等待完成",
            "async": True,
        }

    task_id = task["task_id"]
    run_ctx = risk_cfg.to_dict()

    def _work():
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
            serialized = {}
            for name, res_list in results.items():
                serialized[name] = [{k: v for k, v in r.items()} for r in res_list]
            return serialized
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

    return dispatch_async_task(
        task_id,
        _work,
        cache_namespace="optimize",
        cache_params=task_params,
        cache_code=code,
    )


# ====== 組合 ======


@router.post("/api/portfolio")
async def run_portfolio_api(
    allocations: list[dict],
    weights: list[float] = None,
    rebalance: str = "none",
    rebalance_freq_days: int = 20,
    cash: float = None,
    user=Depends(require_auth),
):
    """組合回測（自動加入任務列表）"""
    from src.core.entitlements import gate_portfolio_task
    from src.core.portfolio import run_portfolio
    from src.core.task_manager import create_task

    gate_portfolio_task(user, advanced=False)

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
    task = create_task(
        "portfolio",
        task_params,
        title=f"組合回測 · 基礎等權 ({len(allocations)}子)",
        user_id=user.id,
    )
    if task.get("is_duplicate"):
        return {
            "success": True,
            "task_id": task["task_id"],
            "is_duplicate": True,
            "message": "相同組合回測正在執行中，請等待完成",
            "async": True,
        }

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
        task_id,
        _work,
        cache_namespace="portfolio",
        cache_params=task_params,
        cache_code=codes[0] if codes else None,
    )


# ====== 預警 ======


@router.get("/api/backtest/history")
async def backtest_history(
    code: str = None,
    strategy: str = None,
    limit: int = 50,
    offset: int = 0,
    page_size: int = None,
    user=Depends(get_current_user),
):
    """查詢回測歷史（登錄用戶優先看自己的數據）"""
    from src.core.db import count_backtest_history, get_backtest_history

    user_id = user.id if user else None
    page_limit = page_size if page_size is not None else limit
    page_limit = max(1, min(int(page_limit), 100))
    page_offset = max(0, int(offset))
    total = count_backtest_history(code=code, strategy=strategy, user_id=user_id)
    results = get_backtest_history(
        code=code,
        strategy=strategy,
        limit=page_limit,
        offset=page_offset,
        user_id=user_id,
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
        "params": (
            params.get("params") if isinstance(params.get("params"), dict) else params
        ),
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
    user=Depends(require_auth),
):
    """Walk-Forward 分析（自動加入任務列表）"""
    from src.core.entitlements import gate_backtest_submit
    from src.core.walkforward import walk_forward
    from src.core.task_manager import create_task

    if not code:
        raise HTTPException(400, "請提供股票代碼")

    gate_backtest_submit(user, advanced=True)
    from src.core.entitlements import gate_concurrent_tasks

    gate_concurrent_tasks(user)

    task_params = {
        "code": code,
        "strategy": strategy,
        "train_days": train_days,
        "test_days": test_days,
    }
    task = create_task(
        "walkforward",
        task_params,
        title=f"Walk-Forward {code}/{strategy}",
        user_id=user.id,
    )
    if task.get("is_duplicate"):
        return {
            "success": True,
            "task_id": task["task_id"],
            "is_duplicate": True,
            "message": "相同 Walk-Forward 正在執行中，請等待完成",
            "async": True,
        }

    task_id = task["task_id"]

    def _work():
        return walk_forward(
            code=code,
            strategy_name=strategy,
            train_days=train_days,
            test_days=test_days,
            step_days=step_days,
            objective=objective,
            n_trials=n_trials,
        )

    return dispatch_async_task(
        task_id,
        _work,
        cache_namespace="walkforward",
        cache_params=task_params,
        cache_code=code,
    )


# ====== 自動優化 ======


@router.post("/api/auto-optimize")
async def run_auto_optimize(body: dict = None, user=Depends(require_auth)):
    """自動參數優化（自動加入任務列表）"""
    from src.core.auto_optimize import auto_optimize_watchlist
    from src.core.entitlements import gate_optimize_submit
    from src.core.task_manager import create_task

    gate_optimize_submit(user)
    from src.core.entitlements import gate_concurrent_tasks

    gate_concurrent_tasks(user)

    if body is None:
        body = {}

    task_params = {
        "codes": body.get("codes"),
        "strategies": body.get("strategies"),
        "method": body.get("method", "optuna"),
    }
    task = create_task(
        "auto_optimize", task_params, title="全自動參數優化", user_id=user.id
    )
    if task.get("is_duplicate"):
        return {
            "success": True,
            "task_id": task["task_id"],
            "is_duplicate": True,
            "message": "全自動優化正在執行中，請等待完成",
            "async": True,
        }

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
        task_id,
        _work,
        cache_namespace="auto_optimize",
        cache_params=task_params,
    )


@router.post("/api/backtest/sandbox")
async def run_sandbox_backtest_api(
    code: str = Body(..., description="股票代碼"),
    strategy_code: str = Body(..., description="用戶上傳的策略源碼（Python）"),
    cash: float = Body(100000.0, description="初始資金"),
    commission: float = Body(0.001, description="手續費率"),
    stop_loss_pct: float = Body(None, description="止損百分比"),
    take_profit_pct: float = Body(None, description="止盈百分比"),
    benchmark: bool = Body(False, description="是否對比基準"),
    timeframe: str = Body("1d", description="K 線週期"),
    user=Depends(require_auth),
):
    """
    沙箱模式回測（Phase 1 穩定性優化）

    允許用戶上傳自定義策略源碼，在隔離環境中執行回測：
    - AST 白名單校驗：僅允許安全庫（numpy/pandas/backtrader 等）
    - 危險語法攔截：禁止 open/eval/exec/__import__ 等
    - 檔案大小限制：最大 64KB
    - AST 節點數限制：防止複雜度爆炸
    - 生產數據隔離：沙箱回測不污染正式回測記錄

    請求體：
        code: 股票代碼
        strategy_code: 用戶策略源碼（必須繼承 UserStrategy）
        cash: 初始資金
        commission: 手續費率
        stop_loss_pct: 止損百分比（可選）
        take_profit_pct: 止盈百分比（可選）
        benchmark: 是否對比基準
        timeframe: K 線週期

    返回：
        任務 ID（異步執行），可通過 /api/tasks/{task_id} 查詢進度
    """
    from src.core.strategy_sandbox import validate_strategy_source
    from src.core.kline_timeframe import normalize_timeframe
    from src.core.task_manager import create_task
    from src.core.entitlements import gate_backtest_submit, gate_concurrent_tasks

    # 權限檢查
    gate_backtest_submit(user, advanced=True)
    gate_concurrent_tasks(user)

    # 驗證策略源碼
    validation = validate_strategy_source(strategy_code)
    if not validation.ok:
        raise HTTPException(400, f"策略源碼校驗失敗：{validation.error}")

    # 標準化時間框架
    try:
        timeframe = normalize_timeframe(timeframe)
    except ValueError as e:
        raise HTTPException(400, str(e))

    # 創建沙箱任務
    task_params = {
        "code": code,
        "strategy_code": strategy_code,
        "cash": cash,
        "commission": commission,
        "stop_loss_pct": stop_loss_pct,
        "take_profit_pct": take_profit_pct,
        "benchmark": benchmark,
        "timeframe": timeframe,
        "sandbox_mode": True,  # 標記為沙箱模式
    }

    task = create_task(
        "sandbox_backtest",
        task_params,
        title=f"沙箱回測 {code}",
        user_id=user.id,
    )

    if task.get("is_duplicate"):
        return {
            "success": True,
            "task_id": task["task_id"],
            "is_duplicate": True,
            "message": "相同沙箱回測正在執行中，請等待完成",
            "async": True,
        }

    task_id = task["task_id"]

    def _work():
        """執行沙箱回測"""
        from src.core.backtest_sandbox_executor import run_sandbox_backtest

        return run_sandbox_backtest(
            code=code,
            strategy_code=strategy_code,
            cash=cash,
            commission=commission,
            stop_loss_pct=stop_loss_pct,
            take_profit_pct=take_profit_pct,
            benchmark=benchmark,
            timeframe=timeframe,
            task_id=task_id,
            user_id=user.id,
        )

    return dispatch_async_task(
        task_id,
        _work,
        cache_namespace="sandbox_backtest",
        cache_params=task_params,
        cache_code=code,
    )


@router.get("/api/backtest/sandbox/examples")
async def get_sandbox_examples():
    """
    獲取沙箱策略示例代碼

    返回多個示例策略，供用戶參考學習如何編寫自定義策略。
    """
    examples = [
        {
            "name": "簡單雙均線策略",
            "description": "當快均線上穿慢均線時買入，下穿時賣出",
            "code": '''from src.core.strategy_base import UserStrategy
import pandas as pd

class MyDualMA(UserStrategy):
    """簡單雙均線策略示例"""
    
    def __init__(self):
        super().__init__()
        self.fast_period = 5
        self.slow_period = 20
    
    def next(self, df: pd.DataFrame) -> int:
        \"\"\"
        返回值：1=買入，-1=賣出，0=保持
        
        df 包含 columns: ['open', 'high', 'low', 'close', 'volume']
        \"\"\"
        if len(df) < self.slow_period:
            return 0
        
        fast_ma = df['close'].tail(self.fast_period).mean()
        slow_ma = df['close'].tail(self.slow_period).mean()
        
        prev_fast = df['close'].tail(self.fast_period + 1).head(self.fast_period).mean()
        prev_slow = df['close'].tail(self.slow_period + 1).head(self.slow_period).mean()
        
        # 金叉：快均線上穿慢均線
        if prev_fast <= prev_slow and fast_ma > slow_ma:
            return 1
        
        # 死叉：快均線下穿慢均線
        if prev_fast >= prev_slow and fast_ma < slow_ma:
            return -1
        
        return 0
''',
        },
        {
            "name": "RSI 超買超賣策略",
            "description": "當 RSI < 30 時買入，RSI > 70 時賣出",
            "code": '''from src.core.strategy_base import UserStrategy
import pandas as pd

class MyRSI(UserStrategy):
    """RSI 超買超賣策略示例"""
    
    def __init__(self):
        super().__init__()
        self.rsi_period = 14
        self.oversold = 30
        self.overbought = 70
    
    def calculate_rsi(self, series: pd.Series) -> float:
        \"\"\"計算 RSI\"\"\"
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=self.rsi_period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.rsi_period).mean()
        rs = gain / loss if loss != 0 else 0
        return 100 - (100 / (1 + rs))
    
    def next(self, df: pd.DataFrame) -> int:
        if len(df) < self.rsi_period + 1:
            return 0
        
        rsi = self.calculate_rsi(df['close'])
        
        # RSI < 30：超賣，買入
        if rsi < self.oversold:
            return 1
        
        # RSI > 70：超買，賣出
        if rsi > self.overbought:
            return -1
        
        return 0
''',
        },
        {
            "name": "布林帶突破策略",
            "description": "價格跌破下軌買入，突破上軌賣出",
            "code": '''from src.core.strategy_base import UserStrategy
import pandas as pd
import numpy as np

class MyBollinger(UserStrategy):
    """布林帶突破策略示例"""
    
    def __init__(self):
        super().__init__()
        self.period = 20
        self.std_mult = 2.0
    
    def next(self, df: pd.DataFrame) -> int:
        if len(df) < self.period:
            return 0
        
        close = df['close']
        sma = close.tail(self.period).mean()
        std = close.tail(self.period).std()
        
        upper = sma + self.std_mult * std
        lower = sma - self.std_mult * std
        
        current_price = close.iloc[-1]
        
        # 跌破下軌：買入
        if current_price < lower:
            return 1
        
        # 突破上軌：賣出
        if current_price > upper:
            return -1
        
        return 0
''',
        },
    ]

    return {
        "success": True,
        "examples": examples,
        "total": len(examples),
        "note": "這些示例僅供參考，實際使用請根據需求調整參數",
    }
