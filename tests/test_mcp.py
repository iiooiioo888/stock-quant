"""全項目 MCP 註冊與 handlers（無需安裝 mcp SDK）。"""
import json
from unittest.mock import patch

import pytest


class TestMcpRegistry:
    def test_all_tools_unique_names(self):
        from src.integrations.mcp.registry import get_all_tools

        tools = get_all_tools()
        names = [t.name for t in tools]
        assert len(names) == len(set(names))
        assert "sq_health" in names
        assert "polymarket_list_markets" in names
        assert "polymarket_evaluate_alerts" in names
        assert "polymarket_strategy_signals" in names

    def test_tool_domains(self):
        from src.integrations.mcp.registry import tool_domains

        domains = tool_domains()
        assert "stock_quant" in domains
        assert "polymarket" in domains
        assert "sq_health" in domains["stock_quant"]

    def test_get_tool_by_name(self):
        from src.integrations.mcp.registry import get_tool_by_name

        assert get_tool_by_name("sq_health") is not None
        assert get_tool_by_name("nonexistent_tool_xyz") is None


class TestMcpCoreHandlers:
    def test_sq_health(self):
        from src.integrations.mcp.tools_core import handle_sq_health

        with patch("src.core.db.get_db_stats", return_value={"tables": 3}):
            text = handle_sq_health({})
        data = json.loads(text)
        assert data["status"] == "ok"
        assert data["database"]["tables"] == 3

    def test_sq_list_tasks(self):
        from src.integrations.mcp.tools_core import handle_sq_list_tasks

        with patch(
            "src.core.task_manager.get_tasks",
            return_value=[{"task_id": "t1", "status": "done"}],
        ):
            text = handle_sq_list_tasks({"limit": 5})
        data = json.loads(text)
        assert data["total"] == 1
        assert data["tasks"][0]["task_id"] == "t1"


class TestMcpPolymarketHandlers:
    def test_list_markets_tool(self):
        from src.integrations.mcp.tools_polymarket import handle_polymarket_list_markets

        with patch(
            "src.integrations.mcp.tools_polymarket.get_polymarket_service"
        ) as mock_get:
            mock_get.return_value.list_markets.return_value = {
                "markets": [],
                "total": 0,
            }
            text = handle_polymarket_list_markets({"limit": 5})
        assert "markets" in text
