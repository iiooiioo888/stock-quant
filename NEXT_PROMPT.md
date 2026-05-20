# stock-quant 下一輪優化提示詞

## 項目位置
`/root/.openclaw/workspace/stock-quant/`
GitHub: https://github.com/iiooiioo888/stock-quant

## 當前狀態（v5.0 — 安全加固 + 配置優化後）

生產級 A 股量化系統，FastAPI + SQLite + Backtrader，~8500+ 行代碼，已部署可運行。

**核心功能（25+ 個模塊）：**
- 19 種策略回測 + 止損/止盈/移動止損 + 滑點/T+1/漲跌停
- 參數優化（網格搜索 + Optuna + 多進程並行）
- 組合回測（多策略多股票 + 相關性矩陣 + 有效前沿）
- 11 種組合方法（等權/風險平價/MVO/波動率目標/最大分散化/反相關/狀態切換/動態權重/Kelly/衰退檢測/信號仲裁）
- Walk-Forward 滾動窗口分析（過擬合檢測）
- 全自動參數尋優（跨股票共識推薦）
- 策略熱力圖（參數敏感性 Canvas 渲染）
- 股票篩選器（MA多頭/量比/近高點/漲幅/站上均線）
- 滬深300基準對比（Alpha/Beta/信息比率）
- 風險指標全套（VaR/CVaR/Sortino/Calmar/月勝率/盈虧比）
- 回測結果持久化 + 歷史查詢 + CSV/JSON 導出
- 定時任務（APScheduler）+ 每日策略報告
- 多渠道通知（企微/釘釘/Telegram + 模板 + 節流）
- 增量數據下載（只下載新增部分）
- LRU 數據緩存（64 stocks）
- WebSocket 實時行情 + 預警規則 CRUD
- 實時信號引擎（當前/歷史/強度評分）
- 數據中心（板塊/資金流向/龍虎榜/基本面/分鐘K線）
- 用戶系統（JWT 認證/獨立 watchlist/預警/回測歷史）
- 策略框架（自定義策略上傳/排行榜/模板繼承）
- 暗色/亮色主題切換（13 個 Tab，Chart.js + Lightweight Charts + Canvas）

**安全加固（v5.0 新增）：**
- JWT Secret 持久化（data/.jwt_secret，重啟不失效）
- 默認管理員隨機密碼（data/.admin_password，600 權限）
- 演示模式（`SQ_DEMO_MODE`）：GET 讀取白名單開放；POST/DELETE 危險寫入需 Bearer Token
- CORS 收緊（默認 localhost，非 *）
- Redis 密碼認證 + 不暴露端口
- WebSocket 支持 ?token=xxx 認證
- API 限流（120 次/分鐘/IP，可配置）
- Pydantic 字段校驗（端口範圍/佣金範圍/日誌級別枚舉）

**配置優化（v5.0 新增）：**
- 19 個策略全部有默認參數（之前缺 6 個）
- 5 個預設組合（新增 trend_follower + value_trap_avoider）
- `config show` / `config validate` CLI 命令
- `--alloc "策略:代碼,策略:代碼"` 參數支持所有組合命令
- config.summary() 脫敏配置摘要

**文件結構：**
```
src/config.py           — pydantic-settings 配置（SQ_ 前綴 + 字段校驗）
src/core/backtest.py    — 19 策略 + SL/TP + 風險指標 + TradeObserver + 滑點/T+1/漲跌停
src/core/optimize.py    — 網格搜索 + Optuna + 並行
src/core/portfolio.py   — 11 種組合方法 + 相關性 + 有效前沿（1668 行）
src/core/walkforward.py — Walk-Forward 分析
src/core/auto_optimize.py — 全自動參數尋優
src/core/heatmap.py     — 參數敏感性熱力圖
src/core/screener.py    — 股票篩選器
src/core/benchmark.py   — 滬深300基準對比
src/core/export.py      — CSV/JSON 導出
src/core/realtime.py    — 東財五檔盤口
src/core/alerts.py      — 預警引擎 + 多渠道通知
src/core/history.py     — 歷史數據下載 + 增量更新
src/core/db.py          — SQLite + LRU 緩存
src/core/scheduler.py   — APScheduler 定時任務
src/core/report.py      — 每日策略報告生成
src/core/signals.py     — 實時信號引擎（SignalEngine + 強度評分）
src/core/auth.py        — JWT 用戶認證（持久化 Secret + 隨機密碼）
src/core/strategy_base.py — 策略基類（用戶自定義策略）
src/core/leaderboard.py — 策略排行榜
src/core/sector.py      — 板塊數據
src/core/capital_flow.py — 資金流向
src/core/dragon_tiger.py — 龍虎榜
src/core/fundamental.py — 基本面數據
src/core/cache.py       — 進階緩存
src/api/app.py          — FastAPI + 70+ 個端點 + 限流 + 認證中間件
main.py                 — CLI 入口（config/serve/download/backtest/optimize/portfolio/...）
```

## 已完成（第一輪 ~ 第五輪）

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

## 待優化（第六輪）

### 🔥 高優（建議優先做）

#### 1. 異步化改造
- `download_stocks` API 改為後台任務（BackgroundTasks），避免大量下載時 HTTP 超時
- `download_all_markets` 異步並發下載（asyncio.gather + 信號量控制）
- 回測/優化接口支持異步模式（提交任務 → 輪詢結果）

#### 2. 數據庫優化
- 添加索引（daily_klines.code+date, backtest_results.code+strategy, signal_logs.code+triggered_at）
- 列表 API 分頁（/api/stocks, /api/backtest/history, /api/alerts 加 limit+offset）
- WAL 模式（SQLite PRAGMA journal_mode=WAL，提升並發讀性能）
- 定期清理舊數據的策略（保留最近 N 年）

#### 3. 測試補全
- CI：`pytest tests/ -q`（含 `test_smoke_api`、`test_auth_write_protection`）；全量手動：`./test_all.sh`
- 現有 3 個測試文件 → 目標覆蓋核心模塊：
  - test_signals.py（信號引擎）
  - test_portfolio.py 補全（11 種組合方法）
  - test_auth.py（認證流程）
  - test_screener.py（篩選器）
  - test_risk_manager.py（風控）
- API 集成測試（httpx.AsyncClient 測試 FastAPI 端點）

### 🟡 中優

#### 4. 前端重構
- 提取內嵌 HTML 到獨立模板文件（static/templates/dashboard.html）
- 移動端響應式完善（表格橫向滾動、圖表自適應）
- Lightweight Charts 替代 Chart.js 的 K 線圖（更專業）
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
- SQLite 為主數據庫（單機部署足夠）
- AKShare 免費接口，有頻率限制（每次請求間隔 ≥0.5s）
- Backtrader 回測引擎
- FastAPI Web 框架
- 前端優先用原生 JS + Chart.js + Lightweight Charts，不要引入 npm/node 構建鏈

## 重要提醒
- 不要改動現有 API 的返回格式（破壞兼容性）
- 新功能加新端點，不要改舊端點的行為
- config.py 的默認值可以改，但環境變量覆蓋機制不能動
- 保留 CLI 入口（main.py），不要刪除
- 安全相關改動必須經過測試驗證
- 敏感文件（.jwt_secret, .admin_password, .env）不能提交到 Git
