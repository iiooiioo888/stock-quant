# stock-quant MCP Server（全項目）

Model Context Protocol (MCP) 為 **整個 stock-quant 項目** 提供 stdio 工具接入，供 Cursor / Claude Desktop 等 Agent 調用本地量化能力（只讀為主）。

## 架構

```
src/integrations/mcp/
├── server.py          # 項目級 stdio 入口（Server 名稱: stock-quant）
├── registry.py        # 聚合各域 tools
├── protocol.py        # ToolSpec 契約
├── utils.py           # JSON 輸出格式
├── tools_core.py      # 核心域 sq_*（健康、策略、任務、數據源）
```

擴展新域：新增 `tools_<domain>.py`，在 `registry.py` 的 `ALL_TOOL_MODULES` 註冊。

## 安裝

```bash
pip install -r requirements-mcp.txt
```

主應用 `requirements.txt` 不依賴 `mcp`。

## 啟動

```bash
cd e:\Jerry_python\stock-quant
python -m src.integrations.mcp.server
```

## Cursor 配置

```json
{
  "mcpServers": {
    "stock-quant": {
      "command": "python",
      "args": ["-m", "src.integrations.mcp.server"],
      "cwd": "E:/Jerry_python/stock-quant",
      "env": {}
    }
  }
}
```

## 已註冊 Tools

### 核心域（`sq_*`）

| Tool | 說明 |
|------|------|
| `sq_health` | 系統健康 + 數據庫統計 |
| `sq_config_summary` | 脫敏配置摘要 |
| `sq_list_strategies` | 19 種內置回測策略 |
| `sq_stock_universe_stats` | A 股股票池統計 |
| `sq_list_tasks` | 最近異步任務 |
| `sq_data_sources` | 全項目數據源熔斷狀態 |

## 與 REST API 的關係

- MCP tools 調用 `src.core` 業務層，與 FastAPI `/api/*` 共用邏輯。
- 新增能力時：先實現 Service → 再掛 REST → 最後在對應 `tools_*.py` 註冊 MCP。

## 環境變量

MCP 進程繼承與 Web 相同的 `SQ_*` 配置（見 `.env.example`），例如：

- `SQ_DB_PATH` — 本地數據庫路徑
