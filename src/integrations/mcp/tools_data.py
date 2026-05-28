"""
數據查詢 MCP Tools — 供 LLM / MCP 調用，與 REST 共用 src.core。
"""
from src.integrations.mcp.protocol import ToolSpec, build_input_schema
from src.integrations.mcp.utils import ERR_NOT_FOUND, ERR_VALIDATION, error_result, json_result


def _trim_list(items: list, limit: int = 20) -> list:
    if not isinstance(items, list):
        return []
    return items[: max(1, min(int(limit or 20), 50))]


def handle_sq_search_stocks(args: dict) -> str:
    """按關鍵字搜索 A 股股票池。"""
    try:
        from src.core.stock_universe import query_stock_universe

        keyword = str(args.get("keyword") or "").strip()
        limit = int(args.get("limit") or 20)
        rows, total = query_stock_universe(market="a_share", keyword=keyword or None, limit=limit, offset=0)
        stocks = [
            {
                "code": r.get("code"),
                "name": r.get("name"),
                "industry": r.get("industry"),
                "market_cap_rank": r.get("rank_mv"),
            }
            for r in _trim_list(rows, limit)
        ]
        return json_result({"keyword": keyword, "stocks": stocks, "total": total, "shown": len(stocks)})
    except Exception as e:
        return error_result(str(e))


def handle_sq_stock_overview(args: dict) -> str:
    """單股技術與區間概覽。"""
    try:
        from src.core.stock_basics import build_stock_overview

        code = str(args.get("code") or "").strip()
        lookback = int(args.get("lookback") or 120)
        if not code:
            return error_result("請提供 code", code=ERR_VALIDATION)
        overview = build_stock_overview(code, lookback=min(max(lookback, 20), 250))
        return json_result({"overview": overview})
    except Exception as e:
        return error_result(str(e))


def handle_sq_stock_fundamentals(args: dict) -> str:
    """單股基本面。"""
    try:
        from src.core.fundamental import get_fundamentals

        code = str(args.get("code") or "").strip()
        if not code:
            return error_result("請提供 code", code=ERR_VALIDATION)
        data = get_fundamentals(code)
        return json_result({"code": code, "fundamentals": data or {}})
    except Exception as e:
        return error_result(str(e))


def handle_sq_north_flow(args: dict) -> str:
    """北向資金（滬深港通）近期流向。"""
    try:
        from src.core.capital_flow import aggregate_north_flow_daily, get_north_flow

        days = int(args.get("days") or 20)
        flows = get_north_flow(days=min(max(days, 5), 60))
        daily = aggregate_north_flow_daily(flows)
        return json_result({
            "days": days,
            "daily": _trim_list(daily, 20),
            "latest": daily[-1] if daily else None,
            "raw_count": len(flows),
        })
    except Exception as e:
        return error_result(str(e))


def handle_sq_market_flow(args: dict) -> str:
    """大盤資金流向。"""
    try:
        from src.core.capital_flow import get_market_capital_flow

        flows = get_market_capital_flow()
        return json_result({"flows": _trim_list(flows, 15), "total": len(flows)})
    except Exception as e:
        return error_result(str(e))


def handle_sq_sector_rotation(args: dict) -> str:
    """板塊輪動 / 強弱概覽。"""
    try:
        from src.core.sector import get_sector_rotation

        days = int(args.get("days") or 10)
        rotation = get_sector_rotation(days=min(max(days, 5), 30))
        return json_result({"rotation": _trim_list(rotation, 25), "total": len(rotation), "days": days})
    except Exception as e:
        return error_result(str(e))


def handle_sq_current_signals(args: dict) -> str:
    """當前策略信號（可選單股）。"""
    try:
        from src.core.signals import get_current_signals_for_codes

        code = str(args.get("code") or "").strip()
        if code:
            rows = get_current_signals_for_codes([code])
        else:
            from src.config import settings
            codes = list(settings.watchlist)[:12]
            rows = get_current_signals_for_codes(codes)
        slim = []
        for row in _trim_list(rows, 15):
            sigs = row.get("signals") or []
            slim.append({
                "code": row.get("code"),
                "name": row.get("name"),
                "signal_count": len(sigs),
                "top_signals": sigs[:5],
                "updated_at": row.get("updated_at"),
            })
        return json_result({"items": slim, "total": len(slim)})
    except Exception as e:
        return error_result(str(e))


