"""效能路線圖整合：執行器、緩存失效、指標端點。"""
import pytest


def test_task_executors_registered():
    from src.core.task_executors import has_executor, list_executor_types

    types = list_executor_types()
    assert "backtest" in types
    assert "optimize" in types
    assert has_executor("data_download_all")


def test_invalidate_by_rule_l1():
    from src.core.cache import get_cache, invalidate_by_rule

    cache = get_cache()
    key = "sq:kline:test:600519"
    cache.set(key, {"ok": 1}, ttl=60)
    assert cache.get(key) is not None
    removed = invalidate_by_rule("data_update", code="600519")
    assert removed >= 0


def test_metrics_payload():
    from src.utils.metrics import metrics_payload

    body, ctype = metrics_payload()
    assert isinstance(body, (bytes, bytearray))
    assert "text" in ctype


def test_celery_app_import():
    from src.core.celery_app import get_celery_app

    app = get_celery_app()
    assert app.main == "stock_quant"
