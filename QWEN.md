## 逐項可行性評估

基於對 `src/core/` 下 8 個關鍵模塊的代碼審查，以下是路線圖每項與現有代碼庫的對齊分析：

---

### 第一階段

#### 1. 數據源智能路由與熔斷機制 ✅ 高度可行，增量改造

**現狀**：`market_fetch.py` 已有完整的多源降級鏈（IB → TradingView → 本地庫 → Yahoo → 東財 → Twelve Data），`pipeline_observability.py` 已有 `record_kline_fetch(source)` 記錄數據源命中。但**沒有熔斷器**——每次失敗都走完整 try-except 降級鏈，持續浪費請求。

**改造量**：
- 新建 `src/core/circuit_breaker.py`（~150 行），提供 `@circuit_breaker(name, failure_threshold, recovery_timeout)` 裝飾器
- 在 `market_fetch.py` 的每個數據源調用點包裹熔斷器（~6 處修改）
- 在 `pipeline_observability.py` 增加熔斷狀態查詢 API
- **不需要**改動 `data_pipeline.py` 或 `db.py`

**風險**：低。純增量，不影響現有降級邏輯。

#### 2. SQLite 併發寫入優化 ⚠️ 大部分已完成

**現狀**：`database/connection.py` **已開啟 WAL 模式**（第 31 行 `PRAGMA journal_mode=WAL`），已配置 `busy_timeout=5000`、`mmap_size=256MB`、`cache_size=64MB`。`task_manager.py` 已使用 `ThreadPoolExecutor` 而非 `ProcessPoolExecutor`（回測任務在線程池中運行）。

**仍需改造**：
- **Writer Queue 模式**：目前 `db.py` 的 `save_daily_kline()` 和 `save_backtest_result()` 直接在調用線程寫庫。在高併發場景下（如全市場下載 5000 隻股票），多線程同時寫入會觸發 `busy_timeout`。
- 改造方案：在 `db.py` 增加一個 `_write_queue: queue.Queue` 和 `_writer_thread`，所有寫操作入隊，單線程出隊批量 `executemany`。
- **工作量**：中等（~200 行），但需要仔細處理 `get_conn()` 上下文管理器的線程歸屬。

#### 3. 代理池與請求指紋隨機化 ✅ 簡單可行

**現狀**：`src/core/data_sources.py` 的 `get_session()` 返回 `requests.Session`。目前 User-Agent 是固定的。

**改造量**：
- 在 `data_sources.py` 的 `get_session()` 中注入隨機 UA 和 Accept-Language（~30 行）
- 新增 `SQ_PROXY_POOL_URL` 環境變量，在 `get_session()` 中配置 proxy（~20 行）
- **不需要**改動任何業務邏輯

---

### 第二階段

#### 1. Polars 化 ⚠️ 高風險，建議漸進

**現狀**：`db.py` 的 `load_daily_kline()` 返回 `pd.DataFrame`，`backtest.py` 的 `prepare_data()` 也返回 Pandas。30+ 策略（`src/core/strategies/`）全部基於 Backtrader，而 Backtrader 的數據源是 `bt.feeds.PandasData`。

**關鍵障礙**：
- **Backtrader 不支持 Polars**：策略引擎核心依賴 Backtrader 的 `PandasData` feed，遷移 Polars 意味著要麼（a）在 feed 入口處轉換 `pl.DataFrame → pd.DataFrame`（收益極小），要麼（b）徹底替換 Backtrader（工作量巨大，重寫 30+ 策略）。
- **建議**：僅在**數據清洗層**（`prepare_data`、K 線合併）使用 Polars，最終轉為 Pandas 送入 Backtrader。這可以獲得 3-5x 的清洗加速，但不觸及策略層。

**Numba JIT**：對 Turtle、Dual Thrust 等有狀態機邏輯的策略，可以嘗試 JIT 加速。但 Backtrader 的 `next()` 方法依賴 `self.data` 對象，Numba 無法直接裝飾。

#### 2. Optuna Redis 分佈式尋優 ✅ 可行，改造量小

**現狀**：`optimize.py` 的 `optuna_search()` 使用 `optuna.create_study(direction="maximize")`（內存存儲），`n_jobs` 參數已支持但用於單機多線程。`docker-compose.yml` 已有 Redis 服務。

