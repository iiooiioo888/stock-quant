# 14. MCP 集成

## 14.1 概述

Stock-Quant 內建 **Model Context Protocol (MCP) Server**，允許 AI Agent（如 Cursor、Claude Desktop、Qwen Code）通過標準 MCP 協議直接調用系統功能。

---

## 14.2 安裝

```bash
# 安裝 MCP 依賴
pip install -r requirements-mcp.txt
```

---

## 14.3 啟動 MCP Server

MCP Server 以 stdio 模式運行：

```bash
python -m src.integrations.mcp.server
```

### 在 Cursor 中配置

```json
{
  "mcpServers": {
    "stock-quant": {
      "command": "python",
      "args": ["-m", "src.integrations.mcp.server"],
      "cwd": "/path/to/stock-quant"
    }
  }
}
```

### 在 Claude Desktop 中配置

```json
{
  "mcpServers": {
    "stock-quant": {
      "command": "python",
      "args": ["-m", "src.integrations.mcp.server"],
      "cwd": "/path/to/stock-quant"
    }
  }
}
```

---

## 14.4 可用 Tools

### 核心域 (`sq_*`)

| Tool | 說明 |
|------|------|
| `sq_get_health` | 系統健康狀態 |
| `sq_get_config` | 讀取系統配置 |
| `sq_list_strategies` | 列出所有策略 |
| `sq_run_backtest` | 運行回測 |
| `sq_optimize` | 參數優化 |
| `sq_get_signals` | 獲取實時信號 |
| `sq_get_stock_info` | 股票信息 |
| `sq_download_data` | 下載歷史數據 |
| `sq_run_portfolio` | 組合分析 |
| `sq_get_alerts` | 獲取預警 |
| `sq_list_tasks` | 列出任務 |
| `sq_get_task` | 任務詳情 |


| Tool | 說明 |
|------|------|

---

## 14.5 架構

```
AI Agent (Cursor/Claude/Qwen)
    ↓ stdio (JSON-RPC)
MCP Server (src/integrations/mcp/server.py)
    ↓
Registry (src/integrations/mcp/registry.py)
    ↓
    ↓
Core Modules (src/core/*)
```

### 文件結構

| 文件 | 職責 |
|------|------|
| `src/integrations/mcp/server.py` | stdio 入口，Server 名稱: stock-quant |
| `src/integrations/mcp/protocol.py` | ToolSpec 契約定義 |
| `src/integrations/mcp/registry.py` | 聚合各域 tools |
| `src/integrations/mcp/tools_core.py` | 核心域 sq_* tools |
| `src/integrations/mcp/utils.py` | JSON 輸出格式化 |

---

## 14.6 使用示例

### 通過 MCP 運行回測

Agent 可以直接調用 `sq_run_backtest` tool：

```json
{
  "tool": "sq_run_backtest",
  "arguments": {
    "code": "600519",
    "strategy": "macd",
    "cash": 100000,
    "start": "2020-01-01",
    "end": "2024-12-31"
  }
}
```

### 通過 MCP 查詢信號

```json
{
  "tool": "sq_get_signals",
  "arguments": {
    "code": "600519"
  }
}
```

---

## 14.7 文檔

詳細的 MCP 文檔位於：
- `docs/MCP.md` — 全項目 MCP Server 說明
