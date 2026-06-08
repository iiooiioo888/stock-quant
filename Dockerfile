# ============================================================
# Dockerfile — 多階段構建，體積最小化，生產優化
# ============================================================

# ------ 構建階段 ------
FROM python:3.12-slim AS builder

WORKDIR /build

# 安裝 uv 工具（加速 Python 依賴安裝）
RUN pip install --no-cache-dir uv

# 系統依賴（僅構建時需要）
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# 安裝 Python 依賴到 /install 目錄（使用 uv 加速）
COPY requirements.txt .
RUN uv pip install --system --no-cache -r requirements.txt

# ------ 運行階段 ------
FROM python:3.12-slim AS runtime

# 安裝必要系統依賴和 tini
RUN apt-get update && apt-get install -y --no-install-recommends \
    tini \
    libpq5 \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# 從構建階段複製依賴
COPY --from=builder /usr/local /usr/local

# 創建非 root 用戶
RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser

WORKDIR /app

# 複製應用代碼（先複製依賴相關文件以利用緩存）
COPY main.py ./
COPY src/ ./src/
COPY strategies/ ./strategies/
COPY migrations/ ./migrations/
COPY alembic.ini ./
COPY celery_worker.py ./

# 再複製其他文件
COPY static/ ./static/
COPY templates/ ./templates/ 2>/dev/null || true
COPY data/ ./data/ 2>/dev/null || true

# 數據目錄（確保權限正確）
RUN mkdir -p /app/data /app/logs && \
    chown -R appuser:appuser /app

# 切換到非 root 用戶
USER appuser

# 環境變量
ENV SQ_DB_PATH=/app/data/stock.db
ENV SQ_LOG_DIR=/app/logs
ENV SQ_WEB_HOST=0.0.0.0
ENV SQ_WEB_PORT=8000
# 生產默認關閉演示；Render/Compose 可覆寫 SQ_DEMO_MODE=true
ENV SQ_DEMO_MODE=false
ENV SQ_HISTORY_START_DATE=20230101
ENV PYTHONUNBUFFERED=1
# OpenTelemetry 配置
ENV OTEL_SERVICE_NAME=stock-quant
ENV OTEL_TRACES_EXPORTER=console
ENV OTEL_METRICS_EXPORTER=console
ENV OTEL_PYTHON_LOGGING_AUTO_INSTRUMENTATION_ENABLED=true

EXPOSE 8000

# 健康檢查
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import json,urllib.request; d=json.load(urllib.request.urlopen('http://127.0.0.1:8000/api/health/sop',timeout=4)); v=(d.get('sop')or{}).get('verdict'); raise SystemExit(0 if v in ('ok','attention') else 1)"

# 使用 tini 作為 PID 1（正確處理信號）
ENTRYPOINT ["tini", "--"]
CMD ["python", "main.py", "serve"]
