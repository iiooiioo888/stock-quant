"""
stock-quant 項目級 MCP Server（stdio）— Cursor / Claude Desktop 接入入口。

暴露全項目只讀 tools：核心域（sq_*）+ 業務域（polymarket_* 等）。
啟動：python -m src.integrations.mcp.server
依賴：pip install -r requirements-mcp.txt
"""
import asyncio
import json
import sys
from pathlib import Path

# 確保項目根在目錄路徑（從任意 cwd 啟動）
_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.integrations.mcp.registry import get_all_tools, get_tool_by_name, tool_domains


def _run_stdio():
    """使用 mcp SDK 啟動 stdio Server。"""
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import TextContent, Tool

    # 項目級 Server 名稱（非單域）
    app = Server("stock-quant")

    @app.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name=spec.name,
                description=spec.description,
                inputSchema=spec.input_schema,
            )
            for spec in get_all_tools()
        ]

    @app.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        spec = get_tool_by_name(name)
        if spec is None:
            domains = tool_domains()
            return [TextContent(
                type="text",
                text=json.dumps({
                    "error": f"未知 tool: {name}",
                    "available_domains": domains,
                }, ensure_ascii=False),
            )]
        text = spec.handler(arguments or {})
        return [TextContent(type="text", text=text)]

    async def main():
        async with stdio_server() as (read_stream, write_stream):
            await app.run(read_stream, write_stream, app.create_initialization_options())

    asyncio.run(main())


if __name__ == "__main__":
    try:
        _run_stdio()
    except ImportError:
        print(
            "缺少 mcp 包。請執行: pip install -r requirements-mcp.txt",
            file=sys.stderr,
        )
        sys.exit(1)
