# StockQ Pro 用詞表（Glossary）

鎖定 UI 文案、API 命名與代碼標識，避免混用。

## UI 文案（繁中）

| 場景 | 標準用詞 | 避免 |
|------|----------|------|
| `/` 入口 | 產品介紹 / 產品首頁 | 官網 |
| 文檔連結 | 項目文檔、使用手冊 | 官網 |
| 數據說明 | 數據源說明 | 官網 |
| 回測模塊 | 策略回測 | 回測引擎、Backtest（面向用戶處） |
| 持倉模塊 | 持倉與淨值、資產組合 | 資產庫（組合頁語境下） |
| 工作台首頁 | 主控台（頁腳錨點） | 官網 |

前端鍵值：`static/js/pro/terms.js`（`StockQPro.Terms.t(key)`）。

## 代碼標識

| 概念 | Python / 路由 | 說明 |
|------|---------------|------|
| 回測引擎 | `backtest_engine`、`run_backtest` | 內部模塊名，UI 仍顯示「策略回測」 |
| 回測 API | `/api/backtest` | 保持向後兼容 |
| 流式趨勢 | `/api/portfolio/trend/stream` | NDJSON |
| 流式權益 | `/api/backtest/{task_id}/equity/stream` | NDJSON |

## API 錯誤格式

```json
{"code": 400, "msg": "參數缺失", "trace_id": "a1b2c3d4e5f6"}
```

由 `src/api/errors.py` 全局處理；前端 `Api` 解析 `msg` 與 `trace_id`。

## CSS 變數

主題色使用 `:root` 中 `--ac`、`--bg*`、`--tx`、`--t*`；漲跌語義用 `--quote-up` / `--quote-down`（見 `.cursor/rules/ui-user-prefs.mdc`）。
