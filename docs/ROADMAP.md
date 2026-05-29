# 🗺️ Stock-Quant 進化路線圖 (Roadmap)

> **版本**: v6.0 | **建立日期**: 2026-05-29 | **狀態**: 進行中

本文檔定義了 stock-quant 專案的短期、中期與長期發展目標，幫助貢獻者與使用者理解系統演進方向。

---

## 📍 當前版本定位 (v6.0)

### ✅ 已實現核心能力

| 維度 | 狀態 | 說明 |
|------|------|------|
| **架構** | ✅ 成熟 | FastAPI + SQLite + Celery/AsyncIO + Redis 可選，前後端分離清晰 |
| **數據源** | ⚠️ 基礎可用 | Yahoo Finance + AKShare，免費源穩定性有限 |
| **策略引擎** | ✅ 豐富 | 30+ 內建策略 + 模組化註冊 + Optuna 優化 + Walk-Forward |
| **並行處理** | ✅ 完善 | 任務佇列 + 緩存 + 網格搜索並行 + Windows 線程相容 |
| **前端體驗** | ✅ 專業 | Pro 工作站 + ECharts + 懶加載 + Cmd+K 命令面板 |
| **部署彈性** | ✅ 友善 | Docker Compose + Render 一鍵部署 + 環境變量配置 |
| **測試覆蓋** | ✅ 扎實 | 640+ 測試用例 + 煙霧測試 + Playwright UI 測試 |

### ⚠️ 已知待改善領域

1. **數據源穩定性**: 依賴單一 Yahoo Finance，需增加多源輪詢與降級機制
2. **資料庫擴展性**: SQLite 在高併發寫入場景有瓶頸，需 PostgreSQL 遷移方案
3. **過擬合防護**: 需強化 Walk-Forward 驗證與參數穩定性檢驗
4. **文檔完整性**: 缺少貢獻指南、運維手冊、故障排除指南

---

## 🟢 Phase 1：穩定性與可維護性（1-2 週）

**目標**: 提升系統穩定性，降低運維成本，建立標準化作業流程

### P1-1: 補全文檔體系
- [ ] 建立 `CONTRIBUTING.md` 貢獻指南
- [ ] 建立 `docs/RUNBOOKS.md` 運維手冊
- [ ] 建立 `docs/TROUBLESHOOTING.md` 故障排除指南
- [x] 建立 `docs/ROADMAP.md` 進化路線圖（本文件）

### P1-2: 沙箱模式
- [x] 新增回測沙箱環境，隔離生產數據 (`/api/backtest/sandbox`)
- [x] 實現 AST 白名單校驗與危險語法攔截
- [x] 提供策略示例代碼端點 (`/api/backtest/sandbox/examples`)
- [ ] 實現沙箱數據自動清理機制
- [ ] 提供沙箱/生產切換開關

### P1-3: 外部連接容錯
- [x] IB 連接斷線自動重連邏輯（見 `ib_data.py`）
- [ ] Polymarket API 降級邏輯
- [ ] 連接狀態監控端點 `/api/connections/status`

### P1-4: 日誌標準化
- [ ] 統一 JSON structured logging 格式
- [ ] 增加 trace_id 支援請求追蹤
- [ ] ELK/Grafana 接入範例配置

### P1-5: 數據源健康檢查
- [x] 新增 `/api/data-sources/health` 端點
- [x] 實現多數據源熔斷與動態排隊機制
- [ ] 自動切換健康數據源

---

## 🟡 Phase 2：效能與擴展性（2-4 週）

**目標**: 突破效能瓶頸，支援高併發場景，實現水平擴展

### P2-1: 指標預計算
- [x] 常用技術指標離線預算（MA/MACD/布林帶/RSI/ATR/KDJ/OBV）
- [x] 建立 `precomputed_indicators.py` 預計算引擎
- [x] 多進程並行計算支援
- [x] API 端點：`/api/indicators/precomputed/*`
- [x] 數據版本控制自動失效機制
- [ ] 前端整合：在回測頁面顯示「使用預計算指標」選項
- [ ] 增量更新：僅重新計算變化的 K 線區間

### P2-2: PostgreSQL 遷移
- [ ] Alembic 遷移腳本
- [ ] SQLite → Postgres 數據同步工具
- [ ] 多用戶隔離 Schema 設計
- [ ] 讀寫分離配置（主從複製）

### P2-3: 策略熱加載
- [ ] 策略模組動態載入（無需重啟）
- [ ] 策略變更監聽（watchdog）
- [ ] 熱加載 API `/api/strategies/reload`

### P2-4: 分散式任務佇列
- [ ] Celery + RabbitMQ/Kafka 配置
- [ ] 多節點水平擴展方案
- [ ] 任務路由與優先級隊列
- [ ] 任務失敗重試機制

