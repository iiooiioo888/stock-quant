# stock-quant — A股量化回測 + 實時盯盤預警

生產級量化系統，**以 Yahoo Finance 為主數據源**（A 股 / 美股 / 指數等），AKShare 為備選；SQLite 本地存儲，FastAPI Web 服務。

### 核心特性

- **Pro 工作站**（`/app`）：ECharts + 按頁懶載入模塊，統一量化工作台
- **資金與板塊**：側欄獨立「資金流」頁（市場資金、北向資金、板塊熱力圖），與總覽分離
- **異步任務佇列**：回測、優化、組合、Walk-Forward 等提交後立即返回，Web 端輪詢並在「任務中心」查看進度
- **並行加速**：可配置任務槽位、網格搜索進程/線程池；Windows 自動使用線程池避免 SQLite 多進程問題
- **結果緩存**：相同參數 + 相同 K 線版本命中緩存，秒級返回；支持本地 LRU 或 Redis（Docker 默認帶 Redis）
- **30+ 可回測策略**（`src/core/strategies/` 模塊化註冊）+ **策略庫目錄**（分類展示，含規劃項）+ 13+ 組合方法 + Optuna 貝葉斯優化
- **多股 / 多策略對比**：Pro 頁支持標的選擇器、多股收益走勢、全策略排行 / 散點 / 淨值曲線與 CSV/PNG 導出
- **前端性能優化**：智能數據預取、請求合併、虛擬滾動、Web Worker 異步處理、四層 TTL 緩存、數據壓縮傳輸
- **完整數據流管理**：優先級調度、並發控制、LRU 淘汰、性能監控儀表板

## 🚀 性能優化亮點

本次優化針對整個前端數據流進行了全面重構：

| 指標 | 優化前 | 優化後 | 改善幅度 |
|------|--------|--------|----------|
| 首屏加載 (FCP) | 2.5s | 1.2s | ↓ 52% |
| API 平均延遲 | 180ms | 95ms | ↓ 47% |
| 緩存命中率 | 25% | 65% | ↑ 160% |
| 長列表渲染 | 2500ms | 80ms | ↓ 97% |
| 記憶體峰值 | 256MB | 145MB | ↓ 43% |

**核心技術：**
- `DataCache`: 四層 TTL 緩存 + LRU 淘汰機制
- `RequestQueue`: 優先級調度 + 並發控制 (max 5)
- `SmartPrefetch`: 智能預取 + 批量預取
- `RequestBatcher`: 防抖合併 + 唯一請求
- `VirtualScroller`: 虛擬滾動渲染
- `DataWorker`: Web Worker 異步處理
- `DataCompressor`: Delta 編碼 + 二進制序列化
- `StreamMonitor`: 實時性能監控

## 🌐 在線演示

> 演示版部署在 Render.com (Free Plan)，首次訪問可能需要等待 30 秒冷啟動。

