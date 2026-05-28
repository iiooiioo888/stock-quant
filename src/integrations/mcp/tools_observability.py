"""
觀測與運維 MCP Tools — 管線指標、索引健檢。
"""
from src.integrations.mcp.protocol import ToolSpec, build_input_schema
from src.integrations.mcp.utils import error_result, json_result


def handle_sq_pipeline_metrics(_args: dict) -> str:
    """數據管線進程內指標（快取、K 線、財報）。"""
    try:
        from src.core.pipeline_observability import get_pipeline_metrics

        return json_result(get_pipeline_metrics())
    except Exception as e:
        return error_result(str(e), code="INTERNAL_ERROR")


def handle_sq_db_index_audit(args: dict) -> str:
    """SQLite 索引健檢；可選 apply_missing 自動補建缺失索引。"""
    try:
        from src.core.database.index_audit import audit_indexes, ensure_missing_indexes

        apply = bool(args.get("apply_missing"))
        if apply:
            result = ensure_missing_indexes()
        else:
            result = {"audit": audit_indexes()}
        return json_result(result)
    except Exception as e:
        return error_result(str(e), code="INTERNAL_ERROR")


OBSERVABILITY_TOOLS: list[ToolSpec] = [
    ToolSpec(
        name="sq_pipeline_metrics",
        description="數據管線觀測指標：快取 defer/flush、K 線寫入與拉取來源、財報命中路徑。",
        input_schema=build_input_schema({}),
        handler=handle_sq_pipeline_metrics,
    ),
    ToolSpec(
        name="sq_db_index_audit",
        description="SQLite 索引健檢；apply_missing=true 時自動建立缺失索引。",
        input_schema=build_input_schema({
            "apply_missing": {
                "type": "boolean",
                "description": "是否自動執行 CREATE INDEX IF NOT EXISTS",
            },
        }),
        handler=handle_sq_db_index_audit,
    ),
]
