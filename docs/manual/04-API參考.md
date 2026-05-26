# 4. API 參考

> Base URL: `http://localhost:8000`
> 認證方式: Bearer Token（JWT）
> 互動式文檔: `http://localhost:8000/docs`（Swagger UI）

## 4.1 認證與權限

| 級別 | 說明 |
|------|------|
| 公開 | 無需登錄即可訪問（健康檢查、配置、儀表盤、實時行情等） |
| 登錄 | 需要有效的 JWT Token |
| 管理員 | 需要 admin 角色的 JWT Token |

**演示模式** (`SQ_DEMO_MODE=true`)：所有 GET 請求公開，POST/DELETE 需認證。

---

## 4.2 健康檢查

| 方法 | 路徑 | 說明 |
|------|------|------|
| GET | `/api/health` | 基本健康檢查 |
| GET | `/api/health/detailed` | 詳細健康（CPU/內存/DB/Redis） |

---

## 4.3 認證 (`/api/auth`)

| 方法 | 路徑 | 說明 | 權限 |
|------|------|------|------|
| POST | `/api/auth/register` | 註冊新用戶 | 公開 |
| POST | `/api/auth/login` | 登錄（返回 JWT Token） | 公開 |
| GET | `/api/auth/me` | 獲取當前用戶信息 | 登錄 |
| PUT | `/api/auth/settings` | 更新用戶設置 | 登錄 |
| GET | `/api/auth/watchlist` | 獲取自選股列表 | 登錄 |
| POST | `/api/auth/watchlist` | 添加自選股 | 登錄 |
| DELETE | `/api/auth/watchlist/{code}` | 刪除自選股 | 登錄 |
| GET | `/api/auth/alert-rules` | 獲取預警規則 | 登錄 |
| POST | `/api/auth/alert-rules` | 創建預警規則 | 登錄 |
| GET | `/api/auth/users` | 獲取所有用戶 | 管理員 |
| POST | `/api/auth/users/{id}/reset-password` | 重置用戶密碼 | 管理員 |

---

## 4.4 股票數據 (`/api/stocks`)

| 方法 | 路徑 | 說明 | 權限 |
|------|------|------|------|
| GET | `/api/stocks` | 股票列表（分頁/搜索） | 公開 |
| GET | `/api/stocks/{code}` | 股票詳情 | 公開 |
| GET | `/api/stocks/{code}/kline` | K 線數據 | 公開 |
| GET | `/api/stocks/{code}/logo` | 股票 Logo | 公開 |
| GET | `/api/stocks/realtime` | 多市場實時行情 | 公開 |
| GET | `/api/stocks/{code}/sparkline` | 迷你圖 | 公開 |
| GET | `/api/stocks/compare` | 多股票對比 | 公開 |
| POST | `/api/stocks/download` | 下載歷史數據 | 登錄 |
| POST | `/api/stocks/download-all` | 批量下載 | 登錄 |

---

## 4.5 回測與優化 (`/api/backtest`, `/api/optimize`)

| 方法 | 路徑 | 說明 | 權限 |
|------|------|------|------|
| POST | `/api/backtest` | 基礎回測 | 登錄 |
| POST | `/api/backtest/advanced` | 高級回測（自定義參數） | 登錄 |
| POST | `/api/backtest/multi` | 多策略回測 | 登錄 |
| GET | `/api/backtest/history` | 回測歷史記錄 | 登錄 |
| POST | `/api/optimize` | 參數優化 | 登錄 |
| POST | `/api/walkforward` | Walk-Forward 分析 | 登錄 |
| POST | `/api/auto-optimize` | 全自動優化 | 登錄 |
| GET | `/api/heatmap` | 參數敏感性熱力圖 | 登錄 |

---

## 4.6 組合分析 (`/api/portfolio`)

| 方法 | 路徑 | 說明 | 權限 |
|------|------|------|------|
| POST | `/api/portfolio` | 組合分析（通用） | 登錄 |
| POST | `/api/portfolio/equal-weight` | 等權重組合 | 登錄 |
| POST | `/api/portfolio/risk-parity` | 風險平價 | 登錄 |
| POST | `/api/portfolio/mvo` | Markowitz 均值方差 | 登錄 |
| POST | `/api/portfolio/bl` | Black-Litterman | 登錄 |
| POST | `/api/portfolio/hrp` | 層次風險平價 | 登錄 |
| POST | `/api/portfolio/cvar` | CVaR 優化 | 登錄 |
| POST | `/api/portfolio/kelly` | Kelly 公式 | 登錄 |
| POST | `/api/portfolio/dynamic` | 動態權重 | 登錄 |
| POST | `/api/portfolio/regime` | 制度切換 | 登錄 |
| POST | `/api/portfolio/multi-timeframe` | 多時間框架 | 登錄 |
| POST | `/api/portfolio/voting` | 投票機制 | 登錄 |
| POST | `/api/portfolio/sector-limit` | 行業限制 | 登錄 |

---

## 4.7 信號與預警

| 方法 | 路徑 | 說明 | 權限 |
|------|------|------|------|
| GET | `/api/signals` | 實時信號 | 公開 |
| GET | `/api/signals/leaderboard` | 策略排行榜 | 公開 |
| GET | `/api/alerts/history` | 預警歷史 | 公開 |
| GET | `/api/alerts/rules` | 預警規則列表 | 登錄 |
| POST | `/api/alerts/rules` | 創建預警規則 | 登錄 |
| PUT | `/api/alerts/rules/{id}` | 更新預警規則 | 登錄 |
| DELETE | `/api/alerts/rules/{id}` | 刪除預警規則 | 登錄 |
| POST | `/api/alerts/suggest` | 自動建議規則 | 登錄 |
| POST | `/api/alerts/test` | 測試通知渠道 | 登錄 |

