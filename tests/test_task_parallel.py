"""任務並行派發測試 — 驗證 _drain_queue 不雙重計數 in_flight"""
import threading
import time
import uuid

import pytest

from src.core.task_manager import (
    STATUS_RUNNING,
    _count_active,
    _count_in_flight,
    _resolve_max_workers,
    count_in_flight_tasks,
    create_task,
    get_task,
    submit_task,
)


@pytest.fixture
def max_workers_3(monkeypatch):
    monkeypatch.setattr(
        "src.core.task_manager._resolve_max_workers",
        lambda: 3,
    )
    monkeypatch.setattr(
        "src.core.task_manager._resolve_heavy_max_concurrent",
        lambda: 3,
    )


def test_count_in_flight_not_double_running():
    tid = uuid.uuid4().hex[:8]
    task = create_task(
        "backtest",
        {"code": "000001", "_pytest": tid},
        title="parallel single",
    )
    task_id = task["task_id"]
    gate = threading.Event()

    def work():
        gate.set()
        time.sleep(0.2)

    submit_task(task_id, work)
    assert gate.wait(timeout=5), "worker 應已啟動"
    t = get_task(task_id)
    assert t and t["status"] == STATUS_RUNNING

    active = _count_active()
    in_flight = _count_in_flight()
    assert in_flight >= 1
    assert in_flight <= _resolve_max_workers()
    assert in_flight <= max(active, 1)


def test_drain_dispatches_up_to_max_workers(max_workers_3):
    """連續提交 3 個任務後，in_flight 應能達到 3（修復前約只能到 1～2）。"""
    ids = []
    started = threading.Barrier(3, timeout=8)

    def make_worker():
        def work():
            started.wait()
            time.sleep(0.15)
        return work

    for i in range(3):
        created = create_task(
            "backtest",
            {"code": "000001", "_pytest_batch": uuid.uuid4().hex},
            title=f"parallel batch {i}",
        )
        ids.append(created["task_id"])
        submit_task(ids[-1], make_worker())

    deadline = time.time() + 6
    peak = 0
    while time.time() < deadline:
        peak = max(peak, count_in_flight_tasks())
        if peak >= 3:
            break
        time.sleep(0.02)

    assert peak >= 3, f"預期同時 in_flight>=3，實際 peak={peak}"
