# 🏗️ Stock-Quant 前後端分拆 + 橫向擴架構重構計劃

> **版本**: v1.0 | **建立日期**: 2026-05-29 | **狀態**: 進行中

---

## 📋 進度追蹤

| 階段 | 狀態 | 工作量 | 重點 |
|------|------|--------|------|
| **P0**: 收費點擴展 | ✅ 完成 | 2天 | 新增 features + limits + gate 函數 |
| **P1**: Celery 正式化 | ✅ 完成 | 2-3天 | 任務狀態遷 Redis |
| **P2**: LLM 新 API | ✅ 完成 | 3-4天 | 策略推薦/報告/代碼生成 |
| **P3**: 多級緩存 + API 無狀態化 | ✅ 完成 | 2-3天 | 反應速度飛躍 |
| **P4**: SSE 任務進度 | ✅ 完成 | 1天 | 替代輪詢 |
| **P5**: app.py 路由拆分 | ✅ 完成 | 3-4天 | 2641行→557行 + 9 router |
| **P6**: PostgreSQL | ✅ 完成 | 3-5天 | 27表 ORM + Alembic + 遷移工具 |
| **P7**: docker-compose 重構 | ✅ 完成 | 1天 | PostgreSQL service + profiles |

---

## 一、現狀分析

### 當前架構問題

| 問題 | 影響 | 嚴重度 |
|------|------|--------|
| **單體 FastAPI** (`app.py` 2706行) 同時承載 API + 靜態文件 + WebSocket | 無法獨立擴展前端/後端 | 🔴 |
| **SQLite 單文件 DB** | 多實例無法共享數據、寫入鎖競爭 | 🔴 |
| **In-process 任務管理** (`task_manager.py` ThreadPoolExecutor) | 任務狀態在進程內存，多實例不可見 | 🔴 |
| **全局內存狀態** (rate limiter, `_tasks` dict, `state.py`) | 無狀態化不足 | 🟡 |
| **前端耦合** (`/`, `/app`, `/admin` 直接返回 HTML) | 前端更新需重啟後端 | 🟡 |

### 已有基礎設施（可復用）

- ✅ `celery_app.py` + `celery_worker.py` — Celery 骨架已就位
- ✅ `redis` — 已支持（cache/result_cache）
- ✅ `docker-compose.yml` — 已有 app + redis + celery-worker + nginx
- ✅ `src/api/routers/` — 路由已按領域拆分（20 個 router 文件）
- ✅ `src/core/` — 業務邏輯與框架已分離
- ✅ CORS 配置已有
- ✅ `billing_plans.py` + `entitlements.py` — 三級方案框架已有

---

## 二、目標架構

