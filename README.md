# stock-quant — A股量化回測 + 實時盯盤預警

生產級量化系統，基於 AKShare 數據源，SQLite 本地存儲，FastAPI Web 服務。

## 🌐 在線演示

> 演示版部署在 Render.com (Free Plan)，首次訪問可能需要等待 30 秒冷啟動。

**演示地址：** `https://stock-quant.onrender.com`

演示模式特性：
- 自動下載 5 只示範股票數據（平安銀行、貴州茅台、五糧液、中國平安、美的集團）
- 包含 13 種策略的完整回測功能
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

# 訪問 http://localhost:8000
```

### 方式二：Docker

```bash
cp .env.example .env
docker compose up -d

# 訪問 http://localhost:8000
```

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

# Walk-Forward 分析
python main.py walkforward 600519 dual_ma

# 股票篩選
python main.py screener

# 策略排行榜
python main.py leaderboard
```

## Web API

### 核心端點

| 端點 | 方法 | 說明 |
|------|------|------|
| `/api/health` | GET | 健康檢查 |
| `/api/health/detailed` | GET | 詳細健康狀態 |
| `/api/status` | GET | 系統狀態 |
| `/api/config` | GET | 當前配置 |

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
| `/api/scheduler/jobs` | GET | 調度任務列表 |
| `/api/scheduler/enable` | POST | 啟用定時任務 |
| `/api/scheduler/disable` | POST | 禁用定時任務 |

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
├── Dockerfile              # Docker 鏡像
├── docker-compose.yml      # Docker Compose
├── .env.example            # 環境變量模板
├── requirements.txt
├── src/
│   ├── config.py           # 配置管理（支持環境變量 + .env）
│   ├── api/
│   │   └── app.py          # FastAPI 應用 + 70+ 端點 + 內建儀表盤
│   ├── core/
│   │   ├── db.py           # 數據庫操作（SQLite + LRU 緩存）
│   │   ├── history.py      # 歷史數據下載 + 增量更新
│   │   ├── realtime.py     # 實時行情
│   │   ├── alerts.py       # 預警引擎 + 多渠道通知
│   │   ├── backtest.py     # 回測引擎（8 種策略 + 滑點/T+1/漲跌停）
│   │   ├── optimize.py     # 參數優化（網格 + Optuna）
│   │   ├── portfolio.py    # 11 種組合方法 + 相關性 + 有效前沿
│   │   ├── walkforward.py  # Walk-Forward 分析
│   │   ├── auto_optimize.py# 全自動參數尋優
│   │   ├── heatmap.py      # 參數敏感性熱力圖
│   │   ├── screener.py     # 股票篩選器
│   │   ├── benchmark.py    # 滬深300基準對比
│   │   ├── export.py       # CSV/JSON 導出
│   │   ├── signals.py      # 實時信號引擎
│   │   ├── scheduler.py    # APScheduler 定時任務
│   │   ├── report.py       # 每日策略報告
│   │   ├── auth.py         # JWT 用戶認證
│   │   ├── strategy_base.py# 策略基類
│   │   ├── leaderboard.py  # 策略排行榜
│   │   ├── sector.py       # 板塊數據
│   │   ├── capital_flow.py # 資金流向
│   │   ├── dragon_tiger.py # 龍虎榜
│   │   ├── fundamental.py  # 基本面數據
│   │   └── cache.py        # 進階緩存
│   ├── models/
│   │   └── schemas.py      # Pydantic 數據模型
│   └── utils/
│       └── logger.py       # 日誌系統（輪轉 + 分級）
├── static/
│   ├── index.html          # 內建儀表盤（13 Tab）
│   ├── css/style.css       # 暗色/亮色主題
│   ├── js/
│   │   ├── app.js          # 主應用 + Tab 路由
│   │   ├── api.js          # API 客戶端
│   │   ├── charts.js       # 圖表封裝
│   │   ├── dashboard.js    # 儀表盤
│   │   ├── backtest.js     # 回測 Tab
│   │   ├── optimize.js     # 優化 Tab
│   │   ├── portfolio.js    # 組合 Tab
│   │   ├── signals.js      # 信號 Tab
│   │   ├── screener.js     # 篩選器 Tab
│   │   ├── heatmap.js      # 熱力圖 Tab
│   │   ├── data.js         # 數據中心 Tab
│   │   └── utils.js        # 工具函數
│   └── lib/                # CDN 備份
├── data/
│   └── stock.db            # SQLite 數據庫
└── logs/
    ├── app.log             # 應用日誌
    └── error.log           # 錯誤日誌
