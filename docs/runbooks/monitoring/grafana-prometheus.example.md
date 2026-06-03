# Grafana + Prometheus 範例（stock-quant）

## 1. Prometheus 抓取

```yaml
# prometheus.yml 片段
scrape_configs:
  - job_name: stock-quant
    metrics_path: /metrics
    static_configs:
      - targets: ["localhost:8000"]
```

確認：`curl -s http://localhost:8000/metrics | head`

業務指標（若啟用）：`GET /api/metrics/business/prometheus`

## 2. 建議面板（PromQL 示意）

| 面板 | 查詢 | 說明 |
|------|------|------|
| API 延遲 p95 | `histogram_quantile(0.95, rate(sq_api_request_seconds_bucket[5m]))` | 需確認 metric 名稱與 label |
| 快取命中 | `rate(sq_cache_hits_total[5m])` | 對比 `sq_cache_misses_total` |
| 管線 deferred | 以 `ops check` JSON 的 `pending_deferred` 或日誌 | 可經 Pushgateway 推送 |

> 實際 metric 名稱以 `src/utils/metrics.py` 註冊為準；部署後在 Prometheus **Targets → metric explorer** 核對。

## 3. 與 SOP 告警聯動

- **Uptime**：`/api/health/sop`（見 [uptime-kuma.md](uptime-kuma.md)）
- **佇列積壓**：Grafana 告警 + `task_queue.pending` 來自定期 `ops probe --json`
- **日誌**：`SQ_LOG_FORMAT=json` → Loki `| json | level="ERROR"`

## 4. Docker Compose 擴展示意

可於 `docker-compose.yml` 增加 `prometheus` + `grafana` 服務，網路與 `app` 同 compose；生產環境請限制 Grafana 對外暴露。
