# 幣安 WebSocket 串流整合文檔

## 架構概覽

```
🌐 Binance WebSocket Streams (wss://stream.binance.com:9443)
        ↓
🔌 BinanceStreamClient (異步 + 重連 + 心跳 + 數據驗證)
        ↓
📊 CryptoStreamManager (多交易對 + K 線聚合 + 快照緩存)
        ↓ ↓ ↓
   ┌────┼────────────┐
   ↓    ↓            ↓
🧹數據清洗  🧠技術指標引擎   🔔告警引擎
   ↓         ↓              ↓
💾持久化    📈信號產生      📡推送通知
(SQLite)    ↓              (WS / Console)
   ↓     📊 API 輸出      ↓
   └──→ REST + WebSocket ←─┘
```

## 模塊清單

| 文件 | 職責 |
|------|------|
| `src/core/crypto/ws_client.py` | 幣安 WebSocket 異步客戶端（自動重連、心跳、驗證） |
| `src/core/crypto/stream_manager.py` | 串流管理器（快照、K 線聚合、trade 窗口） |
| `src/core/crypto/indicators.py` | 30+ 技術指標（RSI/MACD/BB/EMA/ATR/Supertrend/Ichimoku/OBV/VWAP/MFI...） |
| `src/core/crypto/microstructure.py` | 微結構分析（買賣壓力/大單/盤口/波動率） |
| `src/core/crypto/alerts.py` | 多維度告警引擎（8 類規則 + 冷卻 + 歷史） |
| `src/core/crypto/service.py` | 統一服務層（WS 優先 + REST 降級） |

## API 端點

### 原有端點（增強）

| 端點 | 說明 |
|------|------|
| `GET /api/crypto/symbols` | 支持的交易對 |
| `GET /api/crypto/realtime` | 實時行情（WS 快照優先） |
| `GET /api/crypto/kline?interval=1m` | K 線（含 WS 實時聚合） |

### 新增端點

| 端點 | 說明 |
|------|------|
| `GET /api/crypto/indicators?symbol=BTCUSDT&days=90` | 完整技術指標 |
| `GET /api/crypto/microstructure?symbol=BTCUSDT` | 微結構分析 |
| `GET /api/crypto/alerts` | 活躍告警 |
| `GET /api/crypto/alert-history?symbol=BTCUSDT&limit=50` | 告警歷史 |
| `GET /api/crypto/alert-rules?symbol=BTCUSDT` | 告警規則 |
| `GET /api/crypto/ws/status` | WS 連接狀態 |
| `POST /api/crypto/ws/subscribe` | 動態訂閱 `{"symbols": ["DOGEUSDT"]}` |
| `POST /api/crypto/ws/unsubscribe` | 取消訂閱 |
| `POST /api/crypto/alerts/config` | 更新告警閾值 |

## 配置項

所有配置均可通過環境變量（前綴 `SQ_`）或 `.env` 文件設置。

### WebSocket 串流

| 配置 | 默認值 | 說明 |
|------|--------|------|
| `SQ_CRYPTO_WS_ENABLED` | `true` | 啟用 WS 串流 |
| `SQ_CRYPTO_WS_STREAMS` | `trade,kline_1m,ticker,depth` | 訂閱串流類型 |
| `SQ_CRYPTO_WS_KLINE_INTERVALS` | `1m,5m,15m,1h` | K 線週期 |
| `SQ_CRYPTO_WS_RECONNECT_BASE_SEC` | `5` | 基礎重連間隔 |
| `SQ_CRYPTO_WS_RECONNECT_MAX_SEC` | `60` | 最大重連間隔 |
| `SQ_CRYPTO_WS_TRADE_WINDOW_SIZE` | `10000` | trade 滾動窗口 |

### 技術指標

| 配置 | 默認值 | 說明 |
|------|--------|------|
| `SQ_CRYPTO_INDICATOR_RSI_PERIOD` | `14` | RSI 週期 |
| `SQ_CRYPTO_INDICATOR_MACD_FAST` | `12` | MACD 快線 |
| `SQ_CRYPTO_INDICATOR_MACD_SLOW` | `26` | MACD 慢線 |
| `SQ_CRYPTO_INDICATOR_BB_PERIOD` | `20` | 布林帶週期 |
| `SQ_CRYPTO_INDICATOR_BB_STD` | `2.0` | 布林帶標準差 |
| `SQ_CRYPTO_INDICATOR_ATR_PERIOD` | `14` | ATR 週期 |

### 告警

| 配置 | 默認值 | 說明 |
|------|--------|------|
| `SQ_CRYPTO_ALERTS_ENABLED` | `true` | 啟用告警 |
| `SQ_CRYPTO_ALERT_PRICE_CHANGE_PCT` | `5.0` | 漲跌幅告警閾值 % |
| `SQ_CRYPTO_ALERT_RSI_OVERBOUGHT` | `70.0` | RSI 超買閾值 |
| `SQ_CRYPTO_ALERT_RSI_OVERSOLD` | `30.0` | RSI 超賣閾值 |
| `SQ_CRYPTO_ALERT_COOLDOWN_SEC` | `300` | 告警冷卻期（秒） |
| `SQ_CRYPTO_ALERT_LARGE_ORDER_USD` | `100000` | 大單閾值（USD） |

### 推送

| 配置 | 默認值 | 說明 |
|------|--------|------|
| `SQ_CRYPTO_PUSH_INTERVAL_SEC` | `5` | 推送間隔 |
| `SQ_CRYPTO_PUSH_TYPES` | `quotes,indicators,alerts,micro` | 推送消息類型 |

## WebSocket 推送消息類型

前端通過 `/ws` 端點接收以下加密貨幣相關消息：

```json
{"type": "crypto_quotes", "data": [...], "timestamp": "..."}
{"type": "crypto_alerts", "data": [...], "timestamp": "..."}
```

## 技術指標清單

### 趨勢
RSI, MACD (Line/Signal/Histogram), EMA (9/21/55/200), Supertrend, Ichimoku Cloud

### 動量
Stochastic RSI (K/D), Williams %R, CCI

### 波動
Bollinger Bands (Upper/Middle/Lower/Width), ATR, Keltner Channel, 波動率百分位

### 量價
OBV, VWAP, MFI, ADOSC

### 加密專用
Taker Buy/Sell Ratio, 大單偵測

## 依賴

- `websockets>=12.0`（已安裝）
- 幣安公開市場數據串流 **無需 API Key**

## 測試

```bash
python -m pytest tests/test_crypto_ws.py -v