**改造量**：
- 在 `optuna.create_study()` 中加入 `storage="redis://localhost:6379"`（~5 行核心改動）
- 增加環境變量 `SQ_OPTUNA_STORAGE_URL` 控制存儲後端
- 多節點只需啟動多個 worker 連接同一 Redis

**注意**：需要確認 `requirements.txt` 中是否有 `optuna[integration]` 額外依賴（`RedisStorage` 需要 `redis` 庫）。

#### 3. WebSocket 背壓機制 ✅ 可行

**現狀**：`src/api/ws.py`（或等效 WebSocket handler）目前是直接推送。`task_manager.py` 已有 WebSocket 消息推送（`task_*` 消息類型）。

**改造量**：在 WebSocket handler 中增加積壓檢測和降採樣邏輯（~100 行）。

---

### 第三階段

#### 1. 任務隊列重構 ⚠️ 中等風險

**現狀**：`task_manager.py`（1767 行）是自研的完整任務系統，包含：
- `ThreadPoolExecutor` + 優先級（`PRIORITY_HIGH/NORMAL/LOW`）
- 去重（`task_type + params_hash`）
- 協作式取消（`is_task_cancelled()`）
- WebSocket 即時推送
- 重試機制（`task_retry.py`）
- 前端完整 UI（`tasks-pro.js`，~800 行）

**遷移風險**：
- 現有 15+ 任務類型的 executor（`task_executors.py`）全部依賴 `task_manager` 的 API
- 前端 `tasks-pro.js` 通過 WebSocket 接收 `task_*` 消息，格式需兼容
- `celery_worker.py` 和 `src/core/celery_app.py` **已存在**（用於可選的 Celery 模式），但主流程未使用

**建議**：先將 `task_manager` 的存儲層從內存 `dict` 遷移到 Redis（`task_store.py` 已有此設計意圖），再逐步引入 ARQ/Celery 作為執行後端。

#### 2. DuckDB / TimescaleDB ⚠️ 已有基礎設施

**現狀**：
- `src/core/database/orm_base.py`：SQLAlchemy Base
- `src/core/database/models.py`：ORM 模型
- `src/core/database/postgres_config.py`：PostgreSQL 連接配置
- `alembic.ini` + `migrations/`：Alembic 遷移框架
- `scripts/migrate_sqlite_to_pg.py`：SQLite → PG 遷移腳本

**結論**：PostgreSQL 遷移的**基礎設施已就緒**，但主流程仍走 SQLite。遷移需要將 `db.py` 中的所有 `get_conn()` 調用切換為 SQLAlchemy session，這是一個大規模重構（`db.py` 514 行 + 所有調用方）。

#### 3. 多租戶配額與計費 ✅ 已有基礎

**現狀**：`src/core/auth.py`（JWT 認證）、`src/core/billing_plans.py`（方案定義）、`src/core/entitlements.py`（權限控制）、`src/core/pricing_store.py`（定價存儲）、`src/api/routers/billing.py`（計費 API）均已存在。前端 `pricing-pro.js` 已完成定價頁面。

---

### 總結優先級建議

| 項目 | 現有基礎 | 改造量 | 建議順序 |
|------|---------|--------|---------|
| 熔斷器 | 有降級，無熔斷 | ~200 行新文件 + 6 處修改 | **第一**（最高性價比） |
| 代理池 + UA 隨機 | 有 Session | ~50 行 | **第一**（極低成本） |
| Writer Queue | WAL 已開 | ~200 行 | **第一** |
| Optuna Redis | 有 Optuna + Redis | ~10 行核心 | **第二** |
| WebSocket 背壓 | 有 WS | ~100 行 | **第二** |
| Polars 清洗層 | Pandas | ~300 行，不觸及策略 | **第二**（漸進） |
| 任務存儲 Redis 化 | 有 task_store.py 意圖 | ~400 行 | **第三** |
| PostgreSQL 主遷移 | 基礎設施就緒 | 大規模重構 | **第三** |
| 多租戶計費 | auth/billing 已有 | 中等 | **第三** |

如果需要我開始實施其中任何一項，請 **toggle to Act mode**，我可以從第一優先級（熔斷器 + 代理池 + Writer Queue）開始。