**冷啟動保活（可選）**：免費方案約 15 分鐘無流量會休眠。可用 [UptimeRobot](https://uptimerobot.com/) 每 **5–10 分鐘** GET 一次 https://你的域名/api/health（勿過於頻繁）。

**演示地址：** `https://stock-quant.onrender.com`

演示模式特性（`SQ_DEMO_MODE=true`）：
- 自動下載 5 只示範股票數據（平安銀行、貴州茅台、五糧液、中國平安、美的集團）
- 5 隻示範股票 + 多種示範策略（引擎內建 30+ 種可回測）
- **未登錄可讀**：儀表盤、數據中心、任務列表、信號等 GET 接口
- **寫入需登錄**：下載入庫、取消任務、回測提交、調度器變更等 POST/DELETE
- 參數優化、Walk-Forward、組合回測均可體驗
- 實時盯盤功能在非交易時段使用歷史數據模擬

## 快速開始

### 方式一：直接運行

```bash
cd stock-quant

# 安裝依賴
pip install -r requirements.txt

# 啟動 Web 服務
python main.py serve

# 訪問
#   http://localhost:8000/     落地頁
#   http://localhost:8000/app  Pro 工作站
```

### 方式二：Docker Compose（推薦）

```bash
cp .env.example .env
# 可選：編輯 .env 設置 SQ_JWT_SECRET、SQ_REDIS_PASSWORD 等

# 啟動應用 + Redis（緩存跨進程共享）
docker compose up -d --build

# 訪問 Web 儀表盤
# http://localhost:8000
```

**可選服務：**

```bash
# 加上 Nginx 反向代理（端口 80）
docker compose --profile proxy up -d

# 僅啟動應用、不用 Redis（僅容器內 LRU 緩存）
SQ_REDIS_ENABLED=false docker compose up -d app
```

**常用命令：**

```bash
docker compose logs -f app      # 查看日誌
docker compose ps             # 服務狀態
docker compose down           # 停止並移除容器
docker compose restart app    # 重啟應用
```

數據與日誌通過 volume 掛載到宿主機 `./data`、`./logs`，重建容器不丟數據。

## CLI 命令

```bash
# 下載歷史數據
python main.py download
python main.py download 000001 600519

# 回測
python main.py backtest 000001              # 默認雙均線
python main.py backtest 600519 macd         # MACD 策略
python main.py backtest 000001 all          # 所有策略對比

# 參數優化
python main.py optimize 000001              # 網格搜索所有策略
python main.py optimize 000001 dual_ma --method optuna --objective sharpe

# 組合回測
python main.py portfolio

# 實時盯盤
python main.py monitor

# 運維 SOP 健檢（部署前 / CI 同規則）
python main.py ops check
python main.py ops check --json
python main.py ops check --ci
python main.py ops probe --url http://127.0.0.1:8000/api/health/sop --ci
python scripts/probe_health_sop_url.py --url http://127.0.0.1:8000/api/health/sop --ci
python scripts/ops_audit.py --ci
python scripts/ops_audit.py --with-probe --ci   # 需先 main.py serve

# Walk-Forward 分析
python main.py walkforward 600519 dual_ma

# 股票篩選
python main.py screener

# 策略排行榜
python main.py leaderboard

# 定時任務（APScheduler）
python main.py scheduler list
python main.py scheduler setup
python main.py scheduler run incremental_update
```

## Web API

### 核心端點

| 端點 | 方法 | 說明 |
|------|------|------|
| `/api/health` | GET | 健康檢查 |
| `/api/health/detailed` | GET | 詳細健康狀態 |
| `/api/status` | GET | 系統狀態 |
| `/api/config` | GET | 當前配置 |

### 任務與緩存端點

| 端點 | 方法 | 說明 |
|------|------|------|
| `/api/tasks` | GET | 任務列表 + 佇列快照 + 統計 |
| `/api/tasks/queue` | GET | 執行佇列（當前/等待/最近完成） |
| `/api/tasks/{task_id}` | GET | 單任務詳情（含 result） |
| `/api/tasks/{task_id}/cancel` | POST | 取消任務 |
| `/api/tasks/{task_id}` | DELETE | 刪除已完成任務 |
| `/api/cache/stats` | GET | 緩存統計（LRU / Redis） |
| `/api/cache/clear` | POST | 清除計算緩存（可選 `?code=`） |

> 回測、優化、組合、Walk-Forward、自動優化等 POST 接口返回 `{ async: true, task_id }`，前端輪詢 `/api/tasks/{id}` 直至 `status=completed`。緩存命中時可能直接返回 `{ async: false, from_cache: true, result }`。

### 數據端點

| 端點 | 方法 | 說明 |
|------|------|------|
| `/api/stocks` | GET | 股票列表 |
| `/api/stocks/{code}/kline` | GET | K 線數據 |
| `/api/stocks/download` | POST | 下載歷史數據 |
| `/api/stocks/update` | POST | 增量更新數據 |
| `/api/stocks/compare` | POST | 多股收益率對比 |
| `/api/data/minutes` | GET | 分鐘K線（1m/5m/15m/30m/60m） |
| `/api/data/minutes/download` | POST | 下載分鐘數據 |
| `/api/data/sectors` | GET | 板塊行情（行業/概念） |
| `/api/data/sector/{name}/stocks` | GET | 板塊成分股 |
| `/api/data/capital-flow` | GET | 個股資金流向 |
| `/api/data/market-flow` | GET | 大盤資金流向 |
| `/api/data/north-flow` | GET | 北向資金 |
| `/api/data/dragon-tiger` | GET | 龍虎榜 |
| `/api/data/dragon-tiger/{code}/history` | GET | 龍虎榜歷史 |
| `/api/data/fundamentals` | GET | 基本面數據（PE/PB/ROE） |
| `/api/data/fundamentals/screen` | POST | 基本面篩選 |
| `/api/benchmark` | GET | 滬深300基準 |
| `/api/benchmark/compare` | POST | 基準對比 |
| `/api/dashboard/market-charts` | GET | 儀表盤/資金流圖表（`?days=5~60`，市場資金、北向、板塊熱力） |

### 回測端點

| 端點 | 方法 | 說明 |
|------|------|------|
| `/api/backtest` | POST | 單策略回測 |
| `/api/backtest/advanced` | POST | 進階回測（滑點/T+1/漲跌停） |
| `/api/backtest/multi` | POST | 全策略對比 |
| `/api/backtest/history` | GET | 回測歷史查詢 |
| `/api/backtest/compare` | GET | 歷史結果對比 |
| `/api/export/backtest/{id}` | GET | 導出回測結果（CSV/JSON） |
| `/api/export/trades` | GET | 導出交易明細 |

### 優化端點

| 端點 | 方法 | 說明 |
|------|------|------|
| `/api/optimize` | POST | 參數優化（網格/Optuna） |
| `/api/auto-optimize` | POST | 全自動參數尋優 |
| `/api/walkforward` | POST | Walk-Forward 分析 |
| `/api/heatmap` | POST | 策略參數敏感性熱力圖 |
| `/api/heatmap/params/{strategy}` | GET | 策略可優化參數 |

### 組合端點

| 端點 | 方法 | 說明 |
|------|------|------|
| `/api/portfolio` | POST | 基礎組合回測 |
| `/api/portfolio/presets` | GET | 預設組合列表 |
| `/api/portfolio/preset/{name}` | POST | 運行預設組合 |
| `/api/portfolio/frontier` | POST | 有效前沿分析 |
| `/api/portfolio/dynamic` | POST | 動態權重（滾動夏普） |
| `/api/portfolio/kelly` | POST | Kelly 公式最優倉位 |
| `/api/portfolio/degradation` | POST | 策略衰退檢測 |
| `/api/portfolio/arbitrate` | POST | 信號衝突仲裁 |
| `/api/portfolio/risk-parity` | POST | 風險平價組合 |
| `/api/portfolio/mvo` | POST | 均值-方差優化（Markowitz） |
| `/api/portfolio/vol-target` | POST | 波動率目標組合 |
| `/api/portfolio/max-diversification` | POST | 最大分散化組合 |
| `/api/portfolio/anti-correlation` | POST | 反相關組合 |
| `/api/portfolio/regime-switch` | POST | 市場狀態切換組合 |

### 信號端點

| 端點 | 方法 | 說明 |
|------|------|------|
| `/api/signals/current` | GET | 當前實時信號 |
| `/api/signals/history` | GET | 歷史信號查詢 |
| `/api/signals/strength` | GET | 信號強度評分 |

### 篩選端點

| 端點 | 方法 | 說明 |
|------|------|------|
| `/api/screener/stocks` | GET | 可篩選股票列表 |
| `/api/screener/screen` | POST | 條件篩選 |

### 策略管理端點

| 端點 | 方法 | 說明 |
|------|------|------|
| `/api/strategies/list` | GET | 策略列表 |
| `/api/strategies/create` | POST | 創建自定義策略 |
| `/api/strategies/upload` | POST | 上傳策略文件 |
| `/api/strategies/test` | POST | 測試策略 |
| `/api/strategies/leaderboard` | GET | 策略排行榜 |
| `/api/strategies/leaderboard/update` | POST | 更新排行榜 |

### 通知 & 調度端點

| 端點 | 方法 | 說明 |
|------|------|------|
| `/api/alerts` | GET | 預警歷史 |
| `/api/alerts/rules` | GET/PUT | 預警規則 CRUD |
| `/api/alerts/rules/{code}` | DELETE | 刪除預警規則 |
| `/api/watchlist/add` | POST | 加入監控列表 |
| `/api/notify/channels` | GET | 通知渠道狀態 |
| `/api/notify/test` | POST | 測試通知 |
| `/api/scheduler/jobs` | GET | 已註冊的調度任務 |
| `/api/scheduler/catalog` | GET | 任務目錄與啟用狀態 |
| `/api/scheduler/setup` | POST | 按 config 註冊默認任務 |
| `/api/scheduler/jobs/{id}/run` | POST | 立即執行一次 |
| `/api/scheduler/enable` | POST | 啟用默認任務套件 |
| `/api/scheduler/disable` | POST | 禁用全部定時任務 |

### 用戶系統端點

| 端點 | 方法 | 說明 |
|------|------|------|
| `/api/auth/register` | POST | 用戶註冊 |
| `/api/auth/login` | POST | 用戶登入 |
| `/api/auth/me` | GET | 當前用戶信息 |
| `/api/auth/settings` | PUT | 更新用戶設置 |
| `/api/user/watchlists` | GET/POST | 用戶自選列表 |
| `/api/user/alerts` | GET/POST | 用戶預警規則 |
| `/api/user/backtest-history` | GET | 用戶回測歷史 |
| `/api/admin/users` | GET | 管理員：用戶列表 |

### WebSocket

| 端點 | 說明 |
|------|------|
| `ws://host/ws` | 實時行情推送 + 信號推送 |

## 項目結構

```
stock-quant/
├── main.py                 # CLI + Web 入口
├── Dockerfile / docker-compose.yml
├── .env.example
├── requirements.txt
├── docs/
│   ├── manual/             # 項目說明書（架構、API、前端、部署等）
│   ├── runbooks/README.md  # 運維 SOP 總覽
│   └── MCP.md              # MCP Server 文檔
├── src/
│   ├── config.py
│   ├── api/
│   │   ├── app.py          # FastAPI 主應用 + 靜態頁路由
│   │   ├── routers/        # 分模塊路由（backtest、tasks、assets…）
│   │   ├── ws.py
│   │   └── demo.py
│   ├── core/
│   │   ├── database/       # Schema、遷移、連接、種子數據
│   │   ├── strategies/     # 30+ 策略（registry 註冊）
│   │   ├── backtest.py     # 回測引擎
│   │   ├── task_manager.py # 異步任務佇列
│   │   ├── optimize.py / portfolio.py / …
│   │   └── db.py           # 兼容層（轉發 database 包）
│   └── cli/                # 命令行子命令
├── static/
│   ├── home.html           # 落地頁（/）
│   ├── app.html            # Pro 工作站（/app）
│   ├── admin.html
│   ├── css/pro.css         # Pro 設計系統（表單、膠囊、面板）
│   ├── js/
│   │   ├── api.js          # 共享 API 客戶端（Token、任務輪詢、緩存）
│   │   ├── pro/
│   │   │   ├── app.js, module-loader.js, legacy-bridge.js
│   │   │   ├── ui/dashboard-components.js
│   │   │   └── modules/    # dashboard-pro, capitalflow-pro, backtest-pro, …
│   │   └── …               # 共享業務腳本（回測、優化、數據中心等）
├── data/stock.db
└── logs/
```

完整文件索引見 [docs/manual/15-文件索引.md](docs/manual/15-文件索引.md)。

## 內置策略

> 引擎已遷至 `src/core/strategies/` 獨立模塊（`register_strategy` 註冊）。下表為常用策略示例；完整列表以 `/api/strategies/list` 或 CLI `backtest … all` 為準。

| 策略 | 說明 | 核心參數 |
|------|------|----------|
| `dual_ma` | 雙均線金叉/死叉 | fast=5, slow=20 |
| `macd` | MACD 金叉/死叉 | fast=12, slow=26, signal=9 |
| `bollinger` | 布林帶突破 | period=20, devfactor=2.0 |
| `kdj` | KDJ 隨機指標 | period=9, overbought=80, oversold=20 |
| `rsi` | RSI 相對強弱指標 | period=14, overbought=70, oversold=30 |
| `grid` | 網格交易 | grid_pct=3%, position_pct=10% |
| `turtle` | 海龜趨勢跟蹤 | entry=20, exit=10, atr=20 |
| `dual_thrust` | DualThrust 日內突破 | period=4, k_up=0.5, k_down=0.5 |
| `momentum` | 動量 ROC 策略 | lookback=20, hold_period=5 |
| `mean_reversion` | 均值回歸 Z-score 策略 | period=20, entry_z=-2.0, exit_z=0.0 |
| `volume_price` | 量價齊升策略 | price_ma=20, volume_ma=20, ratio=2.0 |
| `breakout` | N 日高點突破策略 | period=60, atr_period=20, atr_mult=2.0 |
| `composite` | 多策略組合投票 | min_agreement=3 |
| `vwap` | VWAP 成交量加權策略 | period=20, deviation_pct=1.0 |
| `envelope` | 均線通道策略 | period=20, deviation_pct=5 |
| `parabolic_sar` | 拋物線 SAR 策略 | af_start=0.02, af_step=0.02, af_max=0.20 |
| `obv` | OBV 能量潮策略 | obv_ma=20, price_ma=20 |
| `bollinger_squeeze` | 布林帶收窄突破策略 | period=20, squeeze_threshold=0.03 |
| `adx_trend` | ADX 趨勢強度策略 | adx_period=14, adx_threshold=25 |
| `supertrend` | SuperTrend 趨勢 | period=10, multiplier=3 |
| `donchian` | 唐奇安通道突破 | period=20 |
| `cci` / `williams_r` | CCI / 威廉指標 | 見各模塊默認參數 |
| `ema_cross` / `triple_ma` | 均線系統 | 見各模塊默認參數 |
| … | 其餘見 `src/core/strategies/` | — |

### 進階回測參數

除基礎回測外，支持以下進階控制：

| 參數 | 說明 | 默認 |
|------|------|------|
| `slippage_pct` | 滑點百分比 | 0.0 |
| `enable_t1` | T+1 限制（A股買入次日才能賣） | true |
| `enable_limit` | 漲跌停限制（±10%/±20%） | true |
| `stop_loss_pct` | 止損百分比 | 0（禁用） |
| `take_profit_pct` | 止盈百分比 | 0（禁用） |
| `trailing_stop_pct` | 移動止損百分比 | 0（禁用） |
| `benchmark` | 是否對比滬深300 | false |

## 組合方法

| 方法 | 端點 | 說明 |
|------|------|------|
| 等權 | `/api/portfolio` | 等權重分配 |
| 預設組合 | `/api/portfolio/preset/{name}` | 配置文件預設 |
| 有效前沿 | `/api/portfolio/frontier` | Markowitz 有效前沿 |
| 動態權重 | `/api/portfolio/dynamic` | 滾動夏普自動調權 |
| Kelly | `/api/portfolio/kelly` | Kelly 公式最優倉位 |
| 衰退檢測 | `/api/portfolio/degradation` | 連續跑輸基準降權 |
| 信號仲裁 | `/api/portfolio/arbitrate` | 多策略矛盾信號投票 |
| 風險平價 | `/api/portfolio/risk-parity` | 每策略風險貢獻相等 |
| 均值-方差 | `/api/portfolio/mvo` | Markowitz 最優權重 |
| 波動率目標 | `/api/portfolio/vol-target` | 已實現波動率動態調倉 |
| 最大分散化 | `/api/portfolio/max-diversification` | 最大化分散化比率 |
| 反相關 | `/api/portfolio/anti-correlation` | 最小化策略間相關性 |
| 狀態切換 | `/api/portfolio/regime-switch` | 趨勢/波動狀態動態調權 |

## 風險指標

回測結果包含以下風險指標：

| 指標 | 說明 |
|------|------|
| VaR 95% | 95% 置信度的在險價值 |
| CVaR 95% | 條件風險價值（VaR 之外的平均損失） |
| Sortino Ratio | 下行風險調整收益 |
| Calmar Ratio | 收益/最大回撤 |
| 年化波動率 | 年化標準差 |
| 月勝率 | 盈利月佔比 |
| 盈虧比 | 平均盈利/平均虧損 |
| 回撤恢復天數 | 最大回撤恢復所需天數 |
| Alpha | 相對基準超額收益 |
| Beta | 相對基準系統性風險 |
| 信息比率 | 超額收益/跟蹤誤差 |
| 跟蹤誤差 | 超額收益標準差 |

## 配置

所有配置項支持環境變量覆蓋（`SQ_` 前綴）。複製模板後編輯：

```bash
cp .env.example .env
```

### 常用環境變量

| 變量 | 說明 | 默認 |
|------|------|------|
| `SQ_WEB_PORT` | Web 端口 | `8000` |
| `SQ_BACKTEST_CASH` | 回測初始資金 | `100000` |
| `SQ_CACHE_ENABLED` | 啟用計算結果緩存 | `true` |
| `SQ_CACHE_BACKTEST_TTL` | 回測緩存秒數 | `3600` |
| `SQ_CACHE_OPTIMIZE_TTL` | 優化緩存秒數 | `7200` |
| `SQ_REDIS_ENABLED` | 使用 Redis（否則僅 LRU） | `false`（本地）/ `true`（Compose） |
| `SQ_REDIS_URL` | Redis 連接串 | — |
| `SQ_TASK_MAX_WORKERS` | **同時運行**的 API 異步任務槽（`0`=自動） | `0` |
| `SQ_MULTI_STRATEGY_WORKERS` | 單任務內多策略/對比線程數 | `4` |
| `SQ_OPTIMIZE_ALL_PARALLEL` | 全策略優化是否跨策略並行 | `false` |
| `SQ_TASK_PARALLEL_GRID` | 單任務內網格搜索是否並行 | `true` |
| `SQ_JWT_SECRET` | JWT 密鑰（生產必設） | 自動生成 |
| `SQ_CORS_ORIGINS` | 允許的前端來源 | localhost |
| `SQ_REDIS_PASSWORD` | Redis 密碼（Compose） | 見 `.env.example` |
| `NGINX_HTTP_PORT` | Nginx 對外端口 | `80` |

```bash
# 環境變量示例（Linux / macOS）
export SQ_WEB_PORT=8080
export SQ_BACKTEST_CASH=200000
export SQ_CACHE_ENABLED=true
export SQ_TASK_MAX_WORKERS=2
export SQ_OPTIMIZE_ALL_PARALLEL=false
```

下載或增量更新 K 線後，相關計算緩存會自動失效；也可手動 `POST /api/cache/clear`。

## 數據來源

| 類型 | 主源 | 備選 |
|------|------|------|
| A 股日 K | **Yahoo Finance**（`600519.SS` / `000001.SZ`） | 東財 AKShare、新浪、網易、騰訊、HTTP 直連 |
| A 股實時 | **Yahoo Finance** | 東財盤口、新浪、騰訊 |
| 滬深300 基準 | **Yahoo**（`000300.SS`） | AKShare 指數 |
| 美股/港股/指數/ETF | **Yahoo Finance** | 新浪全球、Twelve Data |
| 加密貨幣 | Binance | CoinGecko、CoinCap、Twelve Data（`/api/crypto/*` 獨立子系統） |
| 外匯 | Frankfurter / Yahoo | 新浪 |

- 板塊、資金流向、龍虎榜、基本面等仍使用 AKShare（東方財富）
- Yahoo 免費無需 API Key；若遇 `429` 會自動重試並降級到 AKShare
- 分鐘 K 線仍使用東財接口（Yahoo 日線為主）

## 擴展

- **添加新策略**: 在 `src/core/strategies/` 新建模塊，使用 `@register_strategy` 註冊（見 `registry.py`）
- **自定義策略上傳**: 通過 `/api/strategies/upload` 上傳 .py 文件，繼承 `StrategyBase`
- **添加通知渠道**: 修改 `src/core/alerts.py` 的 `dispatch()` 方法
- **添加新股票**: 修改 `src/config.py` 的 `watchlist` 和 `alert_rules`
- **自定義優化空間**: 修改 `src/core/optimize.py` 的 `PARAM_GRIDS` 和 `PARAM_RANGES`

## 文檔

| 文檔 | 說明 |
|------|------|
| [NEXT_PROMPT.md](NEXT_PROMPT.md) | 下一輪優化上下文（給 Agent / 協作者） |
| [docs/runbooks/README.md](docs/runbooks/README.md) | 運維 SOP 總覽（決策樹、日常健檢、事故對照） |
| [docs/PRODUCTION_READINESS.md](docs/PRODUCTION_READINESS.md) | 生產就緒路線圖（安全/效能/測試/監控對照與優先級） |
| [docs/manual/README.md](docs/manual/README.md) | 說明書目錄（概覽、快速開始、架構、API、前端、部署、測試） |
| [docs/manual/06-前端說明.md](docs/manual/06-前端說明.md) | Pro 工作站路由與模塊 |
| [docs/manual/13-架構設計.md](docs/manual/13-架構設計.md) | 架構與設計決策 |
| [docs/MCP.md](docs/MCP.md) | MCP Agent 接入 |

## 前端（Pro 工作站 `/app`）

深色量化工作台（`static/app.html` + `static/css/pro.css`），ECharts 圖表、Cmd+K 命令面板、統一設計系統（表單 / 膠囊 / 面板）。核心頁面通過 `module-loader.js` 懶載入 `*-pro.js`；組合、優化、Walk-Forward、熱力圖、數據中心等頁在 Pro 殼內以 `legacy-mount` 內嵌掛載（`legacy-bridge.js`），對外僅暴露 `/app` 一個工作台入口。

### 🚀 前端性能優化

新增 `static/js/data-stream.js` 完整數據流管理模塊，提供：

| 模塊 | 功能 | 性能提升 |
|------|------|----------|
| **DataCache** | 四層 TTL 緩存 + LRU 淘汰 | 緩存命中率 ↑160% |
| **RequestQueue** | 優先級調度 + 並發控制 (max 5) | 請求延遲 ↓47% |
| **SmartPrefetch** | 智能預取 + 批量預取 | 首屏加載 ↓52% |
| **RequestBatcher** | 防抖合併 + 唯一請求 | API 請求數 ↓60% |
| **VirtualScroller** | 虛擬滾動渲染 | 長列表渲染 ↓97% |
| **DataWorker** | Web Worker 異步處理 | 主線程阻塞 ↓80% |
| **DataCompressor** | Delta 編碼 + 二進制序列化 | 傳輸體積 ↓60% |
| **StreamMonitor** | 實時性能監控 | - |

**使用示例：**
```javascript
// 初始化
DataStream.init();

// 預取數據
await DataStream.prefetch('dashboard', () => fetch('/api/dashboard'), 9);

// 虛擬滾動
VirtualScroller.init('stockList', {
  itemHeight: 48,
  getTotalCount: () => stocks.length,
  renderItem: (i) => createStockRow(stocks[i]),
});

// 性能報告
console.log(DataStream.getPerformanceReport());
```

詳細文檔參見 [DATASTREAM_OPTIMIZATION_REPORT.md](DATASTREAM_OPTIMIZATION_REPORT.md)。

| 側欄 | 模塊 | 功能摘要 |
|------|------|----------|
| 總覽 | `dashboard-pro.js` | 全球掛牌、KPI、多幣種資產結算（不含資金流圖表） |
| **資金流** | `capitalflow-pro.js` | 市場資金流向、北向資金、板塊熱力（`GET /api/dashboard/market-charts`） |
| 策略庫 | `strategy-catalog.js` | 分類、搜尋、方案/狀態篩選、策略卡片 |
| 回測 | `backtest-pro.js` + `backtest-symbol-picker.js` | 標的選擇、進階參數、異步回測、導出 |
| **對比** | `compare-pro.js` | 多策略（排行/散點/淨值 Top5）與多股票（區間收益）；PNG/CSV |
| 任務中心 | `tasks-pro.js` | 佇列、統計、列表、詳情、批量操作 |
| 資產庫 | `assets-pro.js` | 多幣種持倉與結算 |
| 自選 / 掃描 / 預警 / 回測歷史 / 設定 / AI | `*-pro.js` | 各業務頁 |
| 組合 / 優化 / WF / 熱力圖 / 信號 / 數據 / … | `legacy-mount` | Pro 內嵌掛載（逐步遷至 `*-pro.js`） |

**UI 約定**：全站隱藏滾動條、由 `.main` 單容器縱向滾動（見 `.cursor/rules/ui-no-scrollbar.mdc`）。

WebSocket（`/ws`）在登錄後推送任務狀態；未登錄時不建立連線（避免 403 刷屏）。

### 入口一覽

| URL | 頁面 |
|-----|------|
| `/` | 落地頁 `home.html` |
| `/app` | Pro 工作站 |
| `/admin` | 管理後台 |

## 部署

### Render.com（推薦，免費）

1. Fork 本倉庫到你的 GitHub
2. 在 [Render](https://render.com) 註冊，連接 GitHub
3. New → Blueprint → 選擇 fork 的倉庫
4. Render 自動讀取 `render.yaml` 創建服務
5. 部署完成後獲得 `https://xxx.onrender.com` 地址

> 需要自動部署：在 GitHub Repo → Settings → Secrets 添加 `RENDER_SERVICE_ID` 和 `RENDER_API_KEY`

### Docker 單容器

```bash
docker build -t stock-quant .
docker run -p 8000:8000 \
  -v "$(pwd)/data:/app/data" \
  -v "$(pwd)/logs:/app/logs" \
  -e SQ_DB_PATH=/app/data/stock.db \
  -e SQ_CACHE_ENABLED=true \
  -e SQ_REDIS_ENABLED=false \
  stock-quant
```

### Docker Compose 服務說明

| 服務 | 說明 | 默認 |
|------|------|------|
| `app` | FastAPI + 內建前端 | 啟動，端口 `8000` |
| `redis` | 計算緩存、可選行情緩存 | 啟動，僅容器網絡內訪問 |
| `nginx` | 反向代理 | 需 `--profile proxy`，端口 `80` |

Compose 會將 `SQ_REDIS_URL` 指向 `redis` 服務，並掛載 `./data`、`./logs`。

### 股票庫（按市值前 20000）

從 **A 股 + 港股 + 美股** 實時行情拉取基本資料（代碼、名稱、市值、PE/PB 等），按總市值排序後入庫 `stock_universe` 表（默認前 20000，可配置 `SQ_STOCK_UNIVERSE_MAX_COUNT`）。

```bash
# CLI 同步（需可訪問東財/AKShare）
python main.py stock-universe sync
python main.py stock-universe stats
python main.py stock-universe list --market a_share --limit 20

# API（同步需登錄）
# GET  /api/stock-universe/stats
# GET  /api/stock-universe?market=a_share&limit=50&offset=0
# POST /api/stock-universe/sync?max_count=20000
```

說明：滬深 A 股上市約 5000+，要湊滿 20000 需依賴港股/美股數據；若外網失敗會降級為僅 A 股代碼表（無市值）。

### 對外接口檢查

Web 側欄 **接口檢查** Tab，或 API：

- `GET /api/external/check/registry` — 數據源註冊表（無外網）
- `GET /api/external/check` — 最近一次全量探測結果
- `POST /api/external/check/run` — 立即探測（需登錄）


### MCP（全項目 Agent 接入）

```bash
pip install -r requirements-mcp.txt
python -m src.integrations.mcp.server
```

- 文檔：[docs/MCP.md](docs/MCP.md)
- 核心 tools：`sq_health`、`sq_list_strategies`、`sq_data_sources` 等

### 測試

```bash
# CI 與日常開發（推薦）
SQ_DEMO_MODE=true pytest tests/ -q
# 當前約 640 用例（59 個 test_*.py）

# 手動全量 API 煙霧（需本機已啟動服務並設置 SQ_DEMO_ADMIN_PASSWORD）
./test_all.sh
```

| 類型 | 代表文件 |
|------|----------|
| 煙霧 / API | `test_smoke_api.py`, `test_api.py` |
| 認證 | `test_auth_flow.py`, `test_auth_write_protection.py` |
| 回測 / 策略 | `test_backtest.py`, `test_strategies.py` |
| 組合 / 資產 | `test_portfolio.py`, `test_portfolio_ledger.py`, `test_portfolio_currency.py` |
| 數據 / 儀表盤 | `test_dashboard_market.py`, `test_capital_flow_aggregate.py`, `test_data_center_api.py` |
| UI | `test_ui_playwright_smoke.py`, `test_static_onclick.py` |
| 穩定性 | `test_stability_*.py` |

`tests/test_smoke_api.py` 覆蓋核心 GET；`test_auth_write_protection.py` 驗證演示模式寫入保護。

可選瀏覽器煙霧（需本機已 `python main.py serve`）：

```bash
pip install -r requirements-dev.txt
playwright install chromium
pytest tests/test_ui_playwright_smoke.py -v
```

### 生產部署必改配置

部署到雲端時，以下配置項**必須修改**，否則存在安全風險：

| 環境變量 | 說明 | 演示 (Render) | 私有生產 |
|----------|------|---------------|----------|
| `SQ_DEMO_MODE` | 演示：GET 讀開放、寫需登錄 | `true` | **`false`** |
| `SQ_CORS_ORIGINS` | 允許的前端域名（不要用 `*`） | 實際域名 | 實際域名 |
| `SQ_JWT_SECRET` | JWT 簽名密鑰（至少 32 字符） | 建議設置 | **必設** |
| `SQ_WS_AUTH_REQUIRED` | WebSocket 強制認證 | 可 `false` | **`true`** |
| `SQ_DEMO_ADMIN_PASSWORD` | 管理員密碼 | **必設強密碼** | 登入後改密碼 |
| `SQ_REDIS_PASSWORD` | Docker Redis 密碼 | 與 `SQ_REDIS_URL` 一致 | 同左 |
| `SQ_CACHE_ENABLED` | 計算結果緩存 | `true` | `true` |

啟動時若為「公開演示模式」（`SQ_DEMO_MODE=true` 且 CORS 含公網域名），日誌會輸出安全警告。

```bash
# 示例：私有生產環境啟動
export SQ_DEMO_MODE=false
export SQ_CORS_ORIGINS=https://your-domain.com
export SQ_JWT_SECRET=$(openssl rand -hex 32)
export SQ_WS_AUTH_REQUIRED=true
python main.py serve
```

### Render 冷啟動說明與保活方案

Render 免費版在 15 分鐘無請求後會休眠，首次訪問需等待約 30 秒冷啟動。

**推薦保活方案（UptimeRobot）：**

1. 註冊 [UptimeRobot](https://uptimerobot.com/) 免費賬戶
2. 添加新的 HTTP Monitor：
   - **Friendly Name**: `stock-quant keepalive`
   - **URL to monitor**: `https://stock-quant.onrender.com/api/health`
   - **Monitoring Interval**: 5 minutes (免費版最短間隔)
3. 保存後系統會每 5 分鐘自動發送請求，防止服務休眠

**注意事項：**
- UptimeRobot 免費版提供 50 個 monitors，足夠使用
- 此方法僅適合回測演示，實時盯盤建議使用付費服務或自建服務器
- 生產環境建議使用 Docker Compose 部署到 VPS 或本地服務器

**替代方案：**
- GitHub Actions 定時任務（每 10 分鐘 curl 一次）
- 手機快捷指令/自動化定時訪問
- 購買 Render 付費計劃（$7/月起，無冷啟動）
