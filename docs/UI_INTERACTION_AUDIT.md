# 全面用戶交互審計報告

> 生成時間：2026-06-04  
> 審計範圍：`app.html`（1179 行）、`static/js/pro/**/*.js`（25+ 模組）、`static/js/*.js`（15+ 模組）、`src/api/routers/*.py`（30+ 路由）

---

## 一、架構概覽

系統存在 **雙軌 UI 架構**：

| 層 | 模式 | 綁定方式 | Toast | 確認對話 |
|----|------|---------|-------|---------|
| Legacy (`static/js/*.js`) | `App.loadTab()` | 內聯 `onclick` | `Utils.toast()` | `window.confirm()` |
| Pro (`static/js/pro/**/*.js`) | `App.nav()` | `addEventListener` | `StockQPro.App.toast()` | `window.confirm()` |

- **Legacy 頁面**（via `legacy-bridge.js`）：portfolio、optimize、walkforward、heatmap、signals、data、analysis、reports、scheduler、markets、crypto、connectivity、alerts
- **Pro 原生頁面**：dashboard、backtest、compare、tasks、watchlist、scanner、strategies、backhistory、assets、settings、ai、pricing

---

## 二、逐頁交互清單

### 2.1 頂欄（Topbar）

| 元素 | ID/選擇器 | 交互 | 狀態 |
|------|----------|------|------|
| Logo | `.logo[data-nav]` | 點擊 → `nav('dashboard')` | ✅ |
| 產品介紹 | `a[href="/"]` | 導航 | ✅ |
| 使用手冊 | `a[href="/manual"]` | 導航 | ✅ |
| 管理後台 | `a[href="/admin"]` | 導航 | ✅ |
| 行情跑馬燈 | `#topbar-ticker-strip` | 自動滾動，點擊卡片 → 資產詳情 | ✅ |
| 命令面板按鈕 | `#cmd-open-btn` | 點擊/Ctrl+K → 命令面板 | ✅ |
| 連線狀態 | `#conn-status` | 唯讀指示 | ✅ |
| 運維狀態 | `#ops-status-pill` | 點擊 → 設定頁運維區 | ✅ |
| 資產配置 | `#alloc-rail-toggle` | 切換右側配置欄 | ✅ |
| 任務通知 | `#notif-btn` | 點擊 → 任務中心 | ✅ |
| 方案標籤 | `#plan-badge` | 點擊 → 定價頁 | ✅ |
| 登錄/登出 | `#auth-pill` | 點擊 → 登入彈窗/登出 | ✅ |

### 2.2 側邊欄（Sidebar）

| 分組 | 頁面 | 數據屬性 | 快捷鍵 | 狀態 |
|------|------|---------|--------|------|
| 工作台 | 總覽 | `data-p="dashboard"` | `1` | ✅ |
| 工作台 | 任務中心 | `data-p="tasks"` | `T` | ✅ |
| 工作台 | 自選股 | `data-p="watchlist"` | `5` | ✅ |
| 工作台 | 選股器 | `data-p="scanner"` | `6` | ✅ |
| 工作台 | 預警 | `data-p="alerts"` | `7` | ✅ |
| 回測與策略 | 策略庫 | `data-p="strategies"` | `S` | ✅ |
| 回測與策略 | 策略回測 | `data-p="backtest"` | `2` | ✅ |
| 回測與策略 | 對比 | `data-p="compare"` | `3` | ✅ |
| 回測與策略 | 持倉與淨值 | `data-p="portfolio"` | `4` | ✅ |
| 回測與策略 | 回測歷史 | `data-p="backhistory"` | — | ✅ |
| 回測與策略 | 參數優化 | `data-p="optimize"` | — | ✅ |
| 回測與策略 | 滾動驗證 | `data-p="walkforward"` | — | ✅ |
| 回測與策略 | 熱力圖 | `data-p="heatmap"` | — | ✅ |
| 回測與策略 | 策略報告 | `data-p="reports"` | — | ✅ |
| 數據與市場 | 資產庫 | `data-p="assets"` | — | ✅ |
| 數據與市場 | 資金流 | `data-p="capitalflow"` | — | ✅ |
| 數據與市場 | 數據中心 | `data-p="data"` | — | ✅ |
| 數據與市場 | 深度分析 | `data-p="analysis"` | — | ✅ |
| 數據與市場 | 信號 | `data-p="signals"` | — | ✅ |
| 數據與市場 | 市場 | `data-p="markets"` | — | ✅ |
| 數據與市場 | 加密 | `data-p="crypto"` | — | ✅ |
| 數據與市場 | 定時 | `data-p="scheduler"` | — | ✅ |
| 數據與市場 | 數據源 | `data-p="connectivity"` | — | ✅ |
| 實驗·AI | AI | `data-p="ai"` | `A` | ✅ |
| 實驗·AI | 定價 | `data-p="pricing"` | `0` | ✅ |
| 實驗·AI | 因子 | `data-p="factor"` | — | ⏳ 即將推出 |
| 實驗·AI | 季節性 | `data-p="seasonal"` | — | ⏳ 即將推出 |
| 實驗·AI | 市場狀態 | `data-p="regime"` | — | ⏳ 即將推出 |
| 實驗·AI | 風控 | `data-p="risk"` | `8` | ⏳ 即將推出 |
| 實驗·AI | 日誌 | `data-p="journal"` | `9` | ⏳ 即將推出 |
| 系統 | 設定 | `data-p="settings"` | — | ✅ |