```
┌──────────────────────────────────────────────────────────────┐
│                     用戶瀏覽器                                │
│                                                              │
│  static/app.html (保持現有風格)                              │
│  ├── pro/app.js          (Hash 路由 SPA)                    │
│  ├── pro/modules/*.js    (頁面模組)                          │
│  ├── pro/esm/*.mjs       (漸進式 ESM 遷移)                   │
│  ├── charts.js, api.js   (全局 JS)                          │
│  └── pro.css             (樣式)                              │
│                                                              │
│  所有 API 調用走 Api.fetch('/api/...')                       │
│  所有 LLM 調用走 Api.post('/api/llm/...') (後端代理)        │
│  實時進度走 SSE (EventSource) 替代輪詢                       │
│  行情走 WebSocket (現有)                                      │
└──────────────┬───────────────────────┬───────────────────────┘
               │ REST / SSE            │ WebSocket
               ▼                       ▼
┌──────────────────────────────────────────────────────────────┐
│              Nginx Load Balancer                              │
│  ├── proxy_cache (GET /api/* 5s TTL)                         │
│  ├── /api/*  → upstream api_backend (多實例)                 │
│  ├── /ws     → upstream api_backend                          │
│  ├── /static → 緩存 1d                                       │
│  └── /*      → app.html (SPA fallback)                       │
└──────────────┬───────────────────────┬───────────────────────┘
               │                       │
    ┌──────────▼──────┐     ┌──────────▼──────┐
    │  API Server #1  │     │  API Server #2  │  ← 橫向擴展
    │  (FastAPI)      │     │  (FastAPI)      │
    │  Stateless      │     │  Stateless      │
    │  ┌────────────┐ │     │                 │
    │  │LLM Service │ │     │                 │
    │  │(後端代理)   │ │     │                 │
    │  │Model Router│ │     │                 │
    │  │Prompt Cache│ │     │                 │
    │  └────────────┘ │     │                 │
    └────────┬────────┘     └────────┬────────┘
             │                       │
    ┌────────▼───────────────────────▼────────┐
    │          Shared Infrastructure           │
    │  ┌──────────┐  ┌───────┐  ┌──────────┐  │
    │  │PostgreSQL│  │ Redis │  │ Celery   │  │
    │  │(數據)     │  │(緩存  │  │ Workers  │  │
    │  │          │  │ Pub/Sub│  │(N個，    │  │
    │  │          │  │ 隊列)  │  │ 橫向擴展) │  │
    │  └──────────┘  └───────┘  └──────────┘  │
    └──────────────────────────────────────────┘
                          │
              ┌───────────▼───────────┐
              │    LLM Provider       │
              │  ┌──────────────────┐ │
              │  │ GPT-4o-mini      │ │ ← 輕量任務
              │  │ GPT-4o / Claude  │ │ ← 重量任務
              │  │ Ollama 本地模型   │ │ ← 可選自部署
              │  └──────────────────┘ │
              └───────────────────────┘
```

---

## 三、收費點方案

### 方案結構：Free / Pro / Pro+AI / Institutional

#### A. 核心計算能力

| 功能 | Free | Pro ($29/月) | Pro+AI ($44/月) | Institutional ($199/月) |
|------|------|-------------|-----------------|----------------------|
| 基礎回測 | 8次/日 | 80次/日 | 80次/日 | 無限 |
| 進階回測（滑點/T+1/漲跌停） | ❌ | ✅ | ✅ | ✅ |
| 組合回測（基礎等權） | 2次/日 | 30次/日 | 30次/日 | 無限 |
| 組合回測（進階：風險平價/MVO/HRP 等 20+ 方法） | ❌ | ✅ | ✅ | ✅ |
| 參數優化（Grid + Optuna） | ❌ | 10次/日 | 10次/日 | 無限 |
| Walk-Forward 分析 | ❌ | 5次/日 | 10次/日 | 無限 |
| 蒙特卡羅模擬 | ❌ | 10次/日 | 20次/日 | 無限 |
| 有效前沿分析 | ❌ | ✅ | ✅ | ✅ |
| 策略衰退檢測 | ❌ | ✅ | ✅ | ✅ |
| 信號回測驗證 | ❌ | 3次/日 | 10次/日 | 無限 |
| 全面回測報告 | ❌ | 3次/日 | 10次/日 | 無限 |

#### B. AI 智能分析

| 功能 | Free | Pro ($29/月) | Pro+AI ($44/月) | Institutional |
|------|------|-------------|-----------------|---------------|
| AI 基礎問答 | ❌ | 20次/日 | 100次/日 | 無限 |
| AI 策略推薦 | ❌ | ❌ | 10次/日 | 無限 |
| AI 回測報告解讀 | ❌ | 5次/日 | 30次/日 | 無限 |
| AI 策略代碼生成 | ❌ | ❌ | 5次/日 | 無限 |
| AI 參數調優建議 | ❌ | ❌ | 10次/日 | 無限 |
| AI 市場晨報/日報 | ❌ | ❌ | 每日自動 | 每日自動 |

#### C. 實時信號 & 盯盤

