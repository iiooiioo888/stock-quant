# stock-quant 下一輪優化提示詞

## 項目位置
`E:\Jerry_python\stock-quant\`
GitHub: https://github.com/iiooiioo888/stock-quant

## 當前狀態（v6.0 — 多市場 + 異步任務 + 全面測試後）

生產級 A 股量化系統，FastAPI + SQLite + Backtrader，151 個 API 端點，82 個測試全通過。

**核心功能（30+ 個模塊）：**
- 19 種策略回測 + 止損/止盈/移動止損 + 滑點/T+1/漲跌停
- 參數優化（網格搜索 + Optuna + 多進程並行 + 計算預算分配）
- 組合回測（多策略多股票 + 相關性矩陣 + 有效前沿）
- 11+ 種組合方法（等權/風險平價/MVO/波動率目標/最大分散化/反相關/狀態切換/動態權重/Kelly/衰退檢測/信號仲裁）
- Walk-Forward 滾動窗口分析（過擬合檢測）
- 全自動參數尋優（跨股票共識推薦）
- 策略熱力圖（參數敏感性 Canvas 渲染）
- 股票篩選器（MA多頭/量比/近高點/漲幅/站上均線）
- 滬深300基準對比（Alpha/Beta/信息比率）
- 風險指標全套（VaR/CVaR/Sortino/Calmar/月勝率/盈虧比）
- 風險管線（risk_pipeline 多階段風控）
- 回測結果持久化 + 歷史查詢 + CSV/JSON 導出
- 異步任務管理（task_manager 提交→輪詢→結果，支持取消/刪除）
- 定時任務（APScheduler）+ 每日策略報告 + 增強報告
- 多渠道通知（企微/釘釘/Telegram + 模板 + 節流）
- 增量數據下載（並行下載 + 下載任務管理 + 進度追蹤）
- LRU 數據緩存 + API 緩存 + 結果緩存
- WebSocket 實時行情 + 預警規則 CRUD + 自動預警規則
- 實時信號引擎（當前/歷史/強度評分）
- 數據中心（板塊/資金流向/龍虎榜/基本面/分鐘K線/東方財富資金流）
- 多市場支持（A股 + 加密貨幣 + 外匯 + 全球指數）
- 本地K線管理（local_kline 本地存儲與讀取）
- 股票池管理（stock_universe 最多 20000 只）
- 股票基本面數據（stock_basics）
- 多數據源降級（data_sources 主備切換）
- 數據質量檢查（data_quality）
- 模擬交易（paper_trading）
- 用戶系統（JWT 認證/獨立 watchlist/預警/回測歷史）
- 策略框架（自定義策略上傳/排行榜/模板繼承/策略參數元數據）
- 暗色/亮色主題切換（16 個 Tab，Chart.js + Lightweight Charts + Canvas + chart-pro）

**安全加固：**
- JWT Secret 持久化（data/.jwt_secret，重啟不失效）
- 默認管理員隨機密碼（data/.admin_password，600 權限）
- 演示模式（`SQ_DEMO_MODE`）：GET 讀取白名單開放；POST/DELETE 危險寫入需 Bearer Token
- CORS 收緊（默認 localhost，非 *）
- Redis 密碼認證 + 不暴露端口
- WebSocket 支持 ?token=xxx 認證 + 連接上限 50 + 批量清理死連接
- API 限流（120 次/分鐘/IP，可配置）+ 數據請求限流
- Pydantic 字段校驗（端口範圍/佣金範圍/日誌級別枚舉/Redis URL 格式）
- SQLite WAL 模式 + busy_timeout=5000 + thread-local 連接

**配置系統：**
- pydantic-settings（SQ_ 前綴 + 字段校驗）
- 19 個策略全部有默認參數
- 5 個預設組合（穩健型/均衡型/激進型/趨勢跟蹤型/量價驗證型）
- `config show` / `config validate` CLI 命令
- `--alloc "策略:代碼,策略:代碼"` 參數支持所有組合命令
- config.summary() 脫敏配置摘要

**文件結構：**
```
src/
├── config.py               — pydantic-settings 配置（SQ_ 前綴 + 字段校驗）
├── api/
│   ├── app.py              — FastAPI 主應用 + lifespan + WebSocket + 限流
│   ├── constants.py        — 股票名稱常量
│   ├── demo.py             — 演示數據填充
│   ├── dispatch.py         — 任務調度
│   ├── state.py            — 全局狀態
│   ├── ws.py               — WebSocket 路由 + 實時推送
│   └── routers/
│       ├── alerts.py       — 預警規則 CRUD
│       ├── auth.py         — 認證/註冊/重置密碼
│       ├── backtest.py     — 回測/優化/Walk-Forward/熱力圖
│       ├── dashboard_market.py — 儀表盤市場數據
│       ├── data_center.py  — 數據中心（板塊/資金/龍虎榜/基本面/分鐘K）
│       ├── health.py       — 健康檢查
│       ├── indices.py      — 指數行情
│       ├── stocks.py       — 股票列表/搜索/詳情
│       └── tasks.py        — 異步任務管理
├── core/
│   ├── backtest.py         — 19 策略 + SL/TP + 風險指標 + TradeObserver + 滑點/T+1/漲跌停
│   ├── optimize.py         — 網格搜索 + Optuna + 並行
│   ├── portfolio.py        — 11+ 種組合方法 + 相關性 + 有效前沿
│   ├── walkforward.py      — Walk-Forward 分析
│   ├── auto_optimize.py    — 全自動參數尋優
│   ├── heatmap.py          — 參數敏感性熱力圖
│   ├── screener.py         — 股票篩選器
│   ├── benchmark.py        — 滬深300基準對比
│   ├── export.py           — CSV/JSON 導出
│   ├── realtime.py         — 東財五檔盤口
│   ├── alerts.py           — 預警引擎 + 多渠道通知
│   ├── alert_rules_auto.py — 自動預警規則生成
│   ├── history.py          — 歷史數據下載 + 增量更新
│   ├── download_tasks.py   — 下載任務管理（並行+進度）
│   ├── local_kline.py      — 本地K線存儲
│   ├── market_fetch.py     — 行情數據抓取
│   ├── data_sources.py     — 多數據源降級
│   ├── data_quality.py     — 數據質量檢查
│   ├── db.py               — SQLite + LRU 緩存 + WAL
│   ├── cache.py            — 進階緩存
│   ├── api_cache.py        — API 響應緩存
│   ├── result_cache.py     — 計算結果緩存
│   ├── scheduler.py        — APScheduler 定時任務
│   ├── report.py           — 每日策略報告
│   ├── report_enhanced.py  — 增強報告
│   ├── signals.py          — 實時信號引擎（SignalEngine + 強度評分）
│   ├── auth.py             — JWT 用戶認證（持久化 Secret + 隨機密碼）
│   ├── strategy_base.py    — 策略基類（用戶自定義策略）
│   ├── strategy_params_meta.py — 策略參數元數據
│   ├── leaderboard.py      — 策略排行榜
│   ├── task_manager.py     — 異步任務管理器
│   ├── compute_budget.py   — 計算資源預算分配
│   ├── risk_manager.py     — 風險管理器
│   ├── risk_pipeline.py    — 多階段風控管線
│   ├── stock_universe.py   — 股票池管理（最多 20000）
│   ├── stock_basics.py     — 股票基本面
│   ├── sector.py           — 板塊數據
│   ├── capital_flow.py     — 資金流向
│   ├── eastmoney_flow.py   — 東方財富資金流
│   ├── dragon_tiger.py     — 龍虎榜
│   ├── fundamental.py      — 基本面數據
│   ├── crypto.py           — 加密貨幣行情
│   ├── forex.py            — 外匯行情
│   ├── global_market.py    — 全球市場指數
│   ├── yahoo_finance.py    — Yahoo Finance 數據源
│   └── paper_trading.py    — 模擬交易
├── models/
│   ├── schemas.py          — Pydantic 數據模型
│   └── user.py             — 用戶模型
└── utils/
    └── logger.py           — 日誌（RotatingFileHandler）