### 2.3 命令面板（Ctrl+K）

- **輸入**：`#cmd-in`，即時過濾
- **結果列表**：`#cmd-list`，支持頁面導航、策略搜索、代碼快速回測、運維健檢
- **關閉**：ESC 或點擊遮罩
- ✅ 功能完整

### 2.4 策略庫（Strategies）

| 元素 | 交互 | 狀態 |
|------|------|------|
| 搜索框 `#lib-search` | `input` → 即時過濾 | ✅ |
| 方案篩選 `#lib-tier` | `change` → 重新渲染 | ✅ |
| 狀態篩選 `#lib-status` | `change` → 重新渲染 | ✅ |
| 檢視模式 `#lib-view` | `change` → 網格/列表切換 | ✅ |
| 分類標籤 `#cat-pills` | 點擊切換分類 | ✅ |
| 策略卡片 | 點擊 → 策略詳情彈窗 | ✅ |
| 詳情彈窗「用於回測」 | `#sd-use` → 跳轉回測頁 | ✅ |
| 點讚按鈕 | `.strat-like-btn` → API 呼叫 | ✅ |

### 2.5 策略回測（Backtest）

| 元素 | ID | 交互 | 防重 | 狀態 |
|------|----|------|------|------|
| 代碼輸入 | `#bt-code-input` | `input` → 6位數字即時搜索建議 | ✅ | ✅ |
| 標的選擇 Tab | `[data-bt-pick]` | 代碼/自選/資產庫/熱門/搜索 | — | ✅ |
| 策略選擇 | `#bt-sel` | 點擊 → 策略庫 | — | ✅ |
| 週期 | `#bt-timeframe` | 日/週/60分鐘 | — | ✅ |
| 初始資金 | `#bt-capital` | number | — | ✅ |
| 滑點 | `#bt-slip` | number | — | ✅ |
| 佣金 | `#bt-comm` | number | — | ✅ |
| 止損 | `#bt-stop-loss` | number, 可選 | — | ✅ |
| 熔斷回撤 | `#bt-circuit-dd` | number, 可選 | — | ✅ |
| 倉位上限 | `#bt-max-pos` | number, 可選 | — | ✅ |
| T+1 | `#bt-t1` | checkbox | — | ✅ |
| 漲跌停 | `#bt-limit` | checkbox | — | ✅ |
| 背景任務 | `#bt-bg` | checkbox | — | ✅ |
| 強制重算 | `#bt-force` | checkbox | — | ✅ |
| 執行回測 | `#bt-run-btn` | 點擊 → API | `running` + `disabled` | ✅ |
| 參數優化 | `#bt-opt-btn` | 跳轉優化頁 | — | ✅ |
| 任務佇列 | `#bt-tasks-btn` | 跳轉任務中心 | — | ✅ |
| 複製參數 | `#bt-copy-params-btn` | clipboard | — | ✅ |
| 導出 JSON | `#bt-export-btn` | 下載 blob | — | ✅ |
| 導出 CSV | `#bt-export-csv-btn` | 下載 blob | — | ✅ |
| 導出 PNG | `#bt-export-png-btn` | echarts.getDataURL | — | ✅ |
| 清空日誌 | `#bt-clear-log` | 清除 log 區域 | — | ✅ |
| 保存 | `#bt-save-btn` | 自動保存提示 | — | ✅ |
| 圖表 Tab | `[data-bt-tab]` | 淨值/回撤/K線切換 | — | ✅ |
| 成交明細 | `<details>` | 展開/收合 | — | ✅ |

