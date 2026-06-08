# OpenTelemetry 與結構化日誌設置指南

## 概述

本專案已集成 OpenTelemetry 追蹤和 structlog 結構化日誌，提供完整的可觀測性支持。

## 功能特性

### 1. OpenTelemetry 追蹤
- **自動儀器化**: FastAPI 路由自動追蹤
- **分布式追蹤**: 支持跨服務追蹤鏈
- **多種導出器**: Console (開發) / OTLP (生產)
- **自定義 Span**: 支持業務邏輯手動標記

### 2. Structlog 結構化日誌
- **結構化輸出**: JSON 格式（生產）/ 彩色控制台（開發）
- **上下文綁定**: 支持 request_id、user_id 等上下文
- **時間戳**: ISO 8601 格式
- **異常追蹤**: 完整 stack trace

## 使用方法

### 基本設置

```python
# 在應用啟動時初始化
from src.monitoring.telemetry import setup_telemetry, instrument_fastapi
from src.monitoring.logging_config import setup_structured_logging

# 設置結構化日誌
setup_structured_logging(log_level="INFO", json_format=False)

# 設置 OpenTelemetry
setup_telemetry(service_name="stock-quant")

# 為 FastAPI 應用注入追蹤
instrument_fastapi(app)
```

### 使用追蹤上下文

```python
from src.monitoring.telemetry import get_tracer, trace_context

tracer = get_tracer()

# 方法 1: 使用上下文管理器
with trace_context("db_query", table="users", operation="select"):
    # 執行數據庫查詢
    result = db.execute(query)

# 方法 2: 手動創建 span
with tracer.start_as_current_span("strategy_backtest") as span:
    span.set_attribute("strategy_id", strategy_id)
    span.set_attribute("date_range", f"{start_date} to {end_date}")
    # 執行回測
    results = run_backtest(strategy_id, start_date, end_date)
```

### 使用結構化日誌

```python
from src.monitoring.logging_config import get_logger

logger = get_logger(__name__)

# 基本日誌
logger.info("用戶登錄", user_id=user_id, ip=client_ip)

# 綁定上下文
bound_logger = logger.bind(request_id=request_id, session_id=session_id)
bound_logger.debug("處理請求中")
bound_logger.info("請求完成", duration_ms=duration)

# 錯誤日誌
try:
    process_data(data)
except Exception as e:
    logger.error("數據處理失敗", error=str(e), data_id=data_id, exc_info=True)
```

## 環境變量配置

| 變量 | 說明 | 預設值 |
|------|------|--------|
| `OTEL_SERVICE_NAME` | 服務名稱 | stock-quant |
| `OTEL_TRACES_EXPORTER` | 追蹤導出器 (console/otlp) | console |
| `OTEL_METRICS_EXPORTER` | 指標導出器 (console/otlp) | console |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OTLP 端點 | http://localhost:4317 |
| `SQ_LOG_LEVEL` | 日誌級別 | INFO |
| `SQ_LOG_JSON` | JSON 格式輸出 | false |

## Docker Compose 集成

```yaml
version: '3.8'
services:
  app:
    environment:
      - OTEL_SERVICE_NAME=stock-quant
      - OTEL_TRACES_EXPORTER=otlp
      - OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4317
    depends_on:
      - jaeger
  
  jaeger:
    image: jaegertracing/all-in-one:latest
    ports:
      - "16686:16686"  # UI
      - "4317:4317"    # OTLP gRPC
```

## Grafana/Prometheus 集成

參見 `docs/grafana-dashboard.json` 導入預設儀表板。

## 最佳實踐

1. **日誌級別**: 開發用 DEBUG/INFO，生產用 WARNING/ERROR
2. **敏感信息**: 避免記錄密碼、token 等敏感數據
3. **追蹤采樣**: 高流量環境建議配置采樣率
4. **性能考慮**: BatchSpanProcessor 批量導出減少開銷

## 故障排查

### 問題：追蹤未顯示
- 檢查 `setup_telemetry()` 是否在應用啟動時調用
- 確認導出器配置正確
- 查看控制台是否有 OTLP 連接錯誤

### 問題：日誌格式不對
- 確認 `setup_structured_logging()` 已調用
- 檢查 structlog 版本兼容性
- 驗證 processors 鏈配置