```

## 內置策略

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

所有配置項支持環境變量覆蓋（`SQ_` 前綴）：

```bash
# 環境變量示例
export SQ_WEB_PORT=8080
export SQ_BACKTEST_CASH=200000
export SQ_WATCHLIST='["000001","600519"]'
```

或使用 `.env` 文件：

```bash
cp .env.example .env
# 編輯 .env 文件
```

## 數據來源

- 歷史日K: 東方財富（AKShare `stock_zh_a_hist`）+ 新浪備選
- 實時行情: 東方財富（AKShare `stock_bid_ask_em`）
- 板塊數據: 東方財富行業/概念板塊
- 資金流向: 東方財富主力資金
- 北向資金: 東方財富滬深港通
- 龍虎榜: 東方財富龍虎榜
- 基本面: 東方財富 PE/PB/ROE
- 均為免費公開數據，高頻調用可能被限流

## 擴展

- **添加新策略**: 在 `src/core/backtest.py` 中繼承 `bt.Strategy`，註冊到 `STRATEGIES`
- **自定義策略上傳**: 通過 `/api/strategies/upload` 上傳 .py 文件，繼承 `StrategyBase`
- **添加通知渠道**: 修改 `src/core/alerts.py` 的 `dispatch()` 方法
- **添加新股票**: 修改 `src/config.py` 的 `watchlist` 和 `alert_rules`
- **自定義優化空間**: 修改 `src/core/optimize.py` 的 `PARAM_GRIDS` 和 `PARAM_RANGES`

## 前端

內建暗色/亮色主題儀表盤，包含 13 個 Tab：

1. **儀表盤** — 系統概覽 + 監控列表
2. **回測** — 單策略/全策略對比 + K線 + 交易明細
3. **優化** — 參數優化 + 全自動尋優
4. **組合** — 11 種組合方法 + 預設組合 + 有效前沿
5. **對比** — 多股收益率對比
6. **歷史** — 回測歷史查詢
7. **Walk-Forward** — 滾動窗口過擬合檢測
8. **熱力圖** — 策略參數敏感性 Canvas 渲染
9. **篩選器** — 多條件股票篩選
10. **信號** — 實時/歷史/強度信號
11. **數據** — 板塊/資金流向/龍虎榜/基本面
12. **報告** — 每日策略報告 + 定時任務
13. **預警** — 通知渠道 + 預警歷史

## 部署

### Render.com（推薦，免費）

1. Fork 本倉庫到你的 GitHub
2. 在 [Render](https://render.com) 註冊，連接 GitHub
3. New → Blueprint → 選擇 fork 的倉庫
4. Render 自動讀取 `render.yaml` 創建服務
5. 部署完成後獲得 `https://xxx.onrender.com` 地址

> 需要自動部署：在 GitHub Repo → Settings → Secrets 添加 `RENDER_SERVICE_ID` 和 `RENDER_API_KEY`

### Docker

```bash
docker build -t stock-quant .
docker run -p 8000:8000 -e SQ_DEMO_MODE=true stock-quant
```

### docker-compose

```bash
docker-compose up -d
```

### 生產部署必改配置

部署到雲端時，以下配置項**必須修改**，否則存在安全風險：

| 環境變量 | 說明 | 示例 |
|----------|------|------|
| `SQ_CORS_ORIGINS` | 允許的前端域名（不要用 `*`） | `https://your-domain.com` |
| `SQ_JWT_SECRET` | JWT 簽名密鑰（至少 32 字符） | `openssl rand -hex 32` |
| `SQ_WS_AUTH_REQUIRED` | WebSocket 強制認證（默認 true） | `true` |
| `SQ_DEMO_ADMIN_PASSWORD` | 管理員密碼（不設則隨機生成） | 自定義強密碼 |

```bash
# 示例：生產環境啟動
export SQ_CORS_ORIGINS=https://your-domain.com
export SQ_JWT_SECRET=$(openssl rand -hex 32)
export SQ_WS_AUTH_REQUIRED=true
python main.py serve
```

### Render 冷啟動說明

Render 免費版在 15 分鐘無請求後會休眠，首次訪問需等待約 30 秒冷啟動。

**解決方案：**
- 使用 [UptimeRobot](https://uptimerobot.com/) 每 5 分鐘 ping `/api/health` 保持活躍
- 或在 README 中說明「僅適合回測演示，實時盯盤建議自建服務器」