### 2.6 多股/多策略對比（Compare）

| 元素 | ID | 交互 | 狀態 |
|------|----|------|------|
| 模式切換 | `[data-cmp-mode]` | 多策略/多股票 | ✅ |
| Chip 列表 | `#cmp-chips` | 顯示/移除/雙擊設基準 | ✅ |
| 代碼輸入 | `#cmp-code-input` | 輸入+加入 | ✅ |
| 建議列表 | `#cmp-code-suggest` | 即時搜索 | ✅ |
| 選股 Tab | `[data-cmp-pick]` | 熱門/自選/資產庫/搜尋 | ✅ |
| 策略指標 | `#cmp-metric` | 8 種指標 | ✅ |
| 圖表類型 | `#cmp-chart-type` | 橫向排行/散點/淨值 Top5 | ✅ |
| 排序 | `#cmp-sort` | 高→低/低→高 | ✅ |
| 顯示數量 | `#cmp-topn` | Top10/20/全部 | ✅ |
| 執行對比 | `#cmp-run` | API + `disabled` 防重 | ✅ |
| 刷新 | `#cmp-refresh` | 重跑 | ✅ |
| 分享 | `#cmp-share-link` | 複製 URL | ✅ |
| PNG/CSV | `#cmp-export-png/csv` | 導出 | ✅ |
| 自訂組合 | `#cmp-preset-save` | 儲存到 localStorage | ✅ |
| 沿用回測 | `#cmp-use-bt` | 從回測頁帶入代碼 | ✅ |
| 全選自選 | `#cmp-fill-watch` | 批量加入 | ✅ |
| 相關性熱力圖 | `#cmp-corr-heat` | 自動渲染 | ✅ |

### 2.7 任務中心（Tasks）

| 元素 | ID | 交互 | 狀態 |
|------|----|------|------|
| 自動刷新 | `#tk-auto-refresh` | checkbox | ✅ |
| 刷新 | `#tk-refresh` | 手動刷新 | ✅ |
| 導出 | `#tk-export` | 匯出任務數據 | ✅ |
| 取消排隊 | `#tk-cancel-pending` | `confirm()` → API | ✅ |
| 清空歷史 | `#tk-clear-done` | `confirm()` → API | ✅ |
| 清理超時 | `#tk-cleanup` | API | ✅ |
| 快速篩選 | `[data-tk-status/filter]` | 全部/運行中/等待中/已完成/失敗/今日/有結果 | ✅ |
| 搜索 | `#taskSearch` | debounce | ✅ |
| 類型篩選 | `#taskTypeFilter` | dropdown | ✅ |
| 狀態篩選 | `#taskStatusFilter` | dropdown | ✅ |
| 批量選擇 | `.tk-card-chk` | checkbox | ✅ |
| 批量取消 | `#taskBatchCancelBtn` | `confirm()` → API | ✅ |
| 批量刪除 | `#taskBatchDeleteBtn` | `confirm()` → API | ✅ |
| 任務詳情側欄 | `#tkDetailPanel` | 點擊卡片展開 | ✅ |
| 任務操作 | `[data-action]` | 取消/重試/刪除/前往/結果 | ✅ |
| WebSocket 推送 | `task_*` 消息 | 即時更新任務狀態 | ✅ |

### 2.8 自選股（Watchlist）

| 元素 | ID | 交互 | 狀態 |
|------|----|------|------|
| 代碼輸入 | `#wl-code-input` | 6位代碼 | ✅ |
| 備註名稱 | `#wl-name-input` | 可選 | ✅ |
| 自動規則 | `#wl-auto-rule` | checkbox | ✅ |
| 添加 | `#wl-add` | API | ✅ |
| 刷新 | `#wl-reload` | API | ✅ |
| 表格行 | `.wl-row` | 點擊 → 圖表 | ✅ |
| 回測按鈕 | `[data-bt]` | 跳轉回測 | ✅ |
| 詳情按鈕 | `[data-detail]` | 資產詳情 | ✅ |
| 移除按鈕 | `[data-rm]` | API | ✅ |
| 圖表 | `#wl-ch` | echarts | ✅ |

