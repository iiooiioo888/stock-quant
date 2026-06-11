"""
回測任務 MCP Tools — 供 LLM 提交與查詢異步回測。
"""

from src.integrations.mcp.protocol import ToolSpec, build_input_schema
from src.integrations.mcp.utils import (
    ERR_NOT_FOUND,
    ERR_VALIDATION,
    error_result,
    json_result,
)


def _task_summary(task: dict) -> dict:
    if not task:
        return {}
    out = {
        "task_id": task.get("task_id"),
        "task_type": task.get("task_type"),
        "status": task.get("status"),
        "progress": task.get("progress"),
        "title": task.get("title"),
        "error": task.get("error"),
        "created_at": task.get("created_at"),
        "completed_at": task.get("completed_at"),
    }
    result = task.get("result")
    if isinstance(result, dict):
        out["result_preview"] = {
            "code": result.get("code"),
            "strategy": result.get("strategy"),
            "strategy_name": result.get("strategy_name"),
            "total_return_pct": result.get("total_return_pct"),
            "max_drawdown_pct": result.get("max_drawdown_pct"),
            "sharpe_ratio": result.get("sharpe_ratio"),
            "win_rate_pct": result.get("win_rate_pct"),
            "total_trades": result.get("total_trades"),
        }
    elif isinstance(result, list):
        out["result_preview"] = {"strategies_count": len(result), "top": result[:3]}
    return out


def handle_sq_run_backtest(args: dict) -> str:
    """提交單策略進階回測任務（異步）。"""
    try:
        from src.api.dispatch import dispatch_async_task
        from src.core.backtest import STRATEGIES, run_backtest
        from src.core.kline_timeframe import normalize_timeframe
        from src.core.task_manager import create_task

        code = str(args.get("code") or "").strip()
        strategy = str(args.get("strategy") or "dual_ma").strip()
        if not code:
            return error_result("請提供 code", code=ERR_VALIDATION)
        if strategy not in STRATEGIES:
            return error_result(f"未知策略: {strategy}", code=ERR_VALIDATION)

        timeframe = str(args.get("timeframe") or "1d").strip()
        try:
            timeframe = normalize_timeframe(timeframe)
        except ValueError as e:
            return error_result(str(e), code=ERR_VALIDATION)

        cash = args.get("cash")
        commission = args.get("commission")
        slippage_pct = float(args.get("slippage_pct") or 0.0)
        enable_t1 = args.get("enable_t1", True)
        enable_limit = args.get("enable_limit", True)
        force_refresh = bool(args.get("force_refresh") or args.get("force"))

        task_params = {
            "code": code,
            "strategy": strategy,
            "params": args.get("params"),
            "cash": cash,
            "commission": commission,
            "slippage_pct": slippage_pct,
            "enable_t1": enable_t1,
            "enable_limit": enable_limit,
            "timeframe": timeframe,
        }
        if force_refresh:
            from src.core.result_cache import drop_cached_compute

            drop_cached_compute("backtest_advanced", task_params, code=code)

        task = create_task(
            "backtest_advanced",
            task_params,
            title=f"AI 回測 {code}/{strategy}",
            force_refresh=force_refresh,
        )
        if task.get("is_duplicate"):
            return json_result(
                {
                    "task_id": task["task_id"],
                    "async": True,
                    "is_duplicate": True,
                    "message": "相同回測正在執行，請稍後用 sq_get_task 查詢",
                }
            )

        task_id = task["task_id"]

        if task.get("status") == "completed" and task.get("result") is not None:
            return json_result(
                {
                    "task_id": task_id,
                    "async": False,
                    "from_cache": bool(task.get("from_cache")),
                    "message": "緩存命中，已完成",
                    "result_preview": _task_summary(task).get("result_preview"),
                }
            )

        def _work():
            return run_backtest(
                code,
                strategy_name=strategy,
                params=args.get("params"),
                cash=cash,
                commission=commission,
                slippage_pct=slippage_pct,
                enable_t1=enable_t1,
                enable_limit=enable_limit,
                timeframe=timeframe,
                task_id=task_id,
            )

        dispatched = dispatch_async_task(
            task_id,
            _work,
            cache_namespace="backtest_advanced",
            cache_params=task_params,
            cache_code=code,
        )
        return json_result(
            {
                "task_id": task_id,
                "async": bool(dispatched.get("async")),
                "from_cache": bool(dispatched.get("from_cache")),
                "message": "已提交回測" if dispatched.get("async") else "回測已完成",
                "result_preview": (
                    _task_summary({"result": dispatched.get("result")}).get(
                        "result_preview"
                    )
                    if not dispatched.get("async")
                    else None
                ),
            }
        )
    except Exception as e:
        return error_result(str(e))