def handle_sq_backtest_history(args: dict) -> str:
    """近期回測歷史記錄。"""
    try:
        from src.core.db import get_backtest_history

        code = str(args.get("code") or "").strip() or None
        strategy = str(args.get("strategy") or "").strip() or None
        limit = int(args.get("limit") or 10)
        rows = get_backtest_history(code=code, strategy=strategy, limit=min(max(limit, 1), 30))
        slim = []
        for r in rows:
            slim.append({
                "id": r.get("id"),
                "code": r.get("code"),
                "strategy": r.get("strategy"),
                "strategy_name": r.get("strategy_name"),
                "total_return_pct": r.get("total_return_pct"),
                "max_drawdown_pct": r.get("max_drawdown_pct"),
                "sharpe_ratio": r.get("sharpe_ratio"),
                "win_rate_pct": r.get("win_rate_pct"),
                "total_trades": r.get("total_trades"),
                "created_at": r.get("created_at"),
            })
        return json_result({"history": slim, "total": len(slim)})
    except Exception as e:
        return error_result(str(e))


def handle_sq_stock_capital_flow(args: dict) -> str:
    """單股資金流向。"""
    try:
        from src.core.capital_flow import get_capital_flow

        code = str(args.get("code") or "").strip()
        days = int(args.get("days") or 15)
        if not code:
            return error_result("請提供 code", code=ERR_VALIDATION)
        flows = get_capital_flow(code, days=min(max(days, 5), 40))
        return json_result({"code": code, "flows": _trim_list(flows, days), "total": len(flows)})
    except Exception as e:
        return error_result(str(e))


DATA_TOOLS: list[ToolSpec] = [
    ToolSpec(
        name="sq_search_stocks",
        description="在本地 A 股股票池中按代碼或名稱關鍵字搜索。",
        input_schema=build_input_schema({
            "keyword": {"type": "string", "description": "代碼或名稱關鍵字"},
            "limit": {"type": "integer", "description": "返回條數，默認 20"},
        }, required=["keyword"]),
        handler=handle_sq_search_stocks,
    ),
    ToolSpec(
        name="sq_stock_overview",
        description="獲取單股技術指標、區間漲跌幅、均線等概覽。",
        input_schema=build_input_schema({
            "code": {"type": "string", "description": "6 位 A 股代碼"},
            "lookback": {"type": "integer", "description": "回看交易日，默認 120"},
        }, required=["code"]),
        handler=handle_sq_stock_overview,
    ),
    ToolSpec(
        name="sq_stock_fundamentals",
        description="獲取單股基本面（PE、PB、營收增速等）。",
        input_schema=build_input_schema({
            "code": {"type": "string", "description": "6 位 A 股代碼"},
        }, required=["code"]),
        handler=handle_sq_stock_fundamentals,
    ),
    ToolSpec(
        name="sq_stock_capital_flow",
        description="獲取單股近期資金流向。",
        input_schema=build_input_schema({
            "code": {"type": "string", "description": "6 位 A 股代碼"},
            "days": {"type": "integer", "description": "天數，默認 15"},
        }, required=["code"]),
        handler=handle_sq_stock_capital_flow,
    ),
    ToolSpec(
        name="sq_north_flow",
        description="北向資金（滬深港通）近期每日淨流入匯總。",
        input_schema=build_input_schema({
            "days": {"type": "integer", "description": "回看天數，默認 20"},
        }),
        handler=handle_sq_north_flow,
    ),
    ToolSpec(
        name="sq_market_flow",
        description="大盤級別資金流向。",
        input_schema=build_input_schema({}),
        handler=handle_sq_market_flow,
    ),
    ToolSpec(
        name="sq_sector_rotation",
        description="行業板塊輪動與強弱排名。",
        input_schema=build_input_schema({}),
        handler=handle_sq_sector_rotation,
    ),
    ToolSpec(
        name="sq_current_signals",
        description="系統當前策略信號；可指定單股或返回自選股樣本。",
        input_schema=build_input_schema({
            "code": {"type": "string", "description": "可選，6 位代碼"},
        }),
        handler=handle_sq_current_signals,
    ),
    ToolSpec(
        name="sq_backtest_history",
        description="查詢本地回測歷史摘要。",
        input_schema=build_input_schema({
            "code": {"type": "string", "description": "可選股票代碼"},
            "strategy": {"type": "string", "description": "可選策略 key"},
            "limit": {"type": "integer", "description": "條數，默認 10"},
        }),
        handler=handle_sq_backtest_history,
    ),
]
