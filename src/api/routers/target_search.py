"""目標導向回測搜尋 API"""

from fastapi import APIRouter, HTTPException

from src.api.dispatch import dispatch_async_task

router = APIRouter()


@router.post("/api/backtest/target-search")
async def run_target_search_api(
    code: str,
    strategy: str = "dual_ma",
    target_metric: str = "sharpe_ratio",  # sharpe_ratio / total_return_pct / win_rate_pct / max_drawdown_pct
    target_value: float = 1.5,
    method: str = "optuna",  # optuna / random / grid
    max_iter: int = 500,
    timeout_seconds: int = 3600,
    objective: str = "maximize",  # maximize / minimize
):
    """循環回測直至達成目標，支援 Optuna / Random / Grid 搜索（異步任務）"""
    from src.core.target_search import target_search
    from src.core.backtest import STRATEGIES
    from src.core.task_manager import create_task

    if not code:
        raise HTTPException(400, "請提供股票代碼")
    if strategy not in STRATEGIES:
        raise HTTPException(400, f"未知策略: {strategy}，可選: {list(STRATEGIES.keys())}")

    task_params = {
        "code": code,
        "strategy": strategy,
        "target_metric": target_metric,
        "target_value": target_value,
        "method": method,
        "objective": objective,
        "max_iter": max_iter,
        "timeout_seconds": timeout_seconds,
    }

    task = create_task(
        "target_search",
        task_params,
        title=f"目標搜索 {code}/{strategy} ({target_metric} {objective} {target_value})",
    )
    if task.get("is_duplicate"):
        return {"success": True, "task_id": task["task_id"], "is_duplicate": True, "async": True}

    task_id = task["task_id"]

    def _work():
        return target_search(
            code=code,
            strategy_name=strategy,
            target_metric=target_metric,
            target_value=target_value,
            method=method,
            max_iter=max_iter,
            timeout_seconds=timeout_seconds,
            objective=objective,
            task_id=task_id,
        )

    return dispatch_async_task(
        task_id,
        _work,
        cache_namespace="target_search",
        cache_params=task_params,
        cache_code=code,
    )

