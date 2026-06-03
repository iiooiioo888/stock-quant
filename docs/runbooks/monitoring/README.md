# 監控與探活

| 文檔 / 工具 | 用途 |
|-------------|------|
| [uptime-kuma.md](uptime-kuma.md) | Uptime Kuma / Push 設定範本 |
| [grafana-prometheus.example.md](grafana-prometheus.example.md) | Grafana + Prometheus  scrape / PromQL |
| [../README.md § E](../README.md#e-外部監控uptime--託管) | 場景對照與 cron |
| `python scripts/ops_audit.py` | 本機全面稽核（check + 可選 probe） |
| `python main.py ops probe --ci` | 單次 HTTP SOP 探活 |
