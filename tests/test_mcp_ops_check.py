"""MCP sq_ops_check tool。"""

import json

from src.integrations.mcp.tools_observability import handle_sq_ops_check


def test_sq_ops_check_returns_sop_fields():
    raw = handle_sq_ops_check({})
    data = json.loads(raw)
    assert data.get("ok") is True
    assert data.get("verdict") in ("ok", "attention", "critical")
    assert "verdict_zh" in data
    assert isinstance(data.get("checks"), list)
    assert "checked_at" in data
    assert "index_audit" in data