### 2.9 選股器（Scanner）

| 元素 | ID | 交互 | 防重 | 狀態 |
|------|----|------|------|------|
| 市場 | `#scan-market` | 全市場/A股 | — | ✅ |
| 預設條件 | `#scan-preset` | 4 種策略 | — | ✅ |
| 開始掃描 | `#scan-run` | API | `disabled` | ✅ |
| 導出 CSV | `#scan-export` | 下載 | — | ✅ |
| 結果操作 | `[data-bt]/[data-add]` | 回測/加入監控 | — | ✅ |

### 2.10 回測歷史（Backhistory）

| 元素 | ID | 交互 | 狀態 |
|------|----|------|------|
| 代碼篩選 | `#bh-filter-code` | Enter 觸發 | ✅ |
| 策略篩選 | `#bh-filter-strategy` | Enter 觸發 | ✅ |
| 條數 | `#bh-limit` | number | ✅ |
| 刷新 | `#bh-reload` | API | ✅ |
| 對比選中 | `#bh-compare-btn` | 最多 3 筆 | ✅ |
| 導出 CSV | `#bh-export-csv-btn` | 下載 | ✅ |
| 清除選擇 | `#bh-clear-sel` | 重置 | ✅ |
| Checkbox | `.bh-chk` | 選擇記錄 | ✅ |
| 載入回測 | `[data-load]` | 跳轉回測頁 | ✅ |
| 導出單筆 | `[data-dl]` | 下載 JSON | ✅ |

### 2.11 資產庫（Assets）

| 元素 | ID | 交互 | 狀態 |
|------|----|------|------|
| 搜索 | `#assets-search` | 即時過濾 | ✅ |
| 主題包標籤 | `#assets-group-pills` | 點擊篩選 | ✅ |
| 資產卡片 | `#assets-grid` | 點擊 → 詳情 | ✅ |
| 返回列表 | `[data-assets-back]` | 切回列表 | ✅ |
| 資產詳情 | `#assets-detail-root` | 動態渲染 | ✅ |
| ＋配置 | 資產卡片 | 加入右側配置欄 | ✅ |

### 2.12 資金流（Capital Flow）

| 元素 | ID | 交互 | 狀態 |
|------|----|------|------|
| 天數標籤 | `#cf-days-badge` | 顯示當前天數 | ✅ |
| 刷新 | `#cf-refresh-btn` | 重新載入 | ✅ |
| 圖表 | `#cf-charts-grid` | echarts | ✅ |
| 熱力圖 | `#cf-heatmap-row` | 板塊熱力圖 | ✅ |

### 2.13 AI 智能問答

| 元素 | ID | 交互 | 狀態 |
|------|----|------|------|
| 狀態標籤 | `#ai-status-badge` | 顯示 LLM 可用性 | ✅ |
| 輸入框 | `#ai-input` | textarea, Enter 發送 | ✅ |
| 流式回答 | `#ai-stream` | checkbox | ✅ |
| 清空對話 | `#ai-clear-btn` | 清除聊天記錄 | ✅ |
| 發送 | `#ai-send-btn` | API + `disabled` 防重 | ✅ |
| 可用工具 | `#ai-tools-detail` | 展開列表 | ✅ |

### 2.14 設定（Settings）