| 功能 | Free | Pro | Pro+AI | Institutional |
|------|------|-----|--------|---------------|
| 歷史信號查詢 | ✅ | ✅ | ✅ | ✅ |
| 實時信號推送 (WebSocket) | ❌ | 5隻 | 20隻 | 無限 |
| 信號熱力圖 | ❌ | ✅ | ✅ | ✅ |
| 信號排名 | ❌ | 10次/日 | 50次/日 | 無限 |
| 信號強度評分 | ❌ | ✅ | ✅ | ✅ |
| 策略排行榜 | 只看 | ✅ 參與 | ✅ 參與 | ✅ 管理 |

#### D. 風控 & 風險管理

| 功能 | Free | Pro | Pro+AI | Institutional |
|------|------|-----|--------|---------------|
| 基礎倉位計算（固定比例） | ✅ | ✅ | ✅ | ✅ |
| 進階倉位計算（ATR/Kelly/波動率/回撤） | ❌ | ✅ | ✅ | ✅ |
| 風險預算檢查 | ❌ | ✅ | ✅ | ✅ |
| 回撤保護分析 | ❌ | ✅ | ✅ | ✅ |
| 風控管道（信號→倉位→交易） | ❌ | ❌ | ❌ | ✅ |
| 策略相關性監控 | ❌ | ❌ | ❌ | ✅ |
| 多策略信號仲裁 | ❌ | ❌ | ❌ | ✅ |

#### E. 數據 & 策略生態

| 功能 | Free | Pro | Pro+AI | Institutional |
|------|------|-----|--------|---------------|
| 基礎 K 線下載 | ✅ | ✅ | ✅ | ✅ |
| 分鐘 K 線 | ❌ | ✅ | ✅ | ✅ |
| 數據質量修復 | ❌ | ✅ | ✅ | ✅ |
| 多市場多股對比 | ❌ | ✅ | ✅ | ✅ |
| 自定義策略上傳 | ❌ | 5個 | 10個 | 無限 |
| 沙箱回測 | ❌ | ✅ | ✅ | ✅ |
| 數據導出 (CSV/JSON) | ❌ | ✅ (1000行) | ✅ (10000行) | ✅ 無限 |
| REST API 訪問 | ❌ | ❌ | ❌ | ✅ (API Key) |
| 模擬交易 | 1 session | 5 sessions | 10 sessions | 無限 |

#### F. 配額 & 限制

| 項目 | Free | Pro | Pro+AI | Institutional |
|------|------|-----|--------|---------------|
| 自選股上限 | 15 | 80 | 120 | 500 |
| 持倉位置上限 | 5 | 40 | 60 | 200 |
| 並行任務 | 1 | 4 | 6 | 12 |
| 任務超時 | 300s | 1800s | 1800s | 3600s |
| 雲端配置同步 | ❌ | ✅ | ✅ | ✅ |
| 資產庫主題包 | ❌ | ✅ | ✅ | ✅ |
| 任務優先隊列 | ❌ | ✅ | ✅ | ✅ |

---

## 四、P0: 收費點擴展 — 詳細設計

### 4.1 新增 Feature ID

