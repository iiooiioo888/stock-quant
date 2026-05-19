# stock-quant 代碼審查報告 — 2026-05-19（更新）

## 項目狀態總覽

| 指標 | 狀態 |
|------|------|
| 測試 | ✅ 82/82 全部通過 (10.63s) |
| 策略 | ✅ 19 個內置策略全部可用 |
| API 路由 | ✅ 151 個端點 |
| 前端 Tab | ✅ 16 個功能頁面 |
| GitHub | ✅ 已同步，.qwen 已移除 |

---

## 本次修復記錄（2026-05-19）

### 🔴 P0 已修復

| # | 問題 | 修復內容 | 文件 |
|---|------|----------|------|
| 1 | **WebSocket 連接無上限** | `ConnectionManager` 增加 `MAX_CONNECTIONS=50`，超限拒絕；`disconnect()` 添加異常守護防止二次崩潰；`_cleanup_stale()` 批量清理死連接 | `src/api/app.py` |
| 2 | **task_manager 死鎖** | `update_task` 持鎖調用 `_evict_old_tasks` 再次加鎖導致死鎖 → 拆分 `_evict_old_tasks_inner()`（不加鎖）/ `_evict_old_tasks()`（加鎖） | `src/core/task_manager.py` |
| 3 | **BreakoutStrategy NoneType** | `self.highest[-1]` 和 `self.trailing_stop` 添加 `is not None` 守護 | `src/core/backtest.py` |
| 4 | **OBVStrategy 指標缺失** | backtrader 無內建 OBV 指標 → 自定義 `_OBV(bt.Indicator)` 類實現 | `src/core/backtest.py` |
| 5 | **測試 DB 路徑不兼容** | `/tmp/test_stock.db`（Windows 不兼容）→ `tempfile.gettempdir()` 跨平台路徑 + session-scoped `_init_test_db` fixture | `tests/conftest.py` |

### 🟡 P1 已修復

| # | 問題 | 修復內容 | 文件 |
|---|------|----------|------|
| 6 | **任務面板功能不全** | 重寫 tasks.js + 新增 task-common.js 共享模塊，支持列排序、展開詳情、刪除任務、載入指示器、空狀態引導 | `static/js/tasks.js`, `static/js/task-common.js` |
| 7 | **優化頁面缺乏過擬合警告** | OOS 對比圖上方添加紅/綠警告（IS 收益 >5% 且差距 >50% 觸發） | `static/js/optimize.js` |
| 8 | **浮動面板無法跳轉** | 「查看全部」按鈕跳轉 tasks Tab | `static/js/app.js` |
| 9 | **lifespan 啟動日誌** | 添加安全摘要日誌（JWT 狀態、CORS 配置、數據源數量） | `src/api/app.py` |

### 🟢 基礎設施

| # | 改進 | 說明 |
|---|------|------|
| 10 | **.qwen 從 GitHub 移除** | `git rm -r --cached .qwen` + 添加到 `.gitignore` |
| 11 | **新增 DELETE /api/tasks/{id}** | 支持前端刪除任務 |
| 12 | **新增 GET /api/tasks/{id}/full** | 支持前端獲取完整任務詳情 |

---

## 歷史問題狀態更新

| # | 問題 | 原狀態 | 當前狀態 | 說明 |
|---|------|--------|----------|------|
| 1 | WebSocket 認證可選 | 🔴 高 | 🟡 已加固 | 已增加連接上限 50 + 安全 disconnect + 批量清理，認證仍可選但攻擊面大幅縮小 |
| 2 | CORS 預設 localhost | 🟡 中 | ⚠️ 未變 | 雲端部署仍需手動設置 `SQ_CORS_ORIGINS` |
| 3 | 過擬合無強制校驗 | 🟡 中 | 🟡 已改善 | 前端已添加過擬合風險 UI 標註，但後端未強制 |
| 4 | 免費數據限流隨機化缺失 | 🟡 中 | ⚠️ 未變 | 固定間隔，無隨機化抖動 |
| 5 | Render 冷啟動 30 秒 | 🟡 中 | ⚠️ 未變 | README 無說明 |
| 6 | SQLite 併發瓶頸 | 🟡 中 | ✅ 已改善 | 已啟用 WAL + busy_timeout=5000 + thread-local 連接 + LRU 緩存 |
| 7 | AKShare 依賴不穩定 | 低風險 | ✅ 已有緩解 | 多源降級架構 |
| 8 | JWT 密鑰管理 | 已修復 | ✅ 保持 | 自動生成 + 持久化 |
| 9 | 日誌輪轉配置 | 已修復 | ✅ 保持 | RotatingFileHandler |
| 10 | CI/CD 配置 | 已修復 | ✅ 保持 | pytest + Docker + Render |

---

## 剩餘待修復項

### P1 — 建議盡快修復

| # | 問題 | 文件 | 建議 |
|---|------|------|------|
| 1 | **WebSocket 認證仍可選** | `src/api/app.py` | 生產環境強制 token 驗證，開發環境可通過 `SQ_WS_AUTH_REQUIRED=false` 關閉 |
| 2 | **數據請求隨機化抖動** | `src/core/realtime.py` | `throttle()` 加入 ±50% 隨機延遲 |
| 3 | **Optuna 優化強制 Walk-Forward** | `src/core/optimize.py` | 優化 API 默認返回樣本外表現 |

### P2 — 長期改進

| # | 問題 | 文件 | 建議 |
|---|------|------|------|
| 4 | **Render 冷啟動文檔** | `README.md` | 增加 UptimeRobot 保活方案說明 |
| 5 | **多數據源備援增強** | `src/core/realtime.py` | 增加 Tushare/Baostock 備選 |
| 6 | **CORS 雲端部署警告** | `src/config.py` | 非 localhost 部署時啟動警告 |

---

## 測試覆蓋範圍

| 模塊 | 測試數 | 覆蓋內容 |
|------|--------|----------|
| `test_api.py` | 14 | Health/Status/Config 端點、策略列表、Cache LRU |
| `test_backtest.py` | 11 | 合成數據、DualMA 回測、風險指標、權益曲線分析 |
| `test_portfolio.py` | 8 | 組合指標、最大回撤、相關性矩陣、風險貢獻、NAV 計算 |
| `test_strategies.py` | 49 | 19 個策略逐一測試、默認參數、Risk Pipeline、數據質量 |

---

## 架構摘要

```
stock-quant/
├── src/
│   ├── api/app.py          # FastAPI 主應用 (151 路由)
│   ├── core/
│   │   ├── backtest.py     # 回測引擎 (19 策略)
│   │   ├── portfolio.py    # 組合分析 (20+ 方法)
│   │   ├── optimize.py     # 參數優化 (Grid/Optuna)
│   │   ├── task_manager.py # 異步任務管理
│   │   ├── db.py           # SQLite (WAL + LRU)
│   │   └── ...
│   └── config.py           # Pydantic Settings
├── static/
│   ├── index.html          # SPA 主頁 (16 Tab)
│   ├── js/
│   │   ├── app.js          # 路由 + 生命週期
│   │   ├── api.js          # HTTP 客戶端
│   │   ├── task-common.js  # 任務共享模塊
│   │   ├── tasks.js        # 任務面板
│   │   └── ...             # 15 個 JS 文件
│   └── css/
├── tests/                  # 82 個測試
└── docker-compose.yml      # Docker 部署
```