| 元素 | ID | 交互 | 狀態 |
|------|----|------|------|
| 配色方案 | `input[name="set-quote-scheme"]` | radio → 即時預覽 | ✅ |
| 圖表天數 | `#set-chart-days` | number | ✅ |
| 行情輪詢 | `#set-poll-sec` | number | ✅ |
| 緊湊頂欄 | `#set-compact-topbar` | checkbox | ✅ |
| 編輯頂欄指數 | `#set-topbar-edit` | 彈窗編輯器 | ✅ |
| 訂閱方案 | `#set-billing-go` | 跳轉定價 | ✅ |
| 預設佣金 | `#set-commission` | number | ✅ |
| 最大並行 | `#set-max-parallel` | number | ✅ |
| LLM Key | `#set-llm-key` | password | ✅ |
| LLM Base | `#set-llm-base` | text | ✅ |
| LLM Model | `#set-llm-model` | text | ✅ |
| 僅本機 | `#set-llm-local-only` | checkbox | ✅ |
| 保存 LLM | `#set-llm-save` | API/localStorage | ✅ |
| 清除 Key | `#set-llm-clear` | 刪除 | ✅ |
| 刷新 SOP | `#set-ops-refresh` | API | ✅ |
| 複製報告 | `#set-ops-copy` | clipboard | ✅ |
| 下載 JSON | `#set-ops-download` | blob | ✅ |
| 重新檢測 | `#set-src-refresh` | API | ✅ |
| 連線檢查 | `#set-src-connectivity` | 跳轉 | ✅ |
| 保存偏好 | `#set-save-btn` | API/localStorage | ✅ |
| 重新載入 | `#set-reload-btn` | 重新讀取 | ✅ |
| 清除緩存 | `#set-clear-cache` | 刪除緩存 | ✅ |
| 恢復預設 | `#set-reset-prefs` | 重置 | ✅ |

### 2.15 右側資產配置欄（Allocation Rail）

| 元素 | ID | 交互 | 狀態 |
|------|----|------|------|
| 關閉 | `#alloc-rail-close` | 收起側欄 | ✅ |
| 遮罩 | `#alloc-rail-backdrop` | 點擊關閉 | ✅ |
| 權重模式 | `[data-alloc-weight-mode]` | 市值/股數 | ✅ |
| 表單 | `#alloc-rail-form` | submit → 加入持倉 | ✅ |
| 持倉列表 | `#alloc-rail-list` | 顯示/編輯/刪除 | ✅ |
| 組合策略 | `#alloc-pf-strategy` | 5 種策略 | ✅ |
| 回測首檔 | `#alloc-act-backtest` | 跳轉回測 | ✅ |
| 多股對比 | `#alloc-act-compare` | 跳轉對比 | ✅ |
| 組合回測 | `#alloc-act-portfolio` | 跳轉組合 | ✅ |
| 同步自選 | `#alloc-act-watchlist` | API | ✅ |

### 2.16 定價（Pricing）

| 元素 | ID | 交互 | 狀態 |
|------|----|------|------|
| 升級按鈕 | `[data-pricing-upgrade]` | API | ✅ |
| 聯繫按鈕 | `[data-pricing-contact]` | toast 提示 | ✅ |
| 降級按鈕 | `[data-pricing-downgrade]` | toast 提示 | ✅ |

### 2.17 鍵盤快捷鍵

| 按鍵 | 動作 | 狀態 |
|------|------|------|
| `Ctrl+K` | 命令面板 | ✅ |
| `?` | 快捷鍵說明 | ✅ |
| `O` | 運維健檢 + 設定 | ✅ |
| `T` | 任務中心 | ✅ |
| `1–9` | 切換頁面 | ✅ |
| `H` | 產品介紹頁 | ✅ |
| `S` | 策略庫 | ✅ |
| `R` | 刷新任務（任務頁內） | ✅ |
| `Esc` | 關閉彈窗/命令面板 | ✅ |

---

## 三、發現的問題

### 🔴 嚴重（Bug）

#### 3.1 `backtest-pro.js` — `unload()` 中 `const` 變數重賦值

```javascript
// 第 5 行：const charts = {};
// 第 868-870 行：
function unload() {
  try { window.StockQPro?.ECharts?.disposePage?.('backtest'); } catch (_) {}
  charts = {};  // ❌ TypeError: Assignment to constant variable.
}
```

**影響**：切換頁面再切回時，echarts 實例無法正確清理，可能導致記憶體洩漏。

**修復**：改為 `for (const k in charts) delete charts[k];` 或改 `let`。

#### 3.2 `compare-pro.js` — `unload()` 中同樣的 `const` 問題

```javascript
// 第 31 行：let chart = null; (這個是 let，OK)
// 但 corrChart 也是 let，OK
```

✅ 此處正確使用 `let`。

#### 3.3 `backtest-pro.js` — 成交明細表頭不匹配

```javascript
// 第 491-496 行：動態修改 thead th 文字
const ths = theadRow.querySelectorAll('th');
if (ths[0]) ths[0].textContent = intraday ? '買入時間' : '買入日';
if (ths[2]) ths[2].textContent = intraday ? '賣出時間' : '賣出日';
if (ths[4]) ths[4].textContent = intraday ? '持倉 K 線' : '持倉天';
```

