# 效能優化部署檢查清單

部署或升級含效能路線圖改動的版本時，依序確認以下項目。

## 1. 部署前

- [ ] 備份 `data/stock.db`（若曾出現 `SQLITE_CORRUPT`，先修復或重建再升級）
- [ ] 確認 Redis 可連（`SQ_REDIS_ENABLED=true` 時）
- [ ] 更新依賴：`pip install -r requirements.txt`（可選 `pip install -r requirements-dev.txt` 含 numba）
- [ ] 檢查 `.env` 與 `.env.example` 新增變數是否已配置

## 2. 環境變數（建議）

| 變數 | 說明 | 建議 |
|------|------|------|
| `SQ_REDIS_ENABLED` | 二級緩存 | 生產 `true` |
| `SQ_CACHE_WARMUP_ON_STARTUP` | 啟動預熱熱門標的 | 可選 `true` |
| `SQ_CACHE_WARMUP_CODES` | 預熱代碼列表 | 如 `600519,000001` |
| `SQ_HEATMAP_PARALLEL` | 熱力圖並行計算 | `true` |
| `SQ_HEATMAP_MAX_WORKERS` | 並行 worker 數 | `4` |
| `SQ_CELERY_ENABLED` | Celery 任務佇列 | 高負載 `true` |
| `SQ_CELERY_BROKER_URL` | Broker（預設 Redis DB 1） | 與 Redis 密碼一致 |
| `SQ_SQLITE_CACHE_SIZE_KB` | SQLite 頁緩存 | 預設已加大 |
| `SQ_RUNTIME_GC_INTERVAL_SEC` | 週期 GC 間隔 | 預設 `3600` |

## 3. 資料庫遷移

- [ ] 啟動應用一次，確認日誌出現遷移 **v5**（複合索引）成功
- [ ] 可選：執行 `python scripts/warmup_cache.py` 手動預熱

## 4. Docker Compose

```bash
# 僅應用 + Redis
docker compose up -d

# 啟用 Celery Worker（需 SQ_CELERY_ENABLED=true）
docker compose --profile celery up -d
```

- [ ] `app` 健康檢查通過：`GET /api/health`
- [ ] 詳細狀態：`GET /api/health/detailed`（含 Redis、緩存統計）
- [ ] Celery：`docker compose logs celery-worker` 無 broker 連線錯誤

## 5. 驗證

- [ ] `pytest tests/test_perf_integration.py tests/test_fast_indicators.py tests/test_backtest_pagination.py tests/test_cache_warmup.py -q`
- [ ] 回測歷史分頁：`GET /api/backtest/history?page=1&page_size=20` 含 `total`、`has_more`
- [ ] Prometheus（已安裝 `prometheus-client`）：`GET /metrics` 返回指標文本
- [ ] Pro 前端：任務中心進行中任務，WebSocket 進度條應局部更新（非整頁閃爍）
- [ ] 模組懶加載：首次切換分頁時才載入對應 JS（Network 面板可見）

## 6. 監控建議

- 關注 `X-Response-Time-Ms` 響應頭（API 延遲）
- Prometheus：`sq_api_request_seconds`、`sq_cache_hits_total`、`sq_cache_misses_total`
- 緩存：`GET /api/health/detailed` → `redis` 區塊 `hit_rate`

## 7. 回滾

- Celery：設 `SQ_CELERY_ENABLED=false` 並重啟 app（自動回退線程池）
- Redis 不可用時自動降級為 LRU，無需改碼
- 索引遷移 v5 為 additive，一般無需回滾 schema

## 8. 勿提交 / 勿覆蓋

- `data/stock.db`、`data/.admin_password`、`logs/`
- 勿在生產開啟未授權的 `WS_AUTH` 關閉（依 `SQ_WS_AUTH_REQUIRED` 策略）
