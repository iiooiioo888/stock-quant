"""任務管理器增強：狀態機、日誌、批次操作、管道、自癒"""
import time
import uuid

import pytest

from src.core.task_manager import (
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_RETRYING,
    STATUS_RUNNING,
    append_task_log,
    can_transition,
    cancel_all_pending,
    cleanup_stale_tasks,
    create_pipeline,
    create_task,
    delete_all_completed,
    get_task_logs,
    normalize_status,
    submit_task,
    transition_task,
    update_task,
)


def test_status_machine_transitions():
    assert normalize_status("success") == STATUS_COMPLETED
    assert can_transition(STATUS_PENDING, STATUS_RUNNING)
    assert can_transition(STATUS_RUNNING, STATUS_RETRYING)
    assert not can_transition(STATUS_COMPLETED, STATUS_RUNNING)


def test_append_task_log_ring_buffer():
    tid = f"log_{uuid.uuid4().hex[:8]}"
    for i in range(3):
        append_task_log(tid, f"line {i}")
    logs = get_task_logs(tid)
    assert len(logs) == 3
    assert "line 2" in logs[-1]["message"]


def test_cancel_all_pending():
    t1 = create_task("backtest", {"code": "000001", "_t": uuid.uuid4().hex}, title="p1")
    t2 = create_task("backtest", {"code": "000002", "_t": uuid.uuid4().hex}, title="p2")
    assert t1["status"] == STATUS_PENDING
    n = cancel_all_pending()
    assert n >= 2
    from src.core.task_manager import get_task
    assert get_task(t1["task_id"])["status"] == STATUS_CANCELLED


def test_delete_all_completed():
    t = create_task("backtest", {"code": "000003", "_t": uuid.uuid4().hex}, title="done")
    update_task(t["task_id"], status=STATUS_COMPLETED, progress=100, result={"ok": True})
    n = delete_all_completed()
    assert n >= 1


def test_cleanup_stale_tasks_timeout(monkeypatch):
    monkeypatch.setattr("src.core.task_manager._resolve_task_timeout", lambda: 1)
    task = create_task("optimize", {"code": "000004", "_t": uuid.uuid4().hex}, title="stale")
    tid = task["task_id"]
    update_task(tid, status=STATUS_RUNNING, progress=50)
    with __import__("src.core.task_manager", fromlist=["_lock"])._lock:
        __import__("src.core.task_manager", fromlist=["_tasks"])._tasks[tid]["last_accessed"] = time.time() - 5
    cleaned = cleanup_stale_tasks(1)
    assert cleaned >= 1
    from src.core.task_manager import get_task
    assert get_task(tid)["status"] == STATUS_FAILED


def test_transition_retrying():
    task = create_task("backtest", {"code": "000005", "_t": uuid.uuid4().hex}, title="retry")
    tid = task["task_id"]
    update_task(tid, status=STATUS_RUNNING, progress=10)
    out = transition_task(tid, STATUS_RETRYING)
    assert out["status"] == STATUS_RETRYING


def test_pipeline_registers_meta(monkeypatch):
    monkeypatch.setattr(
        "src.core.task_retry.build_retry_worker",
        lambda task_type, params, task_id: lambda: {"pipeline_ok": True},
    )
    steps = [
        {"task_type": "backtest", "params": {"code": "000001", "strategy": "dual_ma"}, "title": "步驟1"},
        {"task_type": "backtest", "params": {"code": "000002", "strategy": "dual_ma"}, "title": "步驟2", "pass_result": True},
    ]
    pipe = create_pipeline(steps, title="pytest 管道")
    assert pipe.get("pipeline_id")
    assert pipe.get("steps") == 2
    from src.core.task_manager import get_task_full
    full = get_task_full(pipe["task_id"], include_result=False)
    assert full["meta"].get("pipeline_id") == pipe["pipeline_id"]


def test_heavy_task_queue_respects_limit(monkeypatch):
    monkeypatch.setattr("src.core.task_manager._resolve_max_workers", lambda: 4)
    monkeypatch.setattr("src.core.task_manager._resolve_heavy_max_concurrent", lambda: 1)
    gates = []

    def make_gate():
        import threading
        g = threading.Event()
        gates.append(g)
        return lambda: (g.set(), time.sleep(0.3))

    ids = []
    for i in range(2):
        c = create_task(
            "backtest",
            {"code": "000001", "_heavy": uuid.uuid4().hex, "i": i},
            title=f"heavy {i}",
        )
        ids.append(c["task_id"])
        submit_task(ids[-1], make_gate())

    time.sleep(0.15)
    from src.core.task_manager import count_in_flight_heavy
    assert count_in_flight_heavy() <= 1
    for g in gates:
        g.wait(timeout=5)
    time.sleep(0.35)
