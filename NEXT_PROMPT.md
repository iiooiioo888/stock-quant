# stock-quant 下一輪優化提示詞

## 項目位置

`E:\Jerry_python\stock-quant\`  
GitHub: [https://github.com/iiooiioo888/stock-quant](https://github.com/iiooiioo888/stock-quant)

## 當前狀態（v7.0 — Pro 工作站 + 異步任務 + 大規模測試）

生產級 A 股量化系統，FastAPI + SQLite + Backtrader。


| 指標     | 數值（2026-05 實測）                   |
| ------ | -------------------------------- |
| API 端點 | 約 170+（`src/api/` 路由裝飾器計數）       |
| pytest | **640** 用例（**59** 個 `test_*.py`） |
| 可回測策略  | 30+（`src/core/strategies/` 模塊註冊） |
| 前端     | **Pro 工作站** `/app`（唯一 Web UI）    |


> 統計：`python -m pytest tests/ --collect-only -q`

### Web 入口


| 入口       | 文件                  | 說明                                      |
| -------- | ------------------- | --------------------------------------- |
| `/`      | `static/home.html`  | 落地頁                                     |
| `/app`   | `static/app.html`   | Pro 工作站：ECharts、Cmd+K、`static/js/pro/`* |
| `/admin` | `static/admin.html` | 管理後台                                    |


Pro 側欄主要頁面（`data-p` → `pg-*`）：

- **核心**：`dashboard` 總覽 · `strategies` 策略庫 · `backtest` 回測 · `compare` 對比 · `tasks` 任務中心
- **持倉**：`assets` 資產庫 · `portfolio` 組合
- **行情**：`watchlist` · `scanner` · `**capitalflow` 資金與板塊**（獨立頁，2026-05 自總覽拆出）
- **進階**：`optimize` · `walkforward` · `heatmap` · `signals` · `data` · `analysis` · `reports` · `scheduler` · `markets` · `crypto` · `connectivity`
- **其他**：`ai` · `factor` · `seasonal` · `regime` · `pricing` · `settings` · `alerts` · `backhistory`

懶載入模塊見 `static/js/pro/module-loader.js`（`capitalflow` → `capitalflow-pro.js`）。

### 核心能力摘要

- 30+ 策略回測 + 止損/止盈/移動止損 + 滑點/T+1/漲跌停
- 參數優化（網格 + Optuna + 多進程/線程池 + 計算預算）
- 組合回測（多策略多標的 + 相關性 + 有效前沿 + 20+ `/api/portfolio/`*）
- Walk-Forward、全自動尋優、參數熱力圖、股票篩選器
- 異步任務（`task_manager` 提交→輪詢→取消/刪除）
- 數據中心（板塊/資金/北向/龍虎榜/基本面/分鐘 K）
- 儀表盤圖表 API：`GET /api/dashboard/market-charts?days=20`（市場資金、北向、板塊熱力）
- 多市場（A 股 + 加密 + 外匯 + 全球指數）、WebSocket 行情、預警 CRUD
- 用戶系統（JWT）、MCP Agent 接入、可選 LLM 問答（Pro `ai` 頁）
- 多幣種資產庫 / 組合結算（`portfolio_currency` · `portfolio_ledger` · `assets` 路由）

### 安全與配置（簡表）

- JWT Secret：`data/.jwt_secret`；管理員密碼：`data/.admin_password`
- 演示模式 `SQ_DEMO_MODE`：GET 白名單開放，POST/DELETE 需 Token
- CORS 默認 localhost；API 限流 120/分/IP；SQLite WAL + busy_timeout
- 配置：`pydantic-settings`（`SQ`_ 前綴）、`config show` / `config validate` CLI

### 目錄結構（精簡）

```
src/
├── config.py
├── api/
│   ├── app.py              # FastAPI 主應用 + 靜態路由 + 限流
│   ├── dispatch.py         # 異步任務 dispatch
│   ├── ws.py               # WebSocket
│   └── routers/            # backtest, tasks, assets, dashboard_market, data_center, …
├── core/
│   ├── strategies/         # 30+ 策略（registry）
│   ├── database/           # schema, migrations, connection
│   ├── backtest.py, optimize.py, portfolio.py, task_manager.py, …
│   └── capital_flow.py, sector.py, data_sources.py, …
├── integrations/
│   ├── mcp/                # MCP Server
│   └── llm/                # 可選 LLM 問答
├── models/
└── cli/

