# UI 按鈕與請求護欄審計

> 2026-05-21 修復後快照。HTML 內約 65 處 `onclick`，多數委派至 `static/js/*.js`。

## 請求層（`static/js/api.js`）

| 機制 | 說明 |
|------|------|
| GET `_inflight` + TTL | 同 path 合併飛行中請求；任務列表 2.5s 快取 |
| `runExclusive(key, fn)` | 長任務防重（如 `download-all`） |
| `debouncedGet(path, ms)` | WS/輪詢用去抖 GET |
| 429 | 返回 `_rateLimited`，輪詢保留上次資料 |

## 後端任務槽（`src/core/task_manager.py`）

- `SQ_TASK_MAX_WORKERS`：同時 **API 異步任務** 數（`_drain_queue` 使用 `_count_in_flight()` + `RLock`，避免雙重計數與派發死鎖）。
- `SQ_MULTI_STRATEGY_WORKERS` 等：單任務 **內部** 並行，由 `compute_budget` 依當前 in-flight 縮限。
- APScheduler（`scheduler.py`）定時任務 **不佔** 任務槽。

## 按 Tab 摘要

| Tab | 主要按鈕 / 載入 | 防重 |
|-----|----------------|------|
| 儀表盤 | `Dashboard.load`、快捷下載 | 下載：`Api.runExclusive('download-all')` + disabled |
| 回測 | `Backtest.run` / `runMulti` | `_running` + `btnLoading` |
| 優化 | `Optimize.run` / `runAuto` | 共用 `_running` |
| 組合 | `Portfolio.run` | `_running` |
| 信號 | `Signals.load*` | `_loadingKey`；WS 刷新 1.8s 去抖 |
| 數據中心 | 子 Tab 自動載入 | `_tabRequestId` 丟棄過期回應 |
| 市場 | Tab 進入 | `Promise.all` 並行載入 |
| 深度分析 | 三鍵分析 | `_analysisRunning` 互斥 |
| 任務 | 刷新 / 批量 | GET silent + 429 保留 `_lastData` |
| 登錄 | `Api.doLogin` | `_loginRunning` + `#loginSubmitBtn` |

## 圖表（穩定策略）

- `charts.js`：`Chart.defaults.animation = false`；LW `resizeTab` 預設不再 `fitContent`。
- `chart-pro.js`：`animation: false`。
- Chart.js CDN 釘版 `4.4.7`。

## 手動驗收

1. `SQ_TASK_MAX_WORKERS=4`，同時提交 4 個不同回測 → 任務 Tab **4/4 running**。
2. 連點全市場下載 → 僅一個任務。
3. 信號 Tab + WS → 無連續 `GET /api/signals/current` 風暴。
4. 儀表盤切 Tab 再回來 → 圖表無長入場動畫閃爍。