---

## 4.8 風控 (`/api/risk`)

| 方法 | 路徑 | 說明 | 權限 |
|------|------|------|------|
| POST | `/api/risk/position-size` | 計算倉位大小 | 登錄 |
| POST | `/api/risk/budget-check` | 風險預算檢查 | 登錄 |
| POST | `/api/risk/drawdown-protect` | 回撤保護檢查 | 登錄 |

---

## 4.9 數據中心 (`/api/data`)

| 方法 | 路徑 | 說明 | 權限 |
|------|------|------|------|
| GET | `/api/data/sectors` | 板塊列表 | 公開 |
| GET | `/api/data/sector-stocks` | 板塊成分股 | 公開 |
| GET | `/api/data/sector-rotation` | 板塊輪動 | 公開 |
| GET | `/api/data/sector-heatmap` | 板塊熱力圖 | 公開 |
| GET | `/api/data/capital-flow` | 資金流向 | 公開 |
| GET | `/api/data/dragon-tiger` | 龍虎榜 | 公開 |
| GET | `/api/data/fundamentals` | 基本面數據 | 公開 |
| GET | `/api/data/minutes` | 分鐘 K 線 | 公開 |
| GET | `/api/data/quality` | 數據質量報告 | 公開 |
| GET | `/api/data/snapshot` | 行情快照 | 公開 |

---

## 4.10 儀表盤與市場

| 方法 | 路徑 | 說明 | 權限 |
|------|------|------|------|
| GET | `/api/dashboard` | 儀表盤數據 | 公開 |
| GET | `/api/dashboard/market` | 市場概覽 | 公開 |
| GET | `/api/indices` | A 股指數行情 | 公開 |
| GET | `/api/realtime/{code}` | 實時行情 | 公開 |
| GET | `/api/benchmark` | 滬深 300 基準 | 公開 |

---

## 4.11 任務管理 (`/api/tasks`)

| 方法 | 路徑 | 說明 | 權限 |
|------|------|------|------|
| GET | `/api/tasks` | 任務列表 | 登錄 |
| GET | `/api/tasks/{id}` | 任務詳情 | 登錄 |
| POST | `/api/tasks/{id}/cancel` | 取消任務 | 登錄 |
| POST | `/api/tasks/{id}/retry` | 重試任務 | 登錄 |
| DELETE | `/api/tasks/{id}` | 刪除任務 | 登錄 |
| POST | `/api/tasks/cleanup` | 清理已完成任務 | 登錄 |
| POST | `/api/tasks/batch` | 批量操作 | 登錄 |

---

## 4.12 策略管理

| 方法 | 路徑 | 說明 | 權限 |
|------|------|------|------|
| GET | `/api/strategies` | 策略列表（內置+自定義） | 公開 |
| GET | `/api/strategies/{name}` | 策略詳情 | 公開 |
| POST | `/api/strategies` | 上傳自定義策略 | 登錄 |
| DELETE | `/api/strategies/{name}` | 刪除自定義策略 | 登錄 |

---

## 4.13 加密貨幣 (`/api/crypto`)

| 方法 | 路徑 | 說明 | 權限 |
|------|------|------|------|
| GET | `/api/crypto/symbols` | 支持的交易對 | 公開 |
| GET | `/api/crypto/realtime` | 實時行情 | 公開 |
| GET | `/api/crypto/kline` | K 線數據 | 公開 |

---

## 4.14 Polymarket 預測市場 (`/api/polymarket`)

| 方法 | 路徑 | 說明 | 權限 |
|------|------|------|------|
| GET | `/api/polymarket/markets` | 市場列表 | 公開 |
| GET | `/api/polymarket/events` | 事件列表 | 公開 |
| GET | `/api/polymarket/tags` | 標籤列表 | 公開 |
| GET | `/api/polymarket/search` | 搜索市場 | 公開 |
| GET | `/api/polymarket/{id}/history` | 價格歷史 | 公開 |
| GET | `/api/polymarket/{id}/orderbook` | 訂單簿 | 公開 |
| POST | `/api/polymarket/sync` | 同步數據 | 登錄 |
| GET | `/api/polymarket/alerts` | 預警規則 | 登錄 |
| POST | `/api/polymarket/alerts` | 創建預警 | 登錄 |

---

## 4.15 其他

| 方法 | 路徑 | 說明 | 權限 |
|------|------|------|------|
| GET | `/api/config` | 讀取配置 | 公開 |
| PUT | `/api/config` | 更新配置 | 管理員 |
| GET | `/api/screener` | 股票篩選器 | 公開 |
| GET | `/api/export` | 導出 CSV/JSON | 登錄 |
| GET | `/api/forex` | 外匯行情 | 公開 |
| GET | `/api/global-market` | 全球市場指數 | 公開 |
| POST | `/api/notify/test` | 測試通知 | 登錄 |
| GET | `/api/stock-universe` | 股票池列表 | 公開 |
| POST | `/api/stock-universe/sync` | 同步股票池 | 管理員 |
| POST | `/api/stock-universe/intro` | 同步股票簡介 | 管理員 |
| GET | `/api/scheduler` | 定時任務列表 | 公開 |
| POST | `/api/scheduler/{name}/toggle` | 啟用/禁用定時任務 | 管理員 |

---

## 4.16 WebSocket

| 路徑 | 說明 |
|------|------|
| `ws://localhost:8000/ws?token={jwt}` | 實時行情推送 |

- 最大 50 個連接
- 交易時段（09:15-15:15 CST）推送實時行情和信號更新
- 任務狀態變更時廣播通知