def handle_sq_run_multi_backtest(args: dict) -> str:
    """提交多策略對比回測（異步）。"""
    try:
        from src.api.dispatch import dispatch_async_task
        from src.core.backtest import run_multi_strategy
        from src.core.task_manager import create_task

        code = str(args.get("code") or "").strip()
        if not code:
            return error_result("請提供 code", code=ERR_VALIDATION)

        task_params = {"code": code}
        task = create_task("backtest_multi", task_params, title=f"AI 多策略 {code}")
        if task.get("is_duplicate"):
            return json_result(
                {
                    "task_id": task["task_id"],
                    "async": True,
                    "is_duplicate": True,
                    "message": "多策略對比進行中，請用 sq_get_task 查詢",
                }
            )

        task_id = task["task_id"]
        if task.get("status") == "completed" and task.get("result") is not None:
            return json_result(
                {
                    "task_id": task_id,
                    "async": False,
                    "message": "已完成（緩存）",
                    "strategies_count": len(task.get("result") or []),
                }
            )

        dispatched = dispatch_async_task(
            task_id,
            lambda: run_multi_strategy(code, task_id=task_id),
            cache_namespace="backtest_multi",
            cache_params=task_params,
            cache_code=code,
        )
        return json_result(
            {
                "task_id": task_id,
                "async": bool(dispatched.get("async")),
                "message": "已提交多策略回測" if dispatched.get("async") else "已完成",
            }
        )
    except Exception as e:
        return error_result(str(e))


def handle_sq_get_task(args: dict) -> str:
    """查詢異步任務狀態與結果摘要。"""
    try:
        from src.core.task_manager import get_task

        task_id = str(args.get("task_id") or "").strip()
        if not task_id:
            return error_result("請提供 task_id", code=ERR_VALIDATION)
        task = get_task(task_id)
        if not task:
            return error_result(f"任務不存在: {task_id}", code=ERR_NOT_FOUND)
        return json_result(_task_summary(task))
    except Exception as e:
        return error_result(str(e))


BACKTEST_TOOLS: list[ToolSpec] = [
    ToolSpec(
        name="sq_run_backtest",
        description="提交單股單策略進階回測（異步）。完成後用 sq_get_task 查 task_id。",
        input_schema=build_input_schema(
            {
                "code": {"type": "string", "description": "6 位 A 股代碼"},
                "strategy": {"type": "string", "description": "策略 key，默認 dual_ma"},
                "timeframe": {"type": "string", "description": "1d / 1h / 1m"},
                "cash": {"type": "number", "description": "初始資金"},
                "force_refresh": {"type": "boolean", "description": "忽略緩存強制重算"},
            },
            required=["code"],
        ),
        handler=handle_sq_run_backtest,
    ),
    ToolSpec(
        name="sq_run_multi_backtest",
        description="對單股運行全部內置策略對比（異步，耗時較長）。",
        input_schema=build_input_schema(
            {
                "code": {"type": "string", "description": "6 位 A 股代碼"},
            },
            required=["code"],
        ),
        handler=handle_sq_run_multi_backtest,
    ),
    ToolSpec(
        name="sq_get_task",
        description="查詢回測/下載等異步任務的進度與結果摘要。",
        input_schema=build_input_schema(
            {
                "task_id": {"type": "string", "description": "任務 ID"},
            },
            required=["task_id"],
        ),
        handler=handle_sq_get_task,
    ),
]
