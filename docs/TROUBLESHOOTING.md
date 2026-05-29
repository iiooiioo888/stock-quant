# 🔧 Stock-Quant 故障排除指南 (Troubleshooting)

> **版本**: v1.0 | **最後更新**: 2026-05-29 | **適用對象**: 開發者、運維人員

本指南提供常見問題的診斷步驟與解決方案，幫助快速恢復系統正常運行。

---

## 📋 目錄

- [快速診斷流程](#快速診斷流程)
- [數據源問題](#數據源問題)
- [回測引擎問題](#回測引擎問題)
- [API 服務問題](#api 服務問題)
- [前端問題](#前端問題)
- [數據庫問題](#數據庫問題)
- [任務佇列問題](#任務佇列問題)
- [記憶體與效能問題](#記憶體與效能問題)
- [部署相關問題](#部署相關問題)

---

## 🚨 快速診斷流程

### 第一步：檢查服務狀態

```bash
# Docker 部署
docker-compose ps

# 直接運行
ps aux | grep -E "(main.py|celery|uvicorn)"

# 檢查端口佔用
netstat -tlnp | grep :8000
# 或
lsof -i :8000
```

### 第二步：查看健康檢查

```bash
# 基礎健康檢查
curl http://localhost:8000/api/health

# 詳細健康檢查（含指標）
curl http://localhost:8000/api/health/detailed | jq

# 數據源健康狀態
curl http://localhost:8000/api/data-sources/health | jq
```

### 第三步：檢查日誌

```bash
# Docker 日誌
docker-compose logs --tail=100
docker-compose logs -f celery-worker  # 只看 Worker

# 應用日誌
tail -f logs/app.log
journalctl -u stock-quant -n 100 --no-pager  # systemd

# 搜尋錯誤關鍵字
grep -i "error\|exception\|traceback" logs/app.log | tail -20
```

### 第四步：資源檢查

```bash
# CPU / 記憶體
top -o %MEM
free -h

# 磁碟空間
df -h
du -sh data/ logs/

# 數據庫大小
sqlite3 data/stock.db "SELECT page_count * page_size as size FROM pragma_page_count(), pragma_page_size();"
```

---

## 📡 數據源問題

### 症狀 1：Yahoo Finance 429 錯誤

**錯誤訊息**:
```
HTTPError: 429 Client Error: Too Many Requests
```

**原因**: API 請求頻率超過限制

**解決方案**:

```bash
# 1. 暫時禁用 Yahoo，切換至 AKShare
export SQ_YAHOO_ENABLED=false
export SQ_AKSHARE_ENABLED=true

# 2. 增加請求間隔（修改 .env）
SQ_YAHOO_REQUEST_INTERVAL=3.0  # 從 1s 增加到 3s

# 3. 清除快取後重試
curl -X POST http://localhost:8000/api/cache/clear

# 4. 實施多源輪詢（代碼層面）
# 參照 src/core/fallback.py 的降級邏輯
```

### 症狀 2：AKShare 連接超時

**錯誤訊息**:
```
ConnectionError: HTTPSConnectionPool(host='akshare.xyz', port=443): Read timed out.
```

**解決方案**:

```python
# 1. 增加超時時間（臨時）
import akshare as ak
ak.set_timeout(30)  # 預設可能為 5s

# 2. 檢查網絡連通性
curl -I https://akshare.xyz

# 3. 使用備援數據源
export SQ_EASTMONEY_ENABLED=true

# 4. 檢查是否被防火牆阻擋
ping akshare.xyz
traceroute akshare.xyz
```

### 症狀 3：IB 連接失敗

**錯誤訊息**:
```
IBConnectionError: Failed to connect to TWS/Gateway
```

**檢查清單**:

```bash
# 1. 確認 TWS/Gateway 正在運行
ps aux | grep -E "(ibgateway|twss)"

# 2. 檢查 IB 配置
echo $SQ_IB_HOST      # 應為 127.0.0.1 或實際 IP
echo $SQ_IB_PORT      # 預設 7496 (TWS) / 4001 (Gateway)
echo $SQ_IB_CLIENT_ID # 唯一客戶端 ID

# 3. 測試 TCP 連接
telnet $SQ_IB_HOST $SQ_IB_PORT
# 或
nc -zv $SQ_IB_HOST $SQ_IB_PORT

# 4. 檢查 TWS API 設置
# TWS → File → Global Configuration → API → Settings
# ✓ Enable ActiveX and Socket Clients
# ✓ Allow connections from localhost only (或取消以允許遠程)
# □ Trust only trusted IPs (建議取消勾選測試)
```

---

## 🧪 回測引擎問題

### 症狀 1：回測結果為空

**可能原因**:

1. 數據時間範圍內無交易數據
2. 策略條件過於嚴格，無信號產生
3. 數據格式錯誤

**診斷步驟**:

```python
# 1. 驗證數據存在性
from src.core.local_kline import LocalKlineStorage
kline = LocalKlineStorage()
df = kline.get_kline('AAPL', '1d', '2024-01-01', '2024-12-31')
print(f"數據行數：{len(df)}")

# 2. 檢查策略信號
from strategies.ma_cross_strategy import MACrossStrategy
strategy = MACrossStrategy()
signals = strategy.generate_signals(df)
print(f"信號數量：{len(signals)}")

# 3. 放寬參數測試
params = {'fast_ma': 5, 'slow_ma': 20}  # 更敏感的參數
```

### 症狀 2：回測運行極慢

**可能原因**:

1. 數據量過大（多年分鐘線）
2. 策略邏輯複雜度太高
3. 記憶體不足導致 swap

**優化方案**:

```bash
# 1. 限制數據範圍
# API 調用添加參數：
?start_date=2024-01-01&end_date=2024-12-31

# 2. 啟用指標預計算（Phase 2 功能）
# 目前可手動建立指標列：
python scripts/precompute_indicators.py AAPL

# 3. 增加 Worker 資源
# docker-compose.yml:
celery-worker:
  deploy:
    resources:
      limits:
        cpus: '2'
        memory: 4G
```

### 症狀 3：Optuna 優化卡住

**解決方案**:

```bash
# 1. 檢查 trials 進度
curl http://localhost:8000/api/optuna/status/<study_id> | jq

# 2. 設置早停機制
# 在優化參數中添加：
timeout=3600  # 1 小時超時
n_trials=100  # 最多 100 次試驗

# 3. 強制停止並清理
python src/core/cleanup_stale_optuna.py

# 4. 降低並行度
export OPTUNA_N_JOBS=2  # 從 4 降到 2
```

---

## 🌐 API 服務問題

### 症狀 1：API 響應 500 錯誤

**診斷步驟**:

```bash
# 1. 查看詳細錯誤日誌
curl -v http://localhost:8000/api/backtest 2>&1 | grep -A 20 "< HTTP"

# 2. 檢查請求參數
curl -X POST http://localhost:8000/api/backtest \
  -H "Content-Type: application/json" \
  -d '{"code": "AAPL", ...}' \
  2>&1 | jq

# 3. 重現問題並捕獲堆疊
python -c "
import requests
try:
    r = requests.post('http://localhost:8000/api/backtest', json={...})
    r.raise_for_status()
except Exception as e:
    import traceback
    traceback.print_exc()
"
```

### 症狀 2：JWT 認證失敗

**錯誤**: `401 Unauthorized` 或 `Token expired`

**解決方案**:

```bash
# 1. 檢查 Token 是否過期
echo $JWT_TOKEN | cut -d'.' -f2 | base64 -d | jq '.exp'

# 2. 重新登入獲取新 Token
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "..."}' | jq '.access_token'

# 3. 調整 Token 過期時間（.env）
SQ_JWT_EXPIRE_MINUTES=1440  # 從 30 分鐘改為 24 小時

# 4. 實現 Token 刷新機制
# 參照 src/core/auth.py 的 refresh_token 端點
```

### 症狀 3：CORS 錯誤（前端無法調用 API）

**瀏覽器控制台錯誤**:
```
Access to fetch at 'http://api/...' from origin 'http://frontend' has been blocked by CORS policy
```

**解決方案**:

```python
# main.py 中檢查 CORS 配置
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "https://your-domain.com"],  # 添加前端域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

## 💻 前端問題

### 症狀 1：白屏或無限加載

**診斷步驟**:

```bash
# 1. 檢查瀏覽器控制台錯誤
F12 → Console → 查看紅色錯誤

# 2. 檢查網絡請求
F12 → Network → 查看失敗的請求

# 3. 清除緩存
Ctrl+Shift+Delete → Clear cache

# 4. 檢查靜態資源
curl -I http://localhost:8000/static/js/main.js
```

**常見原因與解決**:

| 錯誤 | 原因 | 解決方案 |
|------|------|----------|
| `ChunkLoadError` | Webpack chunk 加載失敗 | 清除緩存，檢查 Nginx 配置 |
| `TypeError: Cannot read property` | 數據格式不符 | 檢查 API 響應，添加 null 檢查 |
| `WebSocket connection failed` | WS 服務未啟動 | 確認後端 WebSocket 已啟用 |

### 症狀 2：圖表不顯示

**解決方案**:

```javascript
// 1. 檢查 ECharts 實例
console.log(chartInstance); // 應為 object

// 2. 驗證數據格式
console.log(chartData.series); // 應為陣列

// 3. 檢查容器尺寸
document.querySelector('.chart-container').offsetWidth; // 應 > 0

// 4. 手動觸發重繪
chartInstance.resize();
```

---

## 🗄️ 數據庫問題

### 症狀 1：database is locked

**原因**: SQLite 併發寫入衝突

**解決方案**:

```bash
# 1. 啟用 WAL 模式（立即見效）
sqlite3 data/stock.db "PRAGMA journal_mode=WAL;"

# 2. 檢查是否有長事務
sqlite3 data/stock.db "SELECT * FROM sqlite3_master WHERE type='table';"

# 3. 終結卡住的進程
lsof data/stock.db
kill -9 <pid>

# 4. 定期維護腳本
cat > scripts/vacuum_db.sh << 'EOF'
#!/bin/bash
sqlite3 data/stock.db "VACUUM;"
sqlite3 data/stock.db "ANALYZE;"
EOF
chmod +x scripts/vacuum_db.sh
./scripts/vacuum_db.sh
```

### 症狀 2：數據庫損壞

**症狀**: `database disk image is malformed`

**恢復步驟**:

```bash
# 1. 備份當前狀態
cp data/stock.db data/stock.db.corrupted

# 2. 嘗試導出 SQL
sqlite3 data/stock.db ".dump" > backup.sql

# 3. 重建數據庫
rm data/stock.db
python src/core/init_db.py

# 4. 導入數據（如果 dump 成功）
sqlite3 data/stock.db < backup.sql

# 5. 從備份恢復（最佳方案）
./restore.sh latest_backup.tar.gz
```

### 症狀 3：查詢極慢

**診斷**:

```bash
# 1. 分析查詢計劃
sqlite3 data/stock.db "EXPLAIN QUERY PLAN SELECT * FROM klines WHERE code='AAPL';"

# 2. 檢查缺失索引
sqlite3 data/stock.db ".indices klines"

# 3. 建立索引
sqlite3 data/stock.db << 'EOF'
CREATE INDEX IF NOT EXISTS idx_klines_code ON klines(code);
CREATE INDEX IF NOT EXISTS idx_klines_date ON klines(date);
CREATE INDEX IF NOT EXISTS idx_klines_code_date ON klines(code, date);
EOF

# 4. 分析統計信息
sqlite3 data/stock.db "ANALYZE;"
```

---

## 📬 任務佇列問題

### 症狀 1：Celery Worker 不消費任務

**檢查步驟**:

```bash
# 1. 檢查 Worker 狀態
celery -A celery_worker inspect ping
celery -A celery_worker inspect stats

# 2. 查看佇列長度
celery -A celery_worker inspect active_count()

# 3. 檢查 Broker 連接
redis-cli ping  # 如使用 Redis
# 應返回 PONG

# 4. 重啟 Worker
docker-compose restart celery-worker
```

### 症狀 2：任務重複執行

**原因**: Visibility timeout 設置不當

**解決方案**:

```python
# celeryconfig.py
task_acks_late = True  # 任務完成後才確認
task_reject_on_worker_lost = True  # Worker 崩潰時拒絕任務
worker_prefetch_multiplier = 1  # 每次只取一個任務
```

---

## 💾 記憶體與效能問題

### 症狀 1：記憶體持續增長

**診斷工具**:

```bash
# 1. 安裝 memory_profiler
pip install memory-profiler

# 2. 分析特定函數
python -m memory_profiler -m main.py

# 3. 实时监控
watch -n 1 'ps aux | grep python | awk "{print \$6/1024, \$11}"'
```

**常見洩漏點**:

```python
# ❌ 錯誤：全局累積 DataFrame
global_cache = []

def fetch_data():
    df = pd.read_csv(...)
    global_cache.append(df)  # 永不釋放！

# ✅ 正確：使用 LRU 緩存
from functools import lru_cache

@lru_cache(maxsize=100)
def fetch_data(code):
    return pd.read_csv(...)
```

### 症狀 2：CPU 使用率 100%

**排查步驟**:

```bash
# 1. 找出高 CPU 進程
top -o %CPU

# 2. 使用 py-spy 分析
pip install py-spy
py-spy top --pid <python_pid>

# 3. 生成火焰圖
py-spy record -o profile.svg --pid <python_pid>

# 4. 優化熱點代碼
# 常見優化：
# - 使用向量化操作替代循環
# - 使用 numba 加速計算密集型代碼
# - 異步化 I/O 密集型操作
```

---

## 🚀 部署相關問題

### 症狀 1：Docker 容器無法啟動

**診斷**:

```bash
# 1. 查看容器日誌
docker-compose logs app

# 2. 檢查配置
docker-compose config

# 3. 驗證鏡像
docker images | grep stock-quant

# 4. 重建容器
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

### 症狀 2：Render.com 部署失敗

**常見問題**:

| 錯誤 | 原因 | 解決方案 |
|------|------|----------|
| Build failed | 依賴安裝失敗 | 檢查 requirements.txt 格式 |
| Health check failed | 啟動超時 | 增加 `webCommand` 啟動時間 |
| Database error | SQLite 權限 | 確保 `data/` 目錄可寫 |

**render.yaml 範例**:

```yaml
services:
  - type: web
    name: stock-quant
    env: python
    buildCommand: pip install -r requirements.txt
    startCommand: uvicorn main:app --host 0.0.0.0 --port $PORT
    envVars:
      - key: SQ_DATABASE_URL
        value: sqlite:///data/stock.db
    disk:
      name: stock-data
      mountPath: /data
      sizeGB: 5
```

---

## 📞 獲取幫助

如果以上方法無法解決問題：

1. **搜尋既有 Issue**: https://github.com/.../issues
2. **建立新 Issue**: 包含以下信息
   - 重現步驟
   - 預期行為 vs 實際行為
   - 環境信息（Python 版本、OS、Docker 版本）
   - 相關日誌片段
   - 截圖或錯誤訊息

3. **緊急聯絡**: （內部團隊）Slack #stock-quant-alerts

---

## 📎 附錄：診斷腳本集合

### A. 一鍵診斷腳本

```bash
#!/bin/bash
# diagnose.sh - 一鍵系統診斷

echo "=== Stock-Quant 系統診斷 ==="
echo ""

echo "1. 服務狀態"
docker-compose ps 2>/dev/null || ps aux | grep -E "(main|celery)" | grep -v grep
echo ""

echo "2. 健康檢查"
curl -s http://localhost:8000/api/health | jq '.' 2>/dev/null || echo "無法連接 API"
echo ""

echo "3. 資源使用"
free -h
df -h data/ 2>/dev/null || true
echo ""

echo "4. 最近錯誤日誌"
docker-compose logs --tail=50 2>/dev/null | grep -i error | tail -10 || true
echo ""

echo "5. 數據庫狀態"
sqlite3 data/stock.db "PRAGMA integrity_check;" 2>/dev/null || echo "DB not found"
echo ""

echo "診斷完成"
```

### B. 性能基準測試

```bash
#!/bin/bash
# benchmark.sh - API 性能基準測試

echo "=== API 性能基準測試 ==="

# 健康檢查延遲
echo -n "Health check latency: "
curl -s -o /dev/null -w "%{time_total}s\n" http://localhost:8000/api/health

# 回測 API 延遲
echo -n "Backtest API latency: "
curl -s -o /dev/null -w "%{time_total}s\n" \
  -X POST http://localhost:8000/api/backtest \
  -H "Content-Type: application/json" \
  -d '{"code":"AAPL","strategy":"ma_cross","start":"2024-01-01","end":"2024-12-31"}'

echo "測試完成"
```

---

*最後更新*: 2026-05-29  
*維護者*: Stock-Quant Support Team