static/
├── index.html              — SPA 主頁（16 Tab）
├── css/style.css           — 暗色/亮色主題
└── js/
    ├── app.js              — 路由 + 生命週期 + 浮動面板
    ├── api.js              — HTTP 客戶端
    ├── utils.js            — 工具函數
    ├── dashboard.js        — 儀表盤
    ├── backtest.js         — 回測
    ├── optimize.js         — 優化（含過擬合警告）
    ├── portfolio.js        — 組合分析
    ├── signals.js          — 實時信號
    ├── screener.js         — 篩選器
    ├── data.js             — 數據中心
    ├── heatmap.js          — 熱力圖
    ├── charts.js           — 圖表基礎
    ├── chart-pro.js        — 進階圖表（Lightweight Charts）
    ├── analysis.js         — 分析
    ├── scheduler.js        — 定時任務
    ├── tasks.js            — 任務面板（排序/展開/刪除）
    └── task-common.js      — 任務共享模塊

tests/                      — 27 個測試文件，82 個測試全通過
├── conftest.py             — 跨平台 temp DB + session-scoped fixture
├── test_smoke_api.py       — 冒煙測試
├── test_auth_*.py          — 認證流程/寫保護/默認管理員
├── test_backtest.py        — 回測核心
├── test_backtest_pagination.py — 回測分頁
├── test_strategies.py      — 19 策略逐一測試
├── test_portfolio.py       — 組合指標
├── test_portfolio_methods.py — 組合方法
├── test_signals.py         — 信號引擎
├── test_screener.py        — 篩選器
├── test_tasks_api.py       — 任務 API
├── test_tasks_rate_limit.py — 任務限流
├── test_data_rate_limit.py — 數據限流
├── test_dashboard_market.py — 儀表盤
├── test_data_center_api.py — 數據中心
├── test_market_fetch.py    — 行情抓取
├── test_download_parallel.py — 並行下載
├── test_local_kline.py     — 本地K線
├── test_stock_universe.py  — 股票池
├── test_eastmoney_flow.py  — 東財資金流
├── test_sector_*.py        — 板塊數據
├── test_capital_flow_aggregate.py — 資金流聚合
├── test_scheduler.py       — 定時任務
└── test_alert_rules_auto.py — 自動預警規則
```

## 已完成（第一輪 ~ 第六輪）

### ✅ 第一輪
1. 風險指標增強（VaR/CVaR/Sortino/Calmar/回撤恢復/年化波動/月勝率/盈虧比）
2. 回測結果持久化 + 歷史查詢 + 對比
3. Walk-Forward 分析（滾動窗口，過擬合檢測）
4. 策略參數自動尋優（跨股票共識推薦）
5. 定時任務 + 自動報告（APScheduler 15:30）
6. 通知渠道完善（企微/釘釘/Telegram + 模板 + 節流）

### ✅ 第二輪
7. 策略熱力圖（Canvas 渲染，最佳參數高亮）
8. 股票篩選器（5 種篩選條件，一鍵加入監控）
9. 性能優化（LRU 緩存 + 多進程並行網格搜索）
10. 增量數據下載（檢查最新日期，只下載新增）
11. 基準對比（滬深300，Alpha/Beta/信息比率/跟蹤誤差）
12. 止損/止盈（策略風控層 + 移動止損）
13. 數據導出（CSV/JSON）
14. 組合分析增強（相關性矩陣 + 有效前沿）
15. 前端體驗優化（新Tab + 風控輸入 + Canvas熱力圖）

### ✅ 第三輪（v3.0）
16. 進階回測（滑點模擬 + T+1 限制 + 漲跌停控制）
17. 11 種組合方法（風險平價/均值-方差/波動率目標/最大分散化/反相關/狀態切換/動態權重/Kelly/衰退檢測/信號仲裁）
18. 實時信號引擎（SignalEngine + 多策略共識 + 強度評分 + 歷史回放）
19. 數據中心（板塊行情/資金流向/北向資金/龍虎榜/基本面/分鐘K線）
20. 用戶系統（JWT 認證/獨立 watchlist/預警規則/回測歷史）
21. 策略開發框架（自定義策略上傳/策略模板/排行榜/測試）
22. 前端重構（暗色/亮色主題 + 13 Tab + 進階組合 UI + 信號 Tab）

### ✅ 第四輪（v4.0 — 策略擴展 + 中文命名）
23. 策略中文命名（STRATEGY_NAMES 映射，19 種策略均有中文顯示名）
24. 6 種新策略（VWAP/均線通道/拋物線SAR/OBV能量潮/布林帶收窄/ADX趨勢強度）
25. 策略參數優化空間（新增 6 種策略的 PARAM_GRIDS + PARAM_RANGES）

### ✅ 第五輪（v5.0 — 安全加固 + 配置優化）
26. JWT Secret 持久化（data/.jwt_secret，重啟後 Token 不失效）
27. 默認管理員隨機密碼（首次啟動生成，寫入 data/.admin_password）
28. 演示模式認證：讀開放、寫受控（login/register/health + 數據/任務/儀表盤 GET 白名單）
29. CORS 收緊（默認 localhost，生產環境需設置 SQ_CORS_ORIGINS）
30. Redis 安全加固（密碼認證 + 不暴露端口到宿主機）
31. WebSocket 認證（支持 ?token=xxx 參數）
32. API 限流中間件（120 次/分鐘/IP，可通過 SQ_RATE_LIMIT_PER_MINUTE 配置）
33. 配置字段校驗（端口範圍/佣金範圍/日誌級別/Redis URL 格式）
34. 補齊 6 個策略默認參數（vwap/envelope/parabolic_sar/obv/bollinger_squeeze/adx_trend）
35. 新增 2 個預設組合（trend_follower 趨勢跟蹤型 / value_trap_avoider 量價驗證型）
36. `config show` / `config validate` CLI 命令
37. 所有組合命令支持 `--alloc` 自定義參數
38. 移除廢棄的 @app.on_event，統一到 lifespan 上下文管理器
39. reset-password 不再有默認密碼，必須顯式提供

### ✅ 第六輪（v6.0 — 多市場 + 異步任務 + 測試補全）
40. 多市場支持（加密貨幣 5 只 + 外匯 4 對 + 全球指數）
41. 異步任務管理器（task_manager 提交→輪詢→取消→刪除）
42. 下載任務管理（download_tasks 並行下載 + 進度追蹤）
43. 計算資源預算（compute_budget 動態分配 CPU/內存）
44. 風險管線（risk_pipeline 多階段風控）
45. 模擬交易（paper_trading）
46. 多數據源降級（data_sources 主備自動切換）
47. 數據質量檢查（data_quality）
48. 股票池管理（stock_universe 最多 20000 只）
49. 股票基本面（stock_basics）
50. 本地K線管理（local_kline）
51. 東方財富資金流（eastmoney_flow）
52. 自動預警規則（alert_rules_auto）
53. API 緩存 + 結果緩存（api_cache / result_cache）
54. 增強報告（report_enhanced）
55. Yahoo Finance 數據源（yahoo_finance）
56. WebSocket 連接上限 50 + 批量清理死連接
57. SQLite WAL 模式 + busy_timeout + thread-local 連接
58. 測試補全到 82 個（27 個測試文件，覆蓋認證/回測/組合/信號/篩選/任務/限流/數據中心等）
59. 跨平台測試修復（tempfile.gettempdir 替代 /tmp）
60. 前端任務面板重寫（排序/展開詳情/刪除/載入指示器/空狀態引導）
61. 前端過擬合風險警告（OOS 對比圖紅綠標註）
62. API 路由重構（拆分到 routers/ 子模塊）
63. 16 個前端 Tab（新增任務/指數/數據中心等）

## 生產檢查清單

| 變量 | 演示 (Render) | 私有生產 |
|------|---------------|----------|
| `SQ_DEMO_MODE` | `true` | `false` |
| `SQ_DEMO_ADMIN_PASSWORD` | 必設 | 可選（登入後改密） |
| `SQ_CORS_ORIGINS` | 實際域名 | 實際域名 |
| `SQ_WS_AUTH_REQUIRED` | 可 false | `true` |
| `SQ_RATE_LIMIT_PER_MINUTE` | 120 | 按需調整 |

## 待優化（第七輪）

### 🔥 高優（建議優先做）

#### 1. 異步化改造（部分完成，繼續深化）
- 回測/優化接口支持異步模式（已支持 task_manager，可優化提交→輪詢體驗）
- `download_stocks` API 改為使用 download_tasks 後台任務
- `download_all_markets` 異步並發下載（asyncio.gather + 信號量控制）

#### 2. 數據庫優化
- 添加索引（daily_klines.code+date, backtest_results.code+strategy, signal_logs.code+triggered_at）
- 列表 API 分頁（/api/stocks, /api/backtest/history, /api/alerts 加 limit+offset）
- 定期清理舊數據的策略（保留最近 N 年）

#### 3. 測試繼續補全
- 現有 27 個測試文件 → 目標覆蓋更多邊界場景：
  - test_crypto.py（加密貨幣）
  - test_forex.py（外匯）
  - test_global_market.py（全球指數）
  - test_paper_trading.py（模擬交易）
  - test_risk_pipeline.py（風控管線）
  - test_compute_budget.py（計算預算）
  - test_data_sources.py（多數據源降級）
  - test_download_tasks.py（下載任務管理）
- API 集成測試（httpx.AsyncClient 測試 FastAPI 端點完整流程）

### 🟡 中優

#### 4. 前端重構
- 提取內嵌 HTML 到獨立模板文件（static/templates/dashboard.html）
- 移動端響應式完善（表格橫向滾動、圖表自適應）
- Lightweight Charts 全面替代 Chart.js 的 K 線圖
- 圖表導出 PNG 功能

#### 5. 通知增強
- 通知隊列（異步發送，失敗重試 3 次）
- 通知歷史記錄（SQLite 表，可查詢）
- 條件通知（只在特定策略觸發時通知）
- ServerChan / Bark 推送支持

#### 6. 回測增強
- 交易成本模型完善（印花稅僅賣出收取、過戶費、佣金最低 5 元）
- 分紅除權處理（復權價格）
- 多周期回測（日/週/月 K 線切換）
- 回測結果對比頁面（選 2-3 個結果並排對比）

### 🟢 低優

#### 7. 監控增強
- 系統健康指標（CPU/內存/磁盤/GPU）
- Prometheus metrics 端點（/metrics）
- 錯誤率統計 + 異常告警

#### 8. 部署優化
- GitHub Actions CI/CD（測試 → 構建 → 部署）
- Docker 多階段構建優化（減小鏡像體積）
- 數據庫遷移到 PostgreSQL（可選，適用於多用戶場景）
- Nginx SSL 配置完善（Let's Encrypt 自動續期）

## 技術約束
- Python 3.12，依賴見 requirements.txt
- SQLite 為主數據庫（WAL 模式，單機部署足夠）
- AKShare 免費接口，有頻率限制（每次請求間隔 ≥0.5s，建議加隨機抖動）
- Backtrader 回測引擎
- FastAPI Web 框架
- 前端優先用原生 JS + Chart.js + Lightweight Charts，不要引入 npm/node 構建鏈
- Pydantic v2 + pydantic-settings 配置管理

## 重要提醒
- 不要改動現有 API 的返回格式（破壞兼容性）
- 新功能加新端點，不要改舊端點的行為
- config.py 的默認值可以改，但環境變量覆蓋機制不能動
- 保留 CLI 入口（main.py），不要刪除
- 安全相關改動必須經過測試驗證
- 敏感文件（.jwt_secret, .admin_password, .env）不能提交到 Git
- 不要推送 .qwen 文件夾到 GitHub
