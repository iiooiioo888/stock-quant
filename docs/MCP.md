# stock-quant MCP Server（全項目）

Model Context Protocol (MCP) 為 **整個 stock-quant 項目** 提供 stdio 工具接入，供 Cursor / Claude Desktop 等 Agent 調用本地量化能力（只讀為主）。

運維場景的完整 SOP（決策樹、事故表）見 **[runbooks/README.md](runbooks/README.md)**。

## 操作流程 SOP（精簡）

| 階段 | 步驟 | 說明 |
|------|------|------|
| **安裝** | `pip install -r requirements-mcp.txt` | 與 Web 依賴分離 |
| **IDE** | 使用 `.cursor/mcp.json` | 工作區根為 `cwd` |
| **手動檢查** | 依序呼叫 `sq_health` → `sq_pipeline_metrics` → `sq_db_index_audit` | 索引先勿 `apply_missing=true` |
| **本機檢查** | `python main.py ops check` | 無需 API key / 無需啟動 Web |
| **自動檢查** | `scripts/cursor-agent` 內 `npm run ops-check` | 需 `CURSOR_API_KEY` |
| **擴充** | 新增 `tools_<domain>.py` 並註冊 `registry.py` | 見 `.cursor/rules/mcp-tooling.mdc` |

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

專案已提供 [`.cursor/mcp.json`](../.cursor/mcp.json)，在 Cursor IDE 中會自動載入 `stock-quant` MCP（工作區根目錄為 `cwd`）。

手動覆寫範例（僅在需自訂 Python 路徑時）：

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

## Cursor SDK 自動化（CLI / CI）

除 IDE 外，可用 **Cursor TypeScript SDK**（`@cursor/sdk`）在本地以程式觸發 Agent，並掛載同一套 MCP。

### 一鍵健檢 SOP

```bash
# 0. 專案根：Web 依賴與 data/ 已就緒（可選先 python main.py serve）
pip install -r requirements-mcp.txt

# 1. 安裝 Agent 腳本依賴（僅首次）
cd scripts/cursor-agent && npm install

# 2. 設定 API key（勿 commit）
# PowerShell:
$env:CURSOR_API_KEY = "cursor_..."
# bash:
export CURSOR_API_KEY="cursor_..."

# 3. 執行（預設非串流，適合 CI）
npm run ops-check

# 4. 除錯：看每次 tool 狀態
npm run ops-check:verbose
```

**報告應含**：【總覽】正常/需關注/異常；【各項】三工具摘要；【建議】可執行下一步（不改碼）。

腳本 [`scripts/cursor-agent/quant-ops-check.ts`](../scripts/cursor-agent/quant-ops-check.ts) 使用 **local runtime** + **stdio MCP**，直接讀寫本機 `data/` 與 SQLite，適合部署前自檢或排程任務。需 [Cloud Agents API key](https://cursor.com/dashboard/cloud-agents)；金鑰勿入庫。

| 退出碼 | 含義 |
|--------|------|
| `0` | Agent 完成且 `status === finished` |
| `1` | 啟動失敗（如缺 API key、認證錯誤） |
| `2` | Agent 已跑但 run 以 `error` 結束 |
| `75` | 暫時性錯誤（`CursorAgentError.isRetryable`），可重試 |

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
| `sq_ops_check` | 運維 SOP 健檢（同 `python main.py ops check`） |
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
