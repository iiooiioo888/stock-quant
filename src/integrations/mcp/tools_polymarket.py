"""
Polymarket 域 MCP Tools — 預測市場子集，註冊到全項目 MCP Server。

前綴 polymarket_ 與核心域 sq_ 區分；業務邏輯在 PolymarketService。
"""
from src.core.polymarket.service import (
    PolymarketDisabledError,
    get_polymarket_service,
)
from src.integrations.mcp.protocol import ToolSpec, build_input_schema
from src.integrations.mcp.utils import error_result, json_result


def handle_polymarket_list_markets(args: dict) -> str:
    """Tool: polymarket_list_markets — 列出預測市場。"""
    try:
        svc = get_polymarket_service()
        limit = int(args.get("limit") or 20)
        tag = args.get("tag")
        active = args.get("active", True)
        if isinstance(active, str):
            active = active.lower() in ("true", "1", "yes")
        return json_result(svc.list_markets(limit=limit, tag=tag, active=active))
    except PolymarketDisabledError as e:
        return error_result(str(e))
    except Exception as e:
        return error_result(str(e))


def handle_polymarket_get_market(args: dict) -> str:
    """Tool: polymarket_get_market — 市場詳情。"""
    key = (args.get("market_id_or_slug") or "").strip()
    if not key:
        return error_result("market_id_or_slug 必填")
    try:
        return json_result(get_polymarket_service().get_market(key))
    except PolymarketDisabledError as e:
        return error_result(str(e))
    except Exception as e:
        return error_result(str(e))


def handle_polymarket_get_orderbook(args: dict) -> str:
    """Tool: polymarket_get_orderbook — 訂單簿與價差。"""
    token_id = (args.get("token_id") or "").strip()
    if not token_id:
        return error_result("token_id 必填")
    try:
        return json_result(get_polymarket_service().get_orderbook(token_id))
    except PolymarketDisabledError as e:
        return error_result(str(e))
    except Exception as e:
        return error_result(str(e))


def _handle_polymarket_evaluate_alerts(_args: dict) -> str:
    from src.core.polymarket.alerts import run_polymarket_alert_cycle
    try:
        return json_result(run_polymarket_alert_cycle())
    except PolymarketDisabledError as e:
        return error_result(str(e))
    except Exception as e:
        return error_result(str(e))


def _handle_polymarket_strategy_signals(args: dict) -> str:
    from src.core.polymarket.strategy_signals import compute_strategy_signals
    try:
        limit = int(args.get("limit") or 20)
        tag = args.get("tag")
        return json_result(compute_strategy_signals(limit=limit, tag=tag))
    except PolymarketDisabledError as e:
        return error_result(str(e))
    except Exception as e:
        return error_result(str(e))


# 註冊表：未來新增 tool 在此 append
POLYMARKET_TOOLS: list[ToolSpec] = [
    ToolSpec(
        name="polymarket_list_markets",
        description="列出 Polymarket 預測市場（問題、Yes/No 機率、成交量）。可選 tag 篩選。",
        input_schema=build_input_schema(
            {
                "limit": {"type": "integer", "description": "返回條數，默認 20"},
                "tag": {"type": "string", "description": "標籤 slug，可選"},
                "active": {"type": "boolean", "description": "僅活躍市場，默認 true"},
            },
        ),
        handler=handle_polymarket_list_markets,
    ),
    ToolSpec(
        name="polymarket_get_market",
        description="獲取單個 Polymarket 市場詳情（slug 或 market id）。",
        input_schema=build_input_schema(
            {
                "market_id_or_slug": {
                    "type": "string",
                    "description": "市場 slug 或 condition id",
                },
            },
            required=["market_id_or_slug"],
        ),
        handler=handle_polymarket_get_market,
    ),
    ToolSpec(
        name="polymarket_get_orderbook",
        description="獲取 Polymarket CLOB 訂單簿（需 Yes 或 No 的 token_id）。",
        input_schema=build_input_schema(
            {
                "token_id": {"type": "string", "description": "CLOB token id"},
            },
            required=["token_id"],
        ),
        handler=handle_polymarket_get_orderbook,
    ),
    ToolSpec(
        name="polymarket_evaluate_alerts",
        description="執行一輪 Polymarket 概率預警評估（yes 閾值/變動幅度），觸發則發通知。",
        input_schema=build_input_schema({}),
        handler=_handle_polymarket_evaluate_alerts,
    ),
    ToolSpec(
        name="polymarket_strategy_signals",
        description="批量計算 Polymarket 概率驅動策略信號（偏多/偏空/觀望）。",
        input_schema=build_input_schema(
            {
                "limit": {"type": "integer", "description": "市場數量上限，默認 20"},
                "tag": {"type": "string", "description": "標籤 slug，可選"},
            },
        ),
        handler=_handle_polymarket_strategy_signals,
    ),
]
