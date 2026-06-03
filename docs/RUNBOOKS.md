# 📚 Stock-Quant 運維手冊 (Runbooks)

> **版本**: v1.1 | **最後更新**: 2026-06-03 | **適用對象**: 系統管理員、DevOps 工程師

本手冊提供部署、監控、備份與升級的**深度程序**。日常怎麼走、先查哪份文檔，請從 **[運維 SOP 總覽](runbooks/README.md)** 進入（含決策樹與一鍵健檢）。

---

## ⚡ 日常運維速查（3 分鐘）

| 步驟 | 動作 |
|------|------|
| 1 | 服務存活：`curl -s http://localhost:8000/api/health` |
| 2 | 深度指標：`curl -s http://localhost:8000/api/health/detailed`（或 MCP `sq_health`） |
| 3 | 數據源：`curl -s http://localhost:8000/api/data-sources/health` |
| 4 | 本機：`python main.py ops check` 或 `python scripts/ops_audit.py --ci` |
| 5 | 可選：`cd scripts/cursor-agent && npm run ops-check`（見 [MCP.md](MCP.md)） |

異常時依 [SOP 決策樹](runbooks/README.md#決策樹先對症再翻文檔) 跳至 [data-pipeline](runbooks/data-pipeline.md) 或 [TROUBLESHOOTING.md](TROUBLESHOOTING.md)。

---

## 📋 目錄

- [系統架構概覽](#系統架構概覽)
- [部署檢查清單](#部署檢查清單)
- [監控與告警](#監控與告警)
- [備份與恢復](#備份與恢復)
- [常見故障排除](#常見故障排除)
- [效能調優](#效能調優)
- [安全加固](#安全加固)
- [升級流程](#升級流程)

---

## 🏗️ 系統架構概覽

### 核心組件

```
┌─────────────────────────────────────────────────────────────┐
│                        Stock-Quant System                    │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐      │
│  │   Frontend  │    │   FastAPI   │    │   Celery    │      │
│  │  (React +   │◄──►│   Backend   │◄──►│   Worker    │      │
│  │   ECharts)  │    │   (REST)    │    │  (Async)    │      │
│  └─────────────┘    └──────┬──────┘    └──────┬──────┘      │
│                            │                  │              │
│                   ┌────────▼────────┐         │              │
│                   │   SQLite/PostgreSQL       │              │
│                   │   (stock.db)    │◄────────┘              │
│                   └────────┬────────┘                        │
│                            │                                  │
│                   ┌────────▼────────┐                        │
│                   │   Data Sources  │                        │
│                   │ Yahoo/AKShare/IB│                        │
│                   └─────────────────┘                        │
└─────────────────────────────────────────────────────────────┘
```

### 關鍵文件路徑

| 路徑 | 說明 |
|------|------|
| `data/` | SQLite（如 `stock.db`）與本地數據 |
| `logs/` | 應用日誌 |
| `static/` | 前端靜態資源（Pro 在 `static/js/pro/`） |
| `src/core/strategies/` | 內建策略模組 |
| `src/core/` | 核心業務邏輯 |
| `scripts/cursor-agent/` | Cursor SDK 運維健檢腳本 |

---

## ✅ 部署檢查清單

### 首次部署

```bash
# 1. 環境準備
□ Python 3.9+ 已安裝
□ Git 已安裝
□ Docker & Docker Compose（如使用容器化部署）

# 2. 代碼獲取
□ git clone <repository-url>
□ cd stock-quant

# 3. 依賴安裝
□ pip install -r requirements.txt
□ pip install -r requirements-dev.txt（開發環境）

# 4. 環境配置
□ cp .env.example .env
□ 編輯 .env，設置必要變量：
  □ SQ_DATABASE_URL=sqlite:///data/stock.db
  □ SQ_SECRET_KEY=<隨機生成密鑰>
  □ SQ_YAHOO_ENABLED=true
  □ SQ_AKSHARE_ENABLED=true

# 5. 數據庫初始化
□ mkdir -p data
□ 首次 `python main.py serve` 會自動 init_db / 遷移

# 6. 服務啟動
□ python main.py serve（本機）
□ 或 docker compose up -d --build（容器 + 可選 Redis）

# 7. 健康檢查
□ curl http://localhost:8000/api/health
□ 訪問 http://localhost:8000/ 確認前端正常
```

### 生產環境額外檢查

```bash
# 安全配置
□ HTTPS 已啟用（SSL 證書配置）
□ JWT 密鑰已更換為強密碼
□ CORS 已限制為可信域名
□ 敏感配置已移至 Vault/Secrets Manager

# 效能配置
□ SQLite WAL 模式已啟用
□ 數據庫索引已建立
□ Redis 緩存已配置（可選）
□ Nginx 反向代理已配置

# 監控配置
□ Prometheus Exporter 已啟用
□ Grafana 儀表板已導入
□ 告警規則已配置
□ 日誌聚合系統已接入（ELK/Loki）
```

---

## 📊 監控與告警

### 關鍵指標

#### 1. API 性能指標

| 指標 | 正常閾值 | 告警閾值 | 說明 |
|------|----------|----------|------|
| `http_request_duration_seconds` | p95 < 500ms | p95 > 2s | API 響應時間 |
| `http_requests_total` | - | 錯誤率 > 5% | 請求總數與錯誤率 |
| `active_backtests` | < 50 | > 100 | 活躍回測任務數 |

#### 2. 任務佇列指標

| 指標 | 正常閾值 | 告警閾值 | 說明 |
|------|----------|----------|------|
| `celery_tasks_pending` | < 100 | > 500 | 待處理任務數 |
| `celery_task_runtime` | < 60s | > 300s | 任務執行時間 |
| `celery_worker_online` | = 預期數量 | < 預期數量 | Worker 在線數 |

#### 3. 數據庫指標

| 指標 | 正常閾值 | 告警閾值 | 說明 |
|------|----------|----------|------|
| `db_connections_active` | < 80% max | > 90% max | 連接池使用率 |
| `db_query_duration` | < 100ms | > 1s | 查詢耗時 |
| `db_size_mb` | - | > 10GB | 數據庫大小 |

### 監控端點

```bash
# Prometheus 指標
curl http://localhost:8000/metrics

# 運維 SOP（輕量；attention 仍 HTTP 200，僅 verdict 判斷）
curl http://localhost:8000/api/health/sop
python main.py ops probe --ci --json

# 健康檢查詳情（含 SOP、管線、索引）
curl http://localhost:8000/api/health/detailed

# 系統狀態（uptime + sop 摘要，5s 快取）
curl http://localhost:8000/api/status

# 數據源健康狀態
curl http://localhost:8000/api/data-sources/health

# 任務佇列狀態
curl http://localhost:8000/api/tasks/status
```

### 告警規則範例（Prometheus）

```yaml
groups:
  - name: stock-quant-alerts
    rules:
      - alert: HighAPIErrorRate
        expr: rate(http_requests_total{status=~"5.."}[5m]) > 0.05
        for: 5m
        annotations:
          summary: "API 錯誤率過高"
          description: "過去 5 分鐘錯誤率超過 5%"

      - alert: CeleryQueueBacklog
        expr: celery_tasks_pending > 500
        for: 10m
        annotations:
          summary: "任務佇列積壓"
          description: "待處理任務數超過 500"

      - alert: DatabaseSizeWarning
        expr: db_size_mb > 10240
        for: 1h
        annotations:
          summary: "數據庫體積過大"
          description: "stock.db 超過 10GB"
```

---

## 💾 備份與恢復

### 自動備份腳本

```bash
#!/bin/bash
# backup.sh - 每日自動備份腳本

BACKUP_DIR="/backup/stock-quant"
DATE=$(date +%Y%m%d_%H%M%S)
DB_PATH="data/stock.db"
CONFIG_FILES=".env strategies/"

# 創建備份目錄
mkdir -p $BACKUP_DIR/$DATE

# 備份數據庫
cp $DB_PATH $BACKUP_DIR/$DATE/stock.db

# 備份配置文件
cp -r $CONFIG_FILES $BACKUP_DIR/$DATE/

# 壓縮備份
cd $BACKUP_DIR
tar -czf backup_$DATE.tar.gz $DATE
rm -rf $DATE

# 上傳至 S3（可選）
# aws s3 cp backup_$DATE.tar.gz s3://your-bucket/backups/

# 清理舊備份（保留 7 天）
find $BACKUP_DIR -name "backup_*.tar.gz" -mtime +7 -delete

echo "Backup completed: backup_$DATE.tar.gz"
```

### 手動備份

```bash
# 完整備份
./backup.sh

# 僅備份數據庫
cp data/stock.db data/stock.db.backup.$(date +%Y%m%d)

# 導出 SQL（如使用 PostgreSQL）
pg_dump stock_quant > backup_$(date +%Y%m%d).sql
```

### 恢復流程

```bash
# 1. 停止服務
docker-compose down
# 或 kill 進程

# 2. 恢復數據庫
tar -xzf backup_20260529_120000.tar.gz
cp backup_20260529_120000/stock.db data/stock.db

# 3. 恢復配置
cp -r backup_20260529_120000/.env .
cp -r backup_20260529_120000/strategies/ strategies/

# 4. 重啟服務
docker-compose up -d
# 或 python main.py

# 5. 驗證恢復
curl http://localhost:8000/api/health
```

---

## 🔧 常見故障排除

### 問題 1：數據下載失敗率高

**症狀**: 日誌中出現大量 `Yahoo Finance 429 Too Many Requests`

**原因**: API 限流或網絡問題

**解決方案**:

```bash
# 1. 檢查數據源健康狀態
curl http://localhost:8000/api/data-sources/health

# 2. 啟用多源輪詢（修改 .env）
SQ_YAHOO_ENABLED=true
SQ_AKSHARE_ENABLED=true
SQ_EASTMONEY_ENABLED=true

# 3. 增加請求間隔（修改配置）
export SQ_YAHOO_REQUEST_INTERVAL=2.0  # 秒

# 4. 清除快取重試
curl -X POST http://localhost:8000/api/cache/clear
```

### 問題 2：回測任務卡住

**症狀**: 任務狀態一直為 `pending` 或 `running`

**解決方案**:

```bash
# 1. 檢查 Celery Worker 狀態
celery -A celery_worker inspect active
celery -A celery_worker inspect registered

# 2. 重啟 Worker
docker-compose restart celery-worker
# 或 kill -9 <pid> && celery -A celery_worker worker -l info

# 3. 清理卡住的任務
python src/core/cleanup_stale_tasks.py

# 4. 檢查資源使用
top -o %CPU  # CPU 是否飽和
free -h     # 記憶體是否不足
```

### 問題 3：前端頁面加載慢

**症狀**: 首次加載超過 5 秒

**解決方案**:

```bash
# 1. 檢查靜態資源
ls -lh static/js/ static/css/

# 2. 啟用 Gzip 壓縮（Nginx 配置）
gzip on;
gzip_types text/plain application/json application/javascript text/css;

# 3. 檢查瀏覽器緩存
# Nginx 添加：
location /static/ {
    expires 30d;
    add_header Cache-Control "public, immutable";
}

# 4. 構建優化後的靜態資源
cd static
npm run build  # 生產環境構建
```

### 問題 4：數據庫寫入瓶頸

**症狀**: 併發任務失敗率升高，日誌出現 `database is locked`

**解決方案**:

```bash
# 1. 啟用 WAL 模式
sqlite3 data/stock.db "PRAGMA journal_mode=WAL;"

# 2. 調整 WAL 檢查點閾值
sqlite3 data/stock.db "PRAGMA wal_autocheckpoint=1000;"

# 3. 定期 VACUUM（低峰期）
sqlite3 data/stock.db "VACUUM;"

# 4. 考慮遷移至 PostgreSQL
# 參照 docs/ROADMAP.md Phase 2-2
```

### 問題 5：記憶體洩漏

**症狀**: 服務運行一段時間後記憶體持續增長

**解決方案**:

```bash
# 1. 使用 memory_profiler 分析
pip install memory-profiler
python -m memory_profiler main.py

# 2. 檢查是否有未釋放的 DataFrame
# 在長循環中顯式刪除：
del large_dataframe
import gc; gc.collect()

# 3. 設置記憶體限制
ulimit -v 4194304  # 限制為 4GB

# 4. 定期重啟 Worker（臨時方案）
# Celery 配置：
worker_max_tasks_per_child = 1000
```

---

## ⚡ 效能調優

### 數據庫優化

```sql
-- 1. 建立常用查詢索引
CREATE INDEX IF NOT EXISTS idx_klines_code_date ON klines(code, date);
CREATE INDEX IF NOT EXISTS idx_backtests_strategy ON backtests(strategy_name);
CREATE INDEX IF NOT EXISTS idx_signals_created_at ON signals(created_at);

-- 2. 分析查詢計劃
EXPLAIN QUERY PLAN SELECT * FROM klines WHERE code='AAPL' AND date > '2024-01-01';

-- 3. 定期維護
VACUUM;
ANALYZE;
```

### API 響應優化

```python
# 1. 使用 orjson 替代 json
# requirements.txt 已添加 orjson>=3.9

# 2. 啟用響應緩存（Redis）
from fastapi_cache import FastAPICache
from fastapi_cache.backends.redis import RedisBackend

@app.get("/api/stocks/{code}")
@cache(expire=300)  # 5 分鐘緩存
async def get_stock(code: str):
    ...

# 3. 分頁與限制
@app.get("/api/klines")
async def get_klines(limit: int = 1000, offset: int = 0):
    ...
```

### 前端優化

```javascript
// 1. 代碼分割（Webpack/Vite）
const BacktestChart = lazy(() => import('./components/BacktestChart'));

// 2. 虛擬列表（大數據渲染）
import { FixedSizeList } from 'react-window';

// 3. 圖片與圖表懶加載
<img loading="lazy" src="..." />
```

---

## 🔒 安全加固

### 最小權限原則

```bash
# 1. 數據庫用戶權限限制
# PostgreSQL:
CREATE USER stock_quant_readonly WITH PASSWORD 'xxx';
GRANT SELECT ON ALL TABLES IN SCHEMA public TO stock_quant_readonly;

# 2. 容器非 root 運行
# Dockerfile:
USER nobody
WORKDIR /app
```

### 敏感信息保護

```bash
# 1. 使用環境變量，不硬編碼
export SQ_SECRET_KEY=$(openssl rand -hex 32)

# 2. 密鑰管理（生產環境）
# AWS Secrets Manager / HashiCorp Vault

# 3. .gitignore 已包含：
# .env
# *.db
# logs/
```

### 網絡安全

```nginx
# Nginx 配置示例
server {
    listen 443 ssl;
    server_name stock-quant.example.com;

    # SSL 配置
    ssl_certificate /etc/ssl/certs/stock-quant.crt;
    ssl_certificate_key /etc/ssl/private/stock-quant.key;
    ssl_protocols TLSv1.2 TLSv1.3;

    # 安全頭
    add_header X-Frame-Options "SAMEORIGIN";
    add_header X-Content-Type-Options "nosniff";
    add_header X-XSS-Protection "1; mode=block";

    # Rate Limiting
    limit_req_zone $binary_remote_addr zone=api:10m rate=10r/s;
    location /api/ {
        limit_req zone=api burst=20 nodelay;
        proxy_pass http://localhost:8000;
    }
}
```

---

## 🔄 升級流程

### 常規升級

```bash
# 1. 備份當前版本
./backup.sh

# 2. 拉取最新代碼
git pull origin main

# 3. 安裝新依賴
pip install -r requirements.txt --upgrade

# 4. 執行數據庫遷移
alembic upgrade head

# 5. 重啟服務
docker-compose restart
# 或 systemctl restart stock-quant

# 6. 驗證升級
curl http://localhost:8000/api/health
python tests/smoke/test_basic.py
```

### 回滾流程

```bash
# 1. 停止服務
docker-compose down

# 2. 恢復代碼
git checkout <previous-version-tag>

# 3. 恢復數據庫
./restore.sh backup_YYYYMMDD_HHMMSS.tar.gz

# 4. 回滾依賴
pip install -r requirements.<version>.txt

# 5. 重啟並驗證
docker-compose up -d
```

---

## 📞 支援管道

| 問題類型 | 聯絡方式 | 響應時間 |
|----------|----------|----------|
| Bug 報告 | GitHub Issues | 3-5 工作日 |
| 技術諮詢 | GitHub Discussions | 1-3 工作日 |
| 緊急事故 | Email / Slack（內部） | 24 小時內 |
| 功能建議 | GitHub Issues | 7 工作日 |

---

## 📎 附錄

### A. 環境變量參考

完整列表參見 [.env.example](../../.env.example)

### B. 日誌位置

```bash
# Docker 部署
docker-compose logs -f

# 直接運行
tail -f logs/app.log
journalctl -u stock-quant -f  # systemd
```

### C. 相關文檔

- [運維 SOP 總覽](runbooks/README.md)（**建議入口**）
- [數據管線 Runbook](runbooks/data-pipeline.md)
- [MCP 與自動健檢](MCP.md)
- [架構設計](../manual/13-架構設計.md)
- [部署指南](../manual/09-部署指南.md)
- [故障排除](TROUBLESHOOTING.md)
- [進化路線圖](../ROADMAP.md)

---

*最後更新*: 2026-06-03  
*維護者*: Stock-Quant DevOps Team
