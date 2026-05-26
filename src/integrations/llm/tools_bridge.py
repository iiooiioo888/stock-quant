"""
將 MCP ToolSpec 轉為 OpenAI function calling 格式並執行。
"""
from __future__ import annotations

import json
from typing import Any

from src.integrations.mcp.registry import get_all_tools, get_tool_by_name


def tools_for_llm() -> list[dict]:
    """OpenAI Chat Completions tools 列表。"""
    out = []
    for spec in get_all_tools():
        out.append({
            "type": "function",
            "function": {
                "name": spec.name,
                "description": spec.description,
                "parameters": spec.input_schema,
            },
        })
    return out


def tool_names_for_llm() -> list[str]:
    return [t["function"]["name"] for t in tools_for_llm()]


def execute_tool(name: str, arguments: dict | None) -> dict:
    """執行工具，返回 { ok, name, result_text, parsed }。"""
    spec = get_tool_by_name(name)
    if spec is None:
        return {"ok": False, "name": name, "error": f"未知工具: {name}"}
    args = arguments if isinstance(arguments, dict) else {}
    try:
        text = spec.handler(args)
    except Exception as e:
        return {"ok": False, "name": name, "error": str(e)}
    parsed: Any = None
    try:
        parsed = json.loads(text)
    except Exception:
        parsed = {"raw": text}
    if isinstance(parsed, dict) and parsed.get("error"):
        return {"ok": False, "name": name, "result_text": text, "parsed": parsed, "error": parsed["error"]}
    return {"ok": True, "name": name, "result_text": text, "parsed": parsed}
