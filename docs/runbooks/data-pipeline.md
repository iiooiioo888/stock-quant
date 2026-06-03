# 數據管線 Runbook

> **版本**: v1.1 | **最後更新**: 2026-06-03  
> 適用：`market_fetch`、`data_pipeline`、`local_kline`、`fundamental` 及相關 API。  
> 入口與決策樹：[runbooks/README.md](README.md)

## 處置流程（建議順序）

| 階段 | 動作 | 通過標準 |
|------|------|----------|
| 觀測 | `sq_health` 或 `GET /api/health/detailed` | 無 5xx；`pipeline_metrics` 可讀 |
| 定位 | `sq_pipeline_metrics` | 對照下方「關鍵欄位」與症狀表 |
| 索引 | `sq_db_index_audit`（先 `apply_missing=false`） | `missing` 為空或已排程修復 |
| 修復 | 依「常見症狀」小節 | 症狀消失且 `pending_deferred=0` |
| 驗證 | 重跑 `npm run ops-check` 或手動拉一筆 K 線 | 詳情頁/掛牌響應正常 |

## 架構速覽

| 階段 | 入口 | 說明 |
|------|------|------|
| 行情 K 線 | `market_fetch.fetch_history_df` | **目錄 IB → TV** → 本地庫 → Yahoo → 東財 → global；成功後 `persist_kline_df` |
| IB 行情 | `ib_data` + `market_catalog` | 需 `SQ_IB_ENABLED=true`、`pip install -r requirements-ib.txt`、本地 TWS/Gateway |
| 快取 | `data_pipeline.defer_data_cache_clear` | 單筆寫庫只標記；批量任務 `flush_deferred_data_cache_clear` |
| 財報 | `data_pipeline.resolve_financials` / `fundamental.get_fundamentals` | DB 未過期命中 → akshare 在線 → 兜底 universe |

## 觀測指標

### MCP

- `sq_pipeline_metrics` — 進程內計數器快照
- `sq_health` — 含 `pipeline_metrics` 與 `index_audit` 摘要
- `sq_db_index_audit` — 索引健檢；`apply_missing=true` 可自動補建

### REST

- `GET /api/health/detailed` — 含 `pipeline_metrics`、`index_audit`
- `GET /metrics` — Prometheus（需 `prometheus-client`）

### 關鍵欄位

```json
{
  "cache": {
    "defer_total": 120,
    "flush_total": 3,
    "pending_deferred": 0
  },
  "kline": {
    "persist_rows_total": 45000,
    "fetch_by_source": { "local_db": 800, "yahoo": 12, "eastmoney": 5 }
  },
  "financials": {
    "get_fundamentals": { "db_hit": 200, "online_fetch": 15 },
    "resolve_financials": { "db_fresh": 180, "fetched": 10 }
  }
}
```

## 常見症狀與處置

### 1. 掛牌/批量頁面慢、日誌刷屏「數據緩存已清除」

**原因**：批量 K 線寫入時每條都 `clear_data_cache()`。

**檢查**：`pending_deferred` 是否在批量結束後歸零；`flush_total` 是否隨批量任務增加。

**處置**：

- 確認 `indices` 等批量路由在 `finally` 調用 `flush_deferred_data_cache_clear()`
- 禁止在 `persist_kline_df` 內直接 `clear_data_cache()`

### 2. 詳情頁財報為空

**檢查**：`sq_pipeline_metrics` → `financials.resolve_financials` 是否多為 `empty`。

**處置**：

- 調用 `get_fundamentals(code, max_age_days=7)` 觸發在線補齊
- 查 `sq_data_sources` 確認 akshare 相關源未熔斷

### 3. 查詢變慢

**檢查**：`sq_db_index_audit` → `missing` 非空。

**處置**：

```text
MCP: sq_db_index_audit { "apply_missing": true }
```

或重啟應用觸發 `migrations` 中的 `INDEX_DDL`。

### 4. MCP 調用失敗

錯誤統一格式：

```json
{
  "ok": false,
  "error_code": "VALIDATION_ERROR",
  "error": "請提供 code",
  "tool": "sq_stock_overview"
}
```

| error_code | 含義 |
|------------|------|
| `VALIDATION_ERROR` | 參數缺失或非法 |
| `NOT_FOUND` | 資源不存在（如 task_id） |
| `INTERNAL_ERROR` | 未預期異常 |
| `UNKNOWN_TOOL` | tool 名稱錯誤 |

## 日誌

- 批量清快取：`clear_data_cache(quiet=True, reason=...)`
- 單標的 ensure：`ensure_daily_kline:{code}`（允許即時清快取）

## 相關規則

- `.cursor/rules/data-fetch-pipeline.mdc`
- `.cursor/rules/sqlite-and-caching.mdc`
- `.cursor/rules/mcp-tooling.mdc`