但 HTML 中定義的 thead 是 `日期/方向/價格/數量/盈虧`（5 列），而 renderTrades 生成的是 `買入日/買入價/賣出日/賣出價/持倉天/盈虧/收益%`（7 列）。

**影響**：表頭與數據列不對應，`ths[2]` 改的是「價格」列的標題而非「賣出日」。

### 🟡 中等（UX 問題）

#### 3.4 兩套 Toast 系統並存

- Legacy：`Utils.toast(msg, 3000, 'error')` — 參數 `(msg, duration, type)`
- Pro：`StockQPro.App.toast(msg, 'er')` — 參數 `(msg, type)`

**影響**：如果 `Utils` 和 `StockQPro` 同時存在，可能出現重疊的 toast。

#### 3.5 內聯 `onclick` 未統一遷移

以下頁面仍有大量內聯 `onclick`：

| 文件 | 約數量 |
|------|-------|
| `static/js/app.js`（Legacy 主文件） | 20+ |
| `static/js/tasks.js` | 15+ |
| `static/js/dashboard.js` | 10+ |
| `static/js/data.js` | 5+ |
| `static/js/screener.js` | 3+ |
| `static/js/scheduler.js` | 3+ |

**影響**：
- CSP（Content-Security-Policy）不兼容內聯腳本時無法運行
- 鍵盤用戶無法通過 Enter 觸發（部分按鈕除外）
- 難以做事件委託和批量清理

#### 3.6 原生 `confirm()` 對話框

18 處使用 `window.confirm()`，與暗色主題 UI 不一致：

| 位置 | 操作 |
|------|------|
| `tasks.js` / `tasks-pro.js` | 取消任務、清空歷史、批量操作 |
| `app.js` | 全市場下載確認 |
| `dashboard.js` | 刪除預警規則 |
| `screener.js` | 加入監控 |
| `scheduler.js` | 禁用全部 |
| `admin-app.js` | 刪除用戶/邀請碼/策略 |
| `alerts-pro.js` | 刪除預警 |
| `api.js` | 配額超限跳轉 |

**建議**：統一使用自訂 Modal 組件（已有 `UI.modalOpen`）。

#### 3.7 策略庫「我的點讚」篩選

```html
<option value="liked">我的點讚</option>
```

選中後需要用戶已登錄且後端返回 `liked` 狀態的策略。如果未登錄，應自動跳過或提示。

#### 3.8 對比頁 — 多策略模式下 chip 限制為 1

```javascript
const max = state.mode === 'strategies' ? 1 : MAX_STOCKS;
```

切換到多策略模式時自動截斷到 1 檔，但用戶可能不理解為何其他 chip 被移除。

#### 3.9 鍵盤快捷鍵衝突

`R` 鍵在任務中心內刷新任務，但在其他頁面（如 AI 輸入框聚焦時）應被忽略。目前已有 `INPUT/TEXTAREA/SELECT` 排除，但：

```javascript
if (e.key === 'r' || e.key === 'R') {
  if (this.current === 'tasks') window.StockQPro?.Tasks?.refresh?.();
}
```

✅ 已正確限定在 tasks 頁面內。

#### 3.10 回測頁 — 選擇策略後未同步顯示

點擊策略庫的「用於回測」後，會調用：

```javascript
// strategy-catalog.js
useBtn.onclick = () => {
  window.StockQPro?.App?.closeModal?.('m-strat');
  // 設定 selectedStrategy ...
};
```

但 `backtest-pro.js` 的 `bt-sel-name` 和 `bt-sel-desc` 需要依賴 `window.StockQPro.selectedStrategy` 的更新，且 `init()` 中的策略同步可能延遲。

#### 3.11 自選股 — 搜索輸入框缺少 Enter 提交

```html
<input type="text" id="wl-code-input" class="inp" placeholder="代碼" maxlength="6" />
```

只有「添加」按鈕觸發添加，輸入框無 `keydown` 監聽 Enter 鍵。

#### 3.12 選股器 — 掃描結果無分頁

掃描結果直接渲染全部，如果全市場結果數百條，DOM 節點過多可能影響性能。

#### 3.13 頂欄跑馬燈 — 無暫停交互