static/
├── app.html, home.html, admin.html
├── css/pro.css             # Pro 設計系統（含隱藏滾動條規則）
├── js/
│   ├── api.js              # 共享 HTTP / 任務輪詢
│   └── pro/
│       ├── app.js, module-loader.js, legacy-bridge.js  # 部分頁內嵌掛載（非獨立前端）
│       ├── ui/dashboard-components.js
│       └── modules/
│           ├── dashboard-pro.js      # 總覽（掛牌 + KPI + 多幣種資產）
│           ├── capitalflow-pro.js    # 資金與板塊（獨立頁）
│           ├── backtest-pro.js, compare-pro.js, tasks-pro.js, …
│           └── assets-pro.js, ai-assistant.js, …
tests/                      # 59 個 test_*.py，640 用例
docs/manual/                # 項目說明書
docs/MCP.md
```

完整索引：[docs/manual/15-文件索引.md](docs/manual/15-文件索引.md)

---

## 已完成（第一輪 ~ 第八輪部分）

### 第一輪 ~ 第六輪

（風險指標、Walk-Forward、熱力圖、篩選器、用戶系統、安全加固、多市場、異步任務、API 路由拆分、164→大規模測試擴充等 — 詳見 Git 歷史與 [README.md](README.md)）

### 第七輪（進行中 / 已落地）


| #   | 項                    | 說明                                                                               |
| --- | -------------------- | -------------------------------------------------------------------------------- |
| 64  | **Capital Flow 獨立頁** | 自 `dashboard` 拆出 `pg-capitalflow`；`capitalflow-pro.js` 懶載入；總覽僅保留掛牌 + KPI + 多幣種資產 |
| —   | Pro 模塊化              | `dashboard-components.js` 組件庫、`module-loader` 按頁載入                               |
| —   | 測試擴充                 | 59 個測試文件、640 用例（含 stability / perf / portfolio_ledger / database_schema 等）       |
| —   | 文檔                   | `docs/manual/`* 說明書、`docs/MCP.md`                                                |


### 第八輪（本輪落地）

| #   | 項 | 說明 |
| --- | --- | --- |
| 65  | 異步任務深化 | 下載類自動重試 + `retry_hint`/`can_retry`；任務中心重試後自動輪詢；AKShare 信號量 + 最小間隔 |
| 66  | 分頁與索引 | `backtest_results(code, strategy)` 複合索引；`/api/alerts` offset+total；`/api/stocks` 遊標分頁 |
| 67  | 數據保留 | `SQ_DATA_RETENTION_YEARS` + 週日排程 + `POST /api/data/retention/purge` |
| 68  | 通知增強 | 異步隊列+重試+SQLite 歷史；ServerChan / Bark |
| 69  | 回測成本/週期 | 佣金下限/過戶費走配置；週線/月線重採樣；`adj=qfq/hfq/none` |
| 70  | 測試補全 | crypto/forex/global/paper/budget/data_sources/download + BL/HRP/CVaR/sector-limit |


---


---

## 生產檢查清單


| 變量                         | 演示 (Render) | 私有生產    |
| -------------------------- | ----------- | ------- |
| `SQ_DEMO_MODE`             | `true`      | `false` |
| `SQ_DEMO_ADMIN_PASSWORD`   | 必設          | 登入後改密   |
| `SQ_CORS_ORIGINS`          | 實際域名        | 實際域名    |
| `SQ_WS_AUTH_REQUIRED`      | 可 false     | `true`  |
| `SQ_RATE_LIMIT_PER_MINUTE` | 120         | 按需      |


---

## 待優化（第八輪後）

> **〔已有〕** = 代碼庫已部分落地，應「深化」而非從零開始。

### 高優

#### 1. 異步化深化 〔本輪已深化〕

- 〔已有〕下載類自動重試、`retry_hint`/`can_retry`、任務中心重試後自動輪詢
- 〔已有〕`download_all_markets` AKShare 信號量 + 最小間隔（`SQ_DOWNLOAD_AKSHARE_*`）
- 可續：非下載類任務自動重試策略、進度 stage 文案細化

#### 2. 數據庫與分頁 API 〔本輪已落地〕

- 〔已有〕`idx_bt_code_strategy`；`/api/alerts` offset+total；`/api/stocks` cursor
- 〔已有〕`SQ_DATA_RETENTION_YEARS` + 週日排程
- 可續：其餘大表改遊標；保留策略按表細分年限

#### 3. 測試補全 〔本輪已補專項〕

- 〔已有〕`test_crypto` / `test_forex` / `test_global_market` / `test_paper_trading` / `test_compute_budget` / `test_data_sources` / `test_download_tasks`
- 〔已有〕`test_portfolio_methods`：BL/HRP/CVaR/sector-limit
- Pro UI：`test_ui_playwright_smoke` 可增 **資金流頁** 載入與圖表 smoke

### 中優

#### 4. 前端 〔Pro 已模塊化〕

- 〔已有〕總覽 / 資金流分頁；隱藏滾動條、`.main` 單滾動容器（見 `.cursor/rules/ui-no-scrollbar.mdc`）
- 〔已有〕回測頁 ECharts PNG 導出；通用 `chart-export.js`
- 待遷：optimize / walkforward / heatmap / 數據中心等仍為 `legacy-mount` 內嵌，逐步改為 `*-pro.js`
- 移動端響應式再加深、K 線全面 Lightweight Charts
- 回測結果並排對比 UI 可再強化

#### 5. 通知增強 〔本輪已落地〕

- 〔已有〕異步隊列 + 失敗重試、`notification_history`、ServerChan/Bark
- 可續：管理後台通知歷史頁、渠道配置 UI

#### 6. 回測增強 〔本輪部分落地〕

- 〔已有〕印花稅/過戶費/佣金下限走配置、前/後/不復權、週線/月線（日線重採樣）
- 待：結果並排對比 UI 深化；hfq 本地持久化

### 低優

#### 7. 監控：`/metrics`、系統資源、錯誤率告警

#### 8. 部署：CI 部署階段、多階段 Docker、可選 PostgreSQL

---

## 技術約束

- Python 3.11+（CI 3.11/3.12），依賴 `requirements.txt`
- SQLite WAL 為主；AKShare 請求間隔 ≥0.5s（建議抖動）
- 前端：**原生 JS**，Chart.js + ECharts + Lightweight Charts，**不引入 npm 構建鏈**
- 新 API 加新端點，**勿破壞既有返回格式**
- 保留 `main.py` CLI；敏感文件勿提交 Git（`.env`、`.jwt_secret`、`.admin_password`）

## 重要提醒

- `config.py` 默認值可改，環境變量覆蓋機制不可動
- 安全相關改動必須有測試
- 不要推送 `.qwen` 到 GitHub
- 修改 Pro 頁面時遵守 UI 滾動條規則（無可見滾動條、避免巢狀 `overflow-y: auto`）

## 給下一個 Agent 的開場白（可直接複製）

```
項目：E:\Jerry_python\stock-quant
請先讀 NEXT_PROMPT.md 與 README.md。
當前：Pro /app 為主前端；資金與板塊在側欄「資金流」(capitalflow)，數據來自 GET /api/dashboard/market-charts。
測試：pytest tests/ -q（約 640 用例）。
約束：不破壞 API 兼容性；前端不引入 npm；遵守 ui-no-scrollbar 規則。
任務：[在此填寫本輪具體目標]
```