```python
# billing_plans.py — FEATURE_LABELS 新增

FEATURE_LABELS = {
    # === 現有 ===
    "backtest_basic": "基礎回測與 K 線",
    "backtest_advanced": "進階風控參數回測",
    "compare_multimarket": "多市場多股對比",
    "portfolio_basic": "組合回測（等權/基礎）",
    "portfolio_advanced": "風險平價 / MVO / 有效前沿",
    "allocation_cloud": "雲端個人配置同步",
    "assets_pro": "資產庫主題包與詳情",
    "ai_assistant": "AI 投研助手",
    "task_priority": "任務優先隊列",
    "data_export": "結果導出與 API",
    "team_seats": "團隊席位與 SSO",

    # === P0 新增 ===
    # AI 進階
    "ai_strategy_recommend": "AI 策略智能推薦",
    "ai_report_interpret": "AI 回測報告深度解讀",
    "ai_code_generate": "AI 策略代碼生成",
    "ai_param_suggest": "AI 參數調優建議",
    "ai_market_report": "AI 市場晨報/日報",

    # 高級分析
    "walkforward": "Walk-Forward 分析",
    "monte_carlo": "蒙特卡羅模擬",
    "efficient_frontier": "有效前沿分析",
    "degradation_detect": "策略衰退檢測",
    "signal_backtest": "信號回測驗證",
    "signal_heatmap": "信號熱力圖",
    "signal_ranking": "信號排名",
    "full_report": "全面回測報告",

    # 風控
    "risk_position_calc": "進階倉位計算",
    "risk_budget_check": "風險預算檢查",
    "risk_drawdown_protect": "回撤保護分析",
    "risk_pipeline": "風控管道",
    "correlation_monitor": "策略相關性監控",
    "signal_arbitration": "多策略信號仲裁",

    # 數據
    "minute_kline": "分鐘 K 線",
    "data_quality_repair": "數據質量修復",
    "custom_strategies": "自定義策略",
    "sandbox_backtest": "沙箱回測",
    "strategy_leaderboard": "策略排行榜參與",
    "paper_trading": "模擬交易",
    "realtime_ws_symbols": "實時信號推送",
    "rest_api_access": "REST API 訪問",
}
```

### 4.2 PlanLimits 擴展

```python
@dataclass(frozen=True)
class PlanLimits:
    daily_backtests: int = 5
    daily_portfolio_runs: int = 3
    daily_optimize_runs: int = 1
    daily_ai_queries: int = 0          # 🆕
    daily_walkforward: int = 0         # 🆕
    daily_monte_carlo: int = 0         # 🆕
    daily_signal_ranking: int = 0      # 🆕
    daily_full_report: int = 0         # 🆕
    max_watchlist: int = 20
    max_custom_strategies: int = 0     # 🆕
    max_paper_sessions: int = 1        # 🆕
    max_allocation_positions: int = 10
    concurrent_tasks: int = 2
    realtime_ws_symbols: int = 0       # 🆕
    export_row_limit: int = 0          # 🆕
```

### 4.3 Entitlements 新增 gate 函數

```python
# entitlements.py 新增

def gate_walkforward(user: User) -> None:
    if not user_has_feature(user, "walkforward"):
        _feature_locked("walkforward", "Walk-Forward 分析需 Pro 方案", user)
    check_quota(user, "walkforward")
    record_usage(user, "walkforward")

def gate_monte_carlo(user: User) -> None:
    if not user_has_feature(user, "monte_carlo"):
        _feature_locked("monte_carlo", "蒙特卡羅模擬需 Pro 方案", user)
    check_quota(user, "monte_carlo")
    record_usage(user, "monte_carlo")

def gate_full_report(user: User) -> None:
    if not user_has_feature(user, "full_report"):
        _feature_locked("full_report", "全面回測報告需 Pro 方案", user)
    check_quota(user, "full_report")
    record_usage(user, "full_report")

def gate_ai_strategy_recommend(user: User) -> None:
    if not user_has_feature(user, "ai_strategy_recommend"):
        _feature_locked("ai_strategy_recommend", "AI 策略推薦需 Pro+AI 方案", user)
    check_quota(user, "ai_query")
    record_usage(user, "ai_query")

def gate_ai_code_generate(user: User) -> None:
    if not user_has_feature(user, "ai_code_generate"):
        _feature_locked("ai_code_generate", "AI 策略代碼生成需 Pro+AI 方案", user)
    check_quota(user, "ai_query")
    record_usage(user, "ai_query")

def gate_risk_pipeline(user: User) -> None:
    if not user_has_feature(user, "risk_pipeline"):
        _feature_locked("risk_pipeline", "風控管道需 Institutional 方案", user)

def gate_signal_ranking(user: User) -> None:
    if not user_has_feature(user, "signal_ranking"):
        _feature_locked("signal_ranking", "信號排名需 Pro 方案", user)
    check_quota(user, "signal_ranking")
    record_usage(user, "signal_ranking")
```

---

## 五、P1: Celery 正式化 — 設計

