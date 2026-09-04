"""計算預算管理測試。"""

from src.core.compute_budget import (
    HEAVY_TASK_TYPES,
    cpu_count,
    get_process_workers,
    get_thread_workers,
    should_parallelize_optimize_all,
)


def test_heavy_task_types_cover_backtest_family():
    assert "backtest" in HEAVY_TASK_TYPES
    assert "optimize" in HEAVY_TASK_TYPES
    assert "walkforward" in HEAVY_TASK_TYPES
    assert "portfolio" in HEAVY_TASK_TYPES


def test_cpu_count_positive():
    assert cpu_count() >= 1


def test_process_workers_capped(monkeypatch):
    monkeypatch.setattr("src.core.compute_budget.cpu_count", lambda: 8)
    monkeypatch.setattr("src.core.compute_budget.count_running_heavy_tasks", lambda exclude_task_id=None: 2)
    w = get_process_workers(per_job_cap=16, min_workers=1)
    assert 1 <= w <= 16


def test_thread_workers_respects_configured(monkeypatch):
    monkeypatch.setattr("src.core.compute_budget.cpu_count", lambda: 4)
    monkeypatch.setattr("src.core.compute_budget.count_running_tasks", lambda exclude_task_id=None: 1)
    assert get_thread_workers(2) <= 2


def test_should_parallelize_optimize_all_off_by_default():
    assert should_parallelize_optimize_all() is False
