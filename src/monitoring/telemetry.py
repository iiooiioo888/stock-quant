"""OpenTelemetry 追蹤與監控配置模組"""

from __future__ import annotations
import os
from typing import Optional

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.semconv.trace import SpanAttributes

# 全局追蹤器實例
_tracer: Optional[trace.Tracer] = None


def setup_telemetry(
    service_name: str = "stock-quant",
    traces_exporter: str = "console",
    metrics_exporter: str = "console",
) -> trace.Tracer:
    """
    設置 OpenTelemetry 追蹤
    
    Args:
        service_name: 服務名稱
        traces_exporter: 追蹤導出器 (console/otlp)
        metrics_exporter: 指標導出器 (console/otlp)
    
    Returns:
        配置好的 Tracer 實例
    """
    global _tracer
    
    # 創建 Trace Provider
    provider = TracerProvider()
    
    # 配置導出器
    if traces_exporter == "console":
        exporter = ConsoleSpanExporter()
    else:
        # OTLP 導出器（生產環境使用）
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        exporter = OTLPSpanExporter()
    
    processor = BatchSpanProcessor(exporter)
    provider.add_span_processor(processor)
    
    # 設置全局追蹤提供者
    trace.set_tracer_provider(provider)
    
    # 創建追蹤器
    _tracer = trace.get_tracer(service_name)
    
    return _tracer


def instrument_fastapi(app):
    """為 FastAPI 應用自動注入追蹤"""
    if _tracer is None:
        setup_telemetry()
    
    FastAPIInstrumentor.instrument_app(
        app,
        tracer_provider=trace.get_tracer_provider(),
    )
    
    return app


def get_tracer() -> trace.Tracer:
    """獲取當前追蹤器實例"""
    if _tracer is None:
        return setup_telemetry()
    return _tracer


def trace_context(operation: str, **attributes):
    """
    上下文管理器裝飾器，用於追蹤操作
    
    Usage:
        with trace_context("db_query", table="users"):
            # 執行數據庫查詢
            pass
    """
    tracer = get_tracer()
    return tracer.start_as_current_span(operation, attributes=attributes)
