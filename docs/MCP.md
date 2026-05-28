# stock-quant MCP Server（全項目）

Model Context Protocol (MCP) 為 **整個 stock-quant 項目** 提供 stdio 工具接入，供 Cursor / Claude Desktop 等 Agent 調用本地量化能力（只讀為主）。

## 架構

```
src/integrations/mcp/
├── server.py              # 項目級 stdio 入口（Server 名稱: stock-quant）
├── registry.py            # 聚合各域 tools（含 safe_handler 統一錯誤捕獲）
├── protocol.py            # ToolSpec 契約
├── utils.py               # JSON 成功/錯誤封裝
├── tools_core.py          # 核心域 sq_*（健康、策略、任務、數據源）
├── tools_data.py          # 數據查詢
├── tools_backtest.py      # 回測任務
└── tools_observability.py # 管線指標、索引健檢
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

## 回應格式

**成功**（`json_result`）：

```json
{
  "ok": true,
  "status": "ok",
  "...": "..."
}
```

**失敗**（`error_result`）：

```json
{
  "ok": false,
  "error_code": "VALIDATION_ERROR",
  "error": "請提供 code",
  "tool": "sq_stock_overview"
}
```

| error_code | 說明 |
|------------|------|
| `VALIDATION_ERROR` | 參數錯誤 |
| `NOT_FOUND` | 資源不存在 |
| `INTERNAL_ERROR` | 內部異常 |
| `UNKNOWN_TOOL` | 未註冊的 tool 名稱 |

## 已註冊 Tools

### 核心域

| Tool | 說明 |
|------|------|
| `sq_health` | 系統健康 + DB 統計 + 管線指標摘要 + 索引健檢摘要 |
| `sq_config_summary` | 脫敏配置摘要 |
| `sq_list_strategies` | 19 種內置回測策略 |
| `sq_stock_universe_stats` | A 股股票池統計 |
| `sq_list_tasks` | 最近異步任務 |
| `sq_data_sources` | 全項目數據源熔斷狀態 |

### 觀測 / 運維

| Tool | 說明 |
|------|------|
| `sq_pipeline_metrics` | 數據管線進程內指標（快取、K 線、財報） |
| `sq_db_index_audit` | SQLite 索引健檢；`apply_missing=true` 自動補建 |

### 數據 / 回測

見 `tools_data.py`、`tools_backtest.py`（`sq_search_stocks`、`sq_run_backtest` 等）。

## 與 REST API 的關係

- MCP tools 調用 `src.core` 業務層，與 FastAPI `/api/*` 共用邏輯。
- 新增能力時：先實現 Service → 再掛 REST → 最後在對應 `tools_*.py` 註冊 MCP。
- 詳細運維手冊：[runbooks/data-pipeline.md](runbooks/data-pipeline.md)

## 環境變量

MCP 進程繼承與 Web 相同的 `SQ_*` 配置（見 `.env.example`），例如：

- `SQ_DB_PATH` — 本地數據庫路徑
