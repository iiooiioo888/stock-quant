"""
MCP Tool 協議定義 — stock-quant 全項目 MCP 擴展契約。

設計原則：
- 每個業務域一個 tools_<domain>.py，在 registry.py 聚合
- handler 調用 src.core 業務層（與 REST 共用），禁止重複實現邏輯
- 返回 JSON 字符串供 LLM 消費（見 utils.json_result）
"""

from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class ToolSpec:
    """單個 MCP Tool 元數據。"""

    name: str
    description: str
    input_schema: dict
    handler: Callable[[dict], str]


def build_input_schema(properties: dict, required: list = None) -> dict:
    """生成 JSON Schema（MCP tools/list 用）。"""
    return {
        "type": "object",
        "properties": properties,
        "required": required or [],
    }
