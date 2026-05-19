# stock-quant 代碼審查報告 — 2026-05-18

## 逐項驗證結果

### ✅ 已驗證為問題（需要修復）

| # | 問題 | 嚴重度 | 文件 | 狀態 |
|---|------|--------|------|------|
| 1 | **WebSocket 認證可選** | 🔴 高 | `app.py:websocket_endpoint` | 確認 — 無 token 時允許連接，生產環境可被繞過 |
| 2 | **CORS 預設 localhost** | 🟡 中 | `config.py` / `.env.example` | 確認 — 雲端部署需手動修改 |
| 3 | **過擬合無強制校驗** | 🟡 中 | `optimize.py` | 確認 — Walk-Forward 已實現但未強制使用 |
| 4 | **免費數據限流隨機化缺失** | 🟡 中 | `realtime.py` / `data_sources.py` | 確認 — 固定間隔，無隨機化抖動 |
| 5 | **Render 冷啟動 30 秒** | 🟡 中 | 部署層面 | 確認 — README 無說明 |
| 6 | **SQLite 併發瓶頸** | 🟡 中 | `db.py` | 部分確認 — 已啟用 WAL 模式，但無連接池 |

### ⚠️ 已驗證但風險較低 / 已有緩解

| # | 問題 | 說明 |
|---|------|------|
| 7 | **AKShare 依賴不穩定** | **已有緩解** — `data_sources.py` 已建立多源降級架構（東財→新浪→網易→騰訊→HTTP直連），`realtime.py` 有 4 個備選源。但仍依賴 AKShare 作為主要入口 |
| 8 | **JWT 密鑰管理** | **已修復** — 代碼自動生成隨機密鑰並持久化到 `data/.jwt_secret`（chmod 600），不會使用硬編碼默認值 |
| 9 | **日誌輪轉配置** | **已修復** — `logger.py` 已配置 `RotatingFileHandler(maxBytes=10MB, backupCount=5)` |
| 10 | **CI/CD 配置** | **已修復** — `.github/workflows/ci.yml` 已有 pytest + Docker 構建，`deploy.yml` 已有 Render 自動部署 |
| 11 | **前視偏差** | **未發現** — Backtrader 的 `next()` 方法按時間順序逐 bar 執行，策略只訪問 `self.data[0]`（當前）和 `self.data[-1]`（前一個），無偷看未來數據 |

---

## 優先級修復計劃

### P0 — 生產上線前必須修復

#### 1. WebSocket 強制認證
**文件**: `src/api/app.py` — `websocket_endpoint()`
**問題**: 無 token 時允許連接，任何人可監聽實時行情和信號
**修復**: 生產環境強制 token 驗證，開發環境可通過環境變量關閉

#### 2. CORS 安全加固
**文件**: `src/config.py` / `.env.example`
**問題**: 默認允許 localhost，部署到雲端時需手動修改
**修復**: 啟動時檢查 CORS 配置，非 localhost 部署時警告；README 增加雲端部署檢查清單

### P1 — 建議盡快修復

#### 3. Optuna 優化強制 Walk-Forward
**文件**: `src/core/optimize.py`
**問題**: 用戶可直接跑 Optuna 網格搜索而跳過樣本外驗證，導致過擬合
**修復**: 優化 API 默認返回 Walk-Forward 樣本外表現，結果頁標注「樣本內 vs 樣本外」

#### 4. 數據請求隨機化抖動
**文件**: `src/core/realtime.py` / `src/core/data_sources.py`
**問題**: 固定請求間隔容易觸發限流
**修復**: 在 `throttle()` 和 `fetch_one_realtime()` 中加入隨機抖動（±50%）

#### 5. SQLite 連接池 + 更好的併發處理
**文件**: `src/core/db.py`
**問題**: 每次請求都 `connect()` + `close()`，高併發時效率低
**修復**: 增加簡單連接池或使用 `check_same_thread=False` + 線程本地連接

### P2 — 長期改進

#### 6. Render 冷啟動文檔
**文件**: `README.md`
**問題**: 免費版休眠後首次訪問需等待 30 秒
**修復**: README 增加「生產部署建議」章節，說明 UptimeRobot 保活方案

#### 7. 多數據源備援增強
**文件**: `src/core/realtime.py`
**問題**: AKShare 仍為主要入口，接口變更時需手動更新
**修復**: 增加 Tushare/Baostock 作為備選，配置化切換數據源優先級
