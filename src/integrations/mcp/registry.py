"""
MCP Tool 註冊中心 — 聚合全項目各域 tools，供 stdio Server 統一暴露。

擴展方式：
1. 在 tools_<domain>.py 定義 ToolSpec 列表
2. 在本文件 ALL_TOOL_MODULES 中 import 並 extend
3. 勿在 server.py 硬編碼單域 tools
"""

from src.integrations.mcp.protocol import ToolSpec
from src.integrations.mcp.tools_backtest import BACKTEST_TOOLS
from src.integrations.mcp.tools_core import CORE_TOOLS
from src.integrations.mcp.tools_data import DATA_TOOLS
from src.integrations.mcp.tools_observability import OBSERVABILITY_TOOLS
from src.integrations.mcp.utils import safe_handler

ALL_TOOL_MODULES: list[list[ToolSpec]] = [
    CORE_TOOLS,
    DATA_TOOLS,
    BACKTEST_TOOLS,
    OBSERVABILITY_TOOLS,
]

# 啟動時扁平化；禁止重名
_ALL_TOOLS: list[ToolSpec] | None = None


def get_all_tools() -> list[ToolSpec]:
    """返回已註冊的全部 MCP tools（懶加載 + 重名檢查）。"""
    global _ALL_TOOLS
    if _ALL_TOOLS is not None:
        return _ALL_TOOLS

    merged: list[ToolSpec] = []
    seen: set[str] = set()
    for group in ALL_TOOL_MODULES:
        for spec in group:
            if spec.name in seen:
                raise ValueError(f"MCP tool 名稱衝突: {spec.name}")
            seen.add(spec.name)
            merged.append(
                ToolSpec(
                    name=spec.name,
                    description=spec.description,
                    input_schema=spec.input_schema,
                    handler=safe_handler(spec.name, spec.handler),
                )
            )
    _ALL_TOOLS = merged
    return _ALL_TOOLS


def get_tool_by_name(name: str) -> ToolSpec | None:
    """按名稱查找 tool 定義。"""
    for spec in get_all_tools():
        if spec.name == name:
            return spec
    return None


def tool_domains() -> dict[str, list[str]]:
    """按名稱前綴分組，供文檔與調試。"""
    domains: dict[str, list[str]] = {}
    for spec in get_all_tools():
        if spec.name.startswith("sq_"):
            key = "stock_quant"
        else:
            key = "other"
        domains.setdefault(key, []).append(spec.name)
    return domains
