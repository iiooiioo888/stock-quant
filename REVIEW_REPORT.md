# stock-quant 代碼審查報告 — 2026-06-01

## 項目狀態總覽

| 指標 | 狀態 |
|------|------|
| 測試 | ✅ 693 用例（`tests/`，CI 全量 pytest） |
| 內置策略 | ✅ **30** 個模組（`src/core/strategies/`，`load_builtin_strategies`） |
| API 路由 | ✅ 30+ 路由模組、200+ 端點 |
| 前端 | ✅ Pro 工作站 `/app` + Legacy 入口 |
| Git 本地狀態 | ✅ `data/stock.db`、JWT/管理員秘密檔已自追蹤移除 |

---

## 本次修復記錄（2026-06-01）

### 🔴 P0 — 安全與版本控制

| # | 問題 | 修復 |
|---|------|------|
| 1 | **`data/stock.db`、秘密檔被 Git 追蹤** | 擴充 `.gitignore`；`git rm --cached` 移除 `stock.db`、`.jwt_secret`、`.admin_password`、`runtime_admin_controls.json` |
| 2 | **測試配額 429 導致 CI/本機不穩定** | 新增 `SQ_BILLING_QUOTA_ENFORCE`（測試預設 `false`）；`conftest` 提高限流上限 |

### 🟡 P1 — 測試修復

| 測試 | 原因 | 處理 |
|------|------|------|
| `test_auth_flow` | 免費方案每日回測配額用盡 | 測試環境關閉配額強制 |
| `test_crypto_api` | mock 路徑與 `CryptoService.get_realtime` 不一致 | 改 patch 服務方法 + 指定 `symbols` |
| `test_crypto_ws` | 大單閾值與測試資料不匹配 | 調整 `multiplier` |
| `test_local_kline` | 已改為 `download_one_auto` | mock 自動選源拉取 |
| `test_parallel_integration` | `get_task_stats` 合併歷史 task_log | 改為斷言本管線 3 個任務 ID |
| `test_smoke_api` | 主題包需 `assets_pro` | 煙霧測試先 checkout Pro |
| `test_template_strategy` | Backtrader RSI 零除 | 加長序列、波動價格、`runstandard=False` |

---

## 歷史問題狀態（2026-05-19 起）

| # | 問題 | 當前狀態 |
|---|------|----------|
| 1 | WebSocket 連接無上限 | ✅ 已加固（上限 + 清理） |
| 2 | task_manager 死鎖 | ✅ 已修復 |
| 3 | CORS 雲端需手動配置 | ⚠️ 部署時設 `SQ_CORS_ORIGINS` |
| 4 | 過擬合僅前端提示 | 🟡 後端未強制 Walk-Forward |
| 5 | 數據請求無隨機抖動 | ⚠️ 未變 |
| 6 | SQLite 併發 | ✅ WAL + busy_timeout + 線程本地連接 |
| 7 | AKShare 不穩定 | ✅ 多源降級 |
| 8 | JWT 密鑰 | ✅ 本地 `data/.jwt_secret`（已 gitignore） |

---

## 剩餘建議

### P1

- 生產環境保持 `SQ_BILLING_QUOTA_ENFORCE=true`（預設）
- WebSocket 生產強制 `SQ_WS_AUTH_REQUIRED=true`
- Optuna 優化預設附帶樣本外指標

### P2

- Render 冷啟動保活文檔
- 非 localhost 部署時 CORS 啟動警告

---

## 架構摘要

```
stock-quant/
├── main.py                 # CLI / serve 入口
├── src/
│   ├── api/                # FastAPI（路由按領域拆分）
│   ├── core/               # 回測、任務、數據、計費
│   │   └── strategies/     # 30 個內置策略模組
│   └── config.py           # pydantic-settings（SQ_ 前綴）
├── static/                 # Pro + Legacy 前端（原生 JS）
├── tests/                  # 66 個測試檔、693+ 用例
├── data/                   # 本地 DB 與秘密（不入庫）
└── docker-compose.yml
```

---

## 測試執行

```bash
# 全量（與 CI 一致）
SQ_DB_PATH=/tmp/test_stock.db SQ_REDIS_ENABLED=false SQ_DEMO_MODE=true \
  SQ_BILLING_QUOTA_ENFORCE=false python -m pytest tests/ -q

# 僅 schema
python -m pytest tests/test_database_schema.py -q
```
