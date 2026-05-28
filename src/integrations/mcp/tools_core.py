"""
stock-quant 核心 MCP Tools — 系統、策略、股票池、任務（只讀）。

與 FastAPI 共用 src.core / src.config，不繞過業務層直接拼 HTTP。
"""
from src.config import settings
from src.integrations.mcp.protocol import ToolSpec, build_input_schema
from src.integrations.mcp.utils import ERR_INTERNAL, error_result, json_result


def handle_sq_health(_args: dict) -> str:
    """系統健康與數據庫概況。"""
    try:
        from src.core.db import get_db_stats
        from src.core.database.index_audit import audit_indexes
        from src.core.pipeline_observability import get_pipeline_metrics

        stats = get_db_stats()
        index_audit = audit_indexes()
        pipeline = get_pipeline_metrics()
        return json_result({
            "status": "ok",
            "app": settings.app_name,
            "version": settings.app_version,
            "database": stats,
            "index_audit": {
                "ok": index_audit.get("ok"),
                "present_count": index_audit.get("present_count"),
                "expected_count": index_audit.get("expected_count"),
                "missing_count": len(index_audit.get("missing") or []),
            },
            "pipeline_metrics": pipeline,
        })
    except Exception as e:
        return error_result(str(e), code=ERR_INTERNAL)


def handle_sq_config_summary(_args: dict) -> str:
    """脫敏配置摘要（不含密鑰）。"""
    try:
        return json_result({
            "summary_text": settings.summary(),
            "demo_mode": settings.demo_mode,
        })
    except Exception as e:
        return error_result(str(e))


def handle_sq_list_strategies(_args: dict) -> str:
    """列出內置回測策略及中文名。"""
    try:
        from src.core.backtest import STRATEGIES, STRATEGY_NAMES

        items = [
            {
                "id": key,
                "name_zh": STRATEGY_NAMES.get(key, key),
                "has_default_params": key in settings.strategy_params,
            }
            for key in sorted(STRATEGIES.keys())
        ]
        return json_result({"strategies": items, "total": len(items)})
    except Exception as e:
        return error_result(str(e))


def handle_sq_stock_universe_stats(_args: dict) -> str:
    """股票池統計（本地 SQLite）。"""
    try:
        from src.core.stock_universe import get_universe_stats

        return json_result(get_universe_stats())
    except Exception as e:
        return error_result(str(e))


def handle_sq_list_tasks(args: dict) -> str:
    """最近異步任務列表。"""
    try:
        from src.core.task_manager import get_tasks

        limit = int(args.get("limit") or 20)
        tasks = get_tasks(limit=limit)
        return json_result({"tasks": tasks, "total": len(tasks), "limit": limit})
    except Exception as e:
        return error_result(str(e))


def handle_sq_data_sources(_args: dict) -> str:
    """各類數據源健康狀態。"""
    try:
        from src.core.data_sources import health_check

        return json_result(health_check())
    except Exception as e:
        return error_result(str(e))


# 核心域 tools 註冊表
CORE_TOOLS: list[ToolSpec] = [
    ToolSpec(
        name="sq_health",
        description="stock-quant 系統健康檢查與本地數據庫統計。",
        input_schema=build_input_schema({}),
        handler=handle_sq_health,
    ),
    ToolSpec(
        name="sq_config_summary",
        description="stock-quant 脫敏配置摘要（版本、盯盤、回測、緩存等）。",
        input_schema=build_input_schema({}),
        handler=handle_sq_config_summary,
    ),
    ToolSpec(
        name="sq_list_strategies",
        description="列出全部內置回測策略（19 種）及中文名稱。",
        input_schema=build_input_schema({}),
        handler=handle_sq_list_strategies,
    ),
    ToolSpec(
        name="sq_stock_universe_stats",
        description="A 股股票池本地統計（總數、市場分布等）。",
        input_schema=build_input_schema({}),
        handler=handle_sq_stock_universe_stats,
    ),
    ToolSpec(
        name="sq_list_tasks",
        description="列出最近異步任務（回測、下載等）。",
        input_schema=build_input_schema(
            {"limit": {"type": "integer", "description": "條數，默認 20"}},
        ),
        handler=handle_sq_list_tasks,
    ),
    ToolSpec(
        name="sq_data_sources",
        description="全項目數據源熔斷與可用性（A 股、加密、外匯等）。",
        input_schema=build_input_schema({}),
        handler=handle_sq_data_sources,
    ),
]