### P2-5: K 線增量同步
- [x] 新增 klines 表索引 (`idx_klines_code_date`, `idx_klines_code`, `idx_klines_date`)
- [ ] 分鐘 K 線增量下載（避免全量重複）
- [ ] 斷點續傳機制
- [ ] 最後更新時間戳追蹤

---

## 🔵 Phase 3：智能化與生態（1-2 月）

**目標**: 整合 AI 能力，建立策略生態，提升自動化程度

### P3-1: LLM 整合
- [ ] Ollama + Llama3 本地部署
- [ ] 策略解釋生成（自然語言描述）
- [ ] 參數建議推薦
- [ ] 回測報告自動生成

### P3-2: 策略市場
- [ ] 策略上傳/分享功能
- [ ] 用戶評分與評論系統
- [ ] 策略排行榜
- [ ] 社群生態運營工具

### P3-3: 自動特徵工程
- [ ] TA-Lib 因子自動生成
- [ ] 自定義因子擴展接口
- [ ] 特徵重要性評估
- [ ] 候選特徵集篩選

### P3-4: 風險預警引擎
- [ ] 波動率突變檢測
- [ ] 相關性異常監控
- [ ] 自動降倉信號
- [ ] 策略暫停觸發條件

### P3-5: WebAssembly 前端計算
- [ ] 輕量回測邏輯移至瀏覽器
- [ ] Pyodide/WASM 集成
- [ ] 減輕伺服器負載

---

## 🟣 Phase 4：企業級與合規（長期）

**目標**: 滿足企業級需求，符合金融監管要求

### P4-1: 多租戶隔離
- [ ] 用戶/團隊數據完全隔離
- [ ] 獨立 Schema 或 Database per Tenant
- [ ] 資源配額管理

### P4-2: 審計日誌
- [ ] 所有操作記錄不可竄改
- [ ] 回測/交易/配置變更追蹤
- [ ] 審計日誌導出功能

### P4-3: 合規檢查模組
- [ ] T+1 規則檢測
- [ ] 漲跌停限制檢查
- [ ] 交易所規則自動驗證

### P4-4: 災備與快照
- [ ] 自動備份 stock.db + 策略代碼 + 配置
- [ ] S3/NAS 異地備援
- [ ] 一鍵恢復機制
- [ ] 保留策略版本（7 天/30 天）

### P4-5: API 安全強化
- [ ] Rate Limiting（令牌桶算法）
- [ ] OAuth2 / SSO 集成
- [ ] JWT 過期刷新機制
- [ ] WebSocket 認證

---

## 📊 版本迭代計劃

| 版本 | 預計發布 | 重點功能 |
|------|----------|----------|
| v6.1 | 2026-06-15 | Phase 1 全部功能 + 文檔完善 |
| v6.5 | 2026-07-30 | Phase 2 核心功能（Postgres + 分散式） |
| v7.0 | 2026-09-30 | Phase 3 智能化特性（LLM + 策略市場） |
| v8.0 | 2026-12-31 | Phase 4 企業級功能（多租戶 + 合規） |

---

## 🎯 立即可執行優化（Today List）

以下優化可立即執行，無需等待版本迭代：

```bash
# 1. 啟用 SQLite WAL 模式（提升併發寫入）
sqlite3 data/stock.db "PRAGMA journal_mode=WAL;" 2>/dev/null || echo "DB not found, will apply on first creation"

# 2. 為常用查詢欄位增加索引
sqlite3 data/stock.db "CREATE INDEX IF NOT EXISTS idx_kline_code_date ON klines(code, date);" 2>/dev/null || true

# 3. 在 requirements.txt 增加極速 JSON 庫
grep -q "orjson" requirements.txt || echo "orjson>=3.9" >> requirements.txt

# 4. 增加 .gitattributes 避免大文件誤提交
echo "*.db filter=lfs diff=lfs merge=lfs -text" >> .gitattributes
```

---

## 🤝 貢獻指南摘要

### 如何參與？

1. **Fork & Clone**: Fork 專案並 clone 到本地
2. **Branch**: 建立功能分支 `feature/your-feature-name`
3. **Develop**: 開發功能並撰寫測試
4. **Test**: 確保所有測試通過 (`./test_all.sh`)
5. **PR**: 提交 Pull Request 並描述變更

### 程式碼規範

- 遵循 PEP 8 風格指南
- 函數需包含 docstring
- 新增功能需附帶單元測試
- Commit message 使用語義化格式

### 測試要求

- 新功能測試覆蓋率 ≥ 80%
- 所有現有測試必須通過
- 端到端測試需包含關鍵路徑

---

## 📞 聯絡與回饋

- **GitHub Issues**: 提交 Bug 報告與功能建議
- **Discussions**: 技術討論與最佳實踐分享
- **Email**: stock-quant@example.com（待定）

---

*最後更新*: 2026-05-29
*維護者*: Stock-Quant Team