```html
<div class="ticker-strip" id="topbar-ticker-strip">
  <div class="ticker-strip-inner"></div>
</div>
```

CSS 動畫持續滾動，鼠標懸停時應暫停以便用戶閱讀，但未見 `animation-play-state` 的 hover 控制。

#### 3.14 命令面板 — 策略搜索不支持拼音/簡拼

策略搜索僅匹配中文名稱和英文 key，不支持拼音首字母（如 `smlx` → 雙均線）。

#### 3.15 回測歷史 — 篩選條件無持久化

`#bh-filter-code` 和 `#bh-filter-strategy` 的值在頁面切換後丟失。

#### 3.16 對比頁 — 「沿用回測標的」邏輯

```javascript
$id('cmp-use-bt')?.addEventListener('click', () => {
  const sym = window.StockQPro?.backtestSymbol;
  // ...
});
```

如果回測頁尚未選擇標的，此按鈕無任何反饋（無 toast 提示）。

### 🟢 低（改進建議）

#### 3.17 無 loading skeleton

大部分頁面在載入時顯示「載入中…」文字，而非 skeleton 屏。Pro 的 `_setPageLoading` 已有基礎框架，但子頁面未充分利用。

#### 3.18 表格排序無視覺提示

回測歷史表格的 `th` 列頭無排序指示器（↑↓箭頭），用戶不知道是否支持排序。

#### 3.19 分頁缺失

| 頁面 | 問題 |
|------|------|
| 策略庫 | 策略 130+ 全量渲染，虛擬滾動或分頁可改善 |
| 任務列表 | 有篩選但無分頁，大量任務時 DOM 過多 |
| 選股器結果 | 無分頁 |

#### 3.20 狀態欄快捷鍵提示不完整

```html
<span class="sbi"><kbd>T</kbd> 任務</span>
<span class="sbi"><kbd>?</kbd> 命令面板</span>
```

缺少 `S` 策略庫、`O` 運維、數字鍵等說明。

#### 3.21 定價頁 — 升級流程

點擊升級後調用 `upgradePro()`，如果用戶未登錄應先引導登錄，而非直接報錯。

#### 3.22 「即將推出」頁面的交互

因子、季節性、市場狀態、風控、日誌 5 個頁面只有占位文字：

```html
<p class="placeholder-msg">因子分析功能規劃中，將於後續版本提供。</p>
```

側邊欄的 `.sb--planned` 樣式使其看起來可點擊，建議加 `disabled` 或移至獨立「開發中」分組。

---

## 四、無障礙（Accessibility）摘要

| 項目 | 狀態 | 說明 |
|------|------|------|
| `aria-label` | ✅ 大部分 | 側邊欄、頂欄按鈕、表單元素 |
| `role="button"` | ✅ | auth-pill、策略選擇卡 |
| `role="dialog"` | ✅ | 命令面板、彈窗 |
| `aria-hidden` | ✅ | 隱藏的面板和圖標 |
| `aria-live="polite"` | ✅ | toast、任務列表 |
| 鍵盤導航 | ⚠️ 部分 | Tab 順序基本正確，但側邊欄按鈕使用 `<button>` 而非 `<a>`，Tab 順序可能不直覺 |
| 顏色對比度 | ⚠️ 未驗證 | 暗色主題下淺色文字對比度需工具驗證 |
| 內聯 onclick 鍵盤 | ❌ | 內聯 `onclick` 在 `<div>` 上無法通過 Enter/Space 觸發 |

---

## 五、優先修復建議

### P0（影響功能）

1. **修復 `backtest-pro.js` 的 `charts = {}` const 重賦值** — 會拋 TypeError
2. **修復成交明細表頭列數不匹配** — 表頭 5 列 vs 數據 7 列

### P1（影響體驗）

3. 統一 Toast 系統，避免雙重顯示
4. 自選股輸入框支持 Enter 鍵提交
5. 「沿用回測標的」無標的時的 toast 提示
6. 跑馬燈 hover 暫停
7. 確認對話框統一為自訂 Modal

### P2（代碼品質）

8. 逐步遷移內聯 `onclick` 到 `addEventListener`
9. 表格添加排序指示器
10. 大列表考慮虛擬滾動或分頁
11. 狀態欄快捷鍵提示補全
12. 「即將推出」頁面交互優化（明確標記不可用）