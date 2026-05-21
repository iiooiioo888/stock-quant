# Polymarket 域（MCP 子集）

Polymarket 預測市場數據通過 **全項目 MCP Server** 暴露，不是單獨的 MCP 服務。

- 項目 MCP 文檔：[MCP.md](MCP.md)
- 啟動命令：`python -m src.integrations.mcp.server`（Server 名稱 `stock-quant`）

## Tools（前綴 `polymarket_`）

| Tool | 參數 | 說明 |
|------|------|------|
| `polymarket_list_markets` | `limit`, `tag`, `active` | 市場列表 |
| `polymarket_get_market` | `market_id_or_slug` | 市場詳情 |
| `polymarket_get_orderbook` | `token_id` | Yes/No token 訂單簿 |
| `polymarket_evaluate_alerts` | — | 概率預警評估一輪 |
| `polymarket_strategy_signals` | `limit`, `tag` | 策略信號（偏多/偏空/觀望） |

業務實現：`src/core/polymarket/service.py`（與 `/api/polymarket/*` 共用）。

## REST 對照

| MCP | REST |
|-----|------|
| `polymarket_list_markets` | `GET /api/polymarket/markets` |
| `polymarket_get_market` | `GET /api/polymarket/markets/{id}` |
| `polymarket_get_orderbook` | `GET /api/polymarket/orderbook` |
| `polymarket_evaluate_alerts` | `POST /api/polymarket/alerts/evaluate` |
| `polymarket_strategy_signals` | `GET /api/polymarket/strategy-signals` |

## 概率預警與策略

- 規則表 `polymarket_alert_rules`：`yes_above` / `yes_below` / `prob_change_pct`
- REST：`GET/POST /api/polymarket/alerts/rules`，定時任務 `polymarket_alerts`
- 策略信號：`GET /api/polymarket/strategy-signals`（非 Backtrader，為 advisory）

## 關閉 Polymarket 域

設置 `SQ_POLYMARKET_ENABLED=false` 後，REST 返回 503，MCP tools 返回 `{ "error": "..." }`。