### 5.1 任務狀態遷移 Redis

```
現狀：task_manager._tasks (進程內 dict)
目標：Redis Hash + Stream

Hash key: sq:tasks:{task_id}
Fields: status, type, params, result, progress, user_id, created_at, updated_at

Stream: sq:task-events (用於 SSE 推送)
```

### 5.2 dispatch 走 Celery

```python
# 現在：ThreadPoolExecutor
submit_task(task_id, work_fn)

# 改後：
from src.core.celery_tasks import execute_task
execute_task.delay(task_id, task_type, params)
```

### 5.3 SSE/WebSocket 跨實例廣播

```python
# Redis Pub/Sub 頻道
channel: sq:task-progress  → 任務進度
channel: sq:market-data    → 行情推送
channel: sq:ws-broadcast   → WebSocket 廣播
```

---

## 六、P2: LLM 新 API — 設計

### 新增端點（全部後端代理，前端不直接調 LLM）

| 端點 | 方法 | 功能 | 配額消耗 |
|------|------|------|----------|
| `/api/llm/chat` | POST | 基礎問答（現有） | ai_query |
| `/api/llm/chat/stream` | POST | 流式問答（現有） | ai_query |
| `/api/llm/analyze` | POST | 回測結果解讀 | ai_query |
| `/api/llm/suggest` | POST | 策略推薦 | ai_query |
| `/api/llm/generate` | POST | 策略代碼生成 | ai_query |
| `/api/llm/optimize` | POST | 參數調優建議 | ai_query |
| `/api/llm/report` | POST | 投資報告生成 | ai_query |
| `/api/llm/morning` | POST | 市場晨報 | ai_query |

### LLM 模型路由（後端內部）

```
輕量任務（GPT-4o-mini）：
  - 股票基本面摘要
  - 數據異常檢測
  - 信號翻譯
  - 簡單問答

重量任務（GPT-4o / Claude）：
  - 策略深度分析
  - 回測報告解讀
  - 策略代碼生成
  - 多策略組合方案設計
```

### Prompt Cache（Redis）

```
key: llm:cache:{prompt_hash}
TTL: 1h（相同問題+相同數據→直接返回上次結果）
```

---

## 七、P3-P7: 後續階段概要

### P3: 多級緩存 + API 無狀態化

- Rate Limiter 遷移到 Redis
- api_cache.py 升級為 Redis-first
- Nginx 增加 API 緩存層
- Session/auth state 走 Redis

### P4: SSE 任務進度

- 新增 `/api/tasks/{id}/stream` SSE 端點
- 前端 `pro/esm/services/sse-client.mjs`
- 替代前端輪詢

### P5: app.py 路由拆分

- 將 app.py 中 60+ 直接路由遷到對應 router 文件
- 新建: cache, scheduler, notifications, config, portfolio, heatmap, screener, benchmark, signals, report, risk, data_quality, paper_trading, export, strategies, realtime

### P6: PostgreSQL

- SQLAlchemy ORM + Alembic 遷移
- SQLite → PostgreSQL 數據遷移工具
- 連接池 (asyncpg)
- Read Replica 支持

### P7: docker-compose 重構

- 分離: api / worker / frontend / postgres / redis / nginx
- api 和 worker 可獨立水平擴展
- Nginx 負載均衡

---

## 八、關鍵性能指標預期

| 指標 | 現在 | 優化後 | 方法 |
|------|------|--------|------|
| API 響應（熱查詢） | 50-200ms | <10ms | Nginx 緩存 + Redis L2 |
| 回測提交到結果 | 5-30s（輪詢） | 即時（SSE） | Server-Sent Events |
| 並行回測容量 | 4-8 線程 | N×4 線程 | Celery Worker 擴展 |
| LLM 回答速度 | 5-15s | 2-8s | 模型路由 + Prompt Cache |
| LLM 成本 | 100% | 40-50% | 緩存 + 小模型分流 |

---

*最後更新*: 2026-05-29