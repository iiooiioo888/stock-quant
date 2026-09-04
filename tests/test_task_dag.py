"""
任務依賴 DAG 測試 — depends_on 把關、失敗傳播、扇入扇出、循環檢測
"""

import threading
import time
import uuid

import pytest

from src.core.task_manager import (
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_RUNNING,
    create_dag,
    create_task,
    get_task,
    submit_task,
)


def _wait_status(task_id: str, statuses: tuple[str, ...], timeout: float = 8.0) -> dict:
    """輪詢等待任務進入指定狀態"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        t = get_task(task_id)
        if t and t.get("status") in statuses:
            return t
        time.sleep(0.05)
    raise AssertionError(f"任務 {task_id} 未在 {timeout}s 內進入 {statuses}")


def test_create_dag_validation():
    """節點校驗：重複 id / 未知依賴 / 自我依賴 / 循環依賴"""
    with pytest.raises(ValueError, match="重複"):
        create_dag(
            [
                {"id": "a", "task_type": "backtest"},
                {"id": "a", "task_type": "backtest"},
            ]
        )
    with pytest.raises(ValueError, match="未知節點"):
        create_dag(
            [
                {"id": "a", "task_type": "backtest", "depends_on": ["ghost"]},
            ]
        )
    with pytest.raises(ValueError, match="自身"):
        create_dag(
            [
                {"id": "a", "task_type": "backtest", "depends_on": ["a"]},
            ]
        )
    with pytest.raises(ValueError, match="循環"):
        create_dag(
            [
                {"id": "a", "task_type": "backtest", "depends_on": ["b"]},
                {"id": "b", "task_type": "backtest", "depends_on": ["a"]},
            ]
        )


def test_dag_dependency_gating_and_completion():
    """b 依賴 a：a 完成前 b 保持 pending；a 完成後 b 自動派發"""
    tag = uuid.uuid4().hex[:8]
    dag = create_dag(
        [
            {
                "id": "a",
                "task_type": "backtest",
                "params": {"code": "000001", "_t": tag, "n": "a"},
            },
            {
                "id": "b",
                "task_type": "backtest",
                "params": {"code": "000001", "_t": tag, "n": "b"},
                "depends_on": ["a"],
            },
        ],
        title="測試 DAG",
    )
    a_id, b_id = dag["tasks"]["a"], dag["tasks"]["b"]
    assert dag["edges"] == [[a_id, b_id]]

    # b 的 meta 應記錄依賴
    b_task = get_task(b_id)
    assert (b_task.get("meta") or {}).get("depends_on") == [a_id]

    gate_a = threading.Event()
    b_started = threading.Event()

    def work_a():
        gate_a.wait(timeout=5)
        return {"ok": True}

    def work_b():
        b_started.set()
        return {"ok": True}

    submit_task(a_id, work_a)
    submit_task(b_id, work_b)

    # a 尚未完成 → b 不得派發
    time.sleep(0.3)
    assert not b_started.is_set(), "依賴未完成前 b 不應啟動"
    assert get_task(b_id)["status"] == STATUS_PENDING

    # a 完成 → b 應被自動派發
    gate_a.set()
    _wait_status(a_id, (STATUS_COMPLETED,))
    assert b_started.wait(timeout=5), "a 完成後 b 應自動派發"
    _wait_status(b_id, (STATUS_COMPLETED,))


def test_dag_failure_propagation():
    """上游失敗 → 下游自動標記失敗（依賴失敗傳播）"""
    tag = uuid.uuid4().hex[:8]
    dag = create_dag(
        [
            {
                "id": "a",
                "task_type": "backtest",
                "params": {"code": "000002", "_t": tag, "n": "a"},
            },
            {
                "id": "b",
                "task_type": "backtest",
                "params": {"code": "000002", "_t": tag, "n": "b"},
                "depends_on": ["a"],
            },
            {
                "id": "c",
                "task_type": "backtest",
                "params": {"code": "000002", "_t": tag, "n": "c"},
                "depends_on": ["b"],
            },
        ],
        title="失敗傳播鏈",
    )
    a_id, b_id, c_id = (dag["tasks"][k] for k in ("a", "b", "c"))

    def work_fail():
        raise RuntimeError("模擬上游爆炸")

    submit_task(a_id, work_fail)
    submit_task(b_id, lambda: {"ok": True})
    submit_task(c_id, lambda: {"ok": True})

    a_final = _wait_status(a_id, (STATUS_FAILED,))
    assert "模擬上游爆炸" in (a_final.get("error") or "")

    b_final = _wait_status(b_id, (STATUS_FAILED,))
    assert "依賴任務失敗" in (b_final.get("error") or "")

    # 失敗沿鏈傳播到 c
    c_final = _wait_status(c_id, (STATUS_FAILED,))
    assert "依賴任務失敗" in (c_final.get("error") or "")


def test_dag_fan_in():
    """扇入：c 需等待 a、b 都完成才派發"""
    tag = uuid.uuid4().hex[:8]
    dag = create_dag(
        [
            {
                "id": "a",
                "task_type": "backtest",
                "params": {"code": "000003", "_t": tag, "n": "a"},
            },
            {
                "id": "b",
                "task_type": "backtest",
                "params": {"code": "000003", "_t": tag, "n": "b"},
            },
            {
                "id": "c",
                "task_type": "backtest",
                "params": {"code": "000003", "_t": tag, "n": "c"},
                "depends_on": ["a", "b"],
            },
        ],
        title="扇入測試",
    )
    a_id, b_id, c_id = (dag["tasks"][k] for k in ("a", "b", "c"))

    gate_b = threading.Event()
    c_started = threading.Event()

    submit_task(a_id, lambda: {"ok": True})
    submit_task(b_id, lambda: (gate_b.wait(timeout=5), {"ok": True})[1])
    submit_task(c_id, lambda: (c_started.set(), {"ok": True})[1])

    # a 完成但 b 未完成 → c 仍等待
    _wait_status(a_id, (STATUS_COMPLETED,))
    time.sleep(0.3)
    assert not c_started.is_set(), "b 未完成前 c 不應啟動"

    gate_b.set()
    _wait_status(b_id, (STATUS_COMPLETED,))
    assert c_started.wait(timeout=5), "a、b 均完成後 c 應派發"
    _wait_status(c_id, (STATUS_COMPLETED,))


def test_dag_missing_dependency_fails():
    """依賴不存在的 task_id → 任務標記失敗"""
    tag = uuid.uuid4().hex[:8]
    created = create_task(
        "backtest",
        {"code": "000004", "_t": tag},
        title="缺失依賴",
        depends_on=["task_not_exist_123"],
    )
    task_id = created["task_id"]
    submit_task(task_id, lambda: {"ok": True})
    final = _wait_status(task_id, (STATUS_FAILED,))
    assert "依賴任務不存在" in (final.get("error") or "")


@pytest.fixture
def auth_headers(client):
    """註冊並登錄，返回 Authorization header"""
    pw = "test_task_dag_pw_2026"
    username = f"dagtester_{uuid.uuid4().hex[:8]}"
    client.post("/api/auth/register", json={"username": username, "password": pw})
    resp = client.post("/api/auth/login", json={"username": username, "password": pw})
    assert resp.status_code == 200
    token = resp.json().get("token")
    assert token
    return {"Authorization": f"Bearer {token}"}


def test_dag_api(client, auth_headers):
    """POST /api/tasks/dag 端點契約測試"""
    tag = uuid.uuid4().hex[:8]
    resp = client.post(
        "/api/tasks/dag",
        headers=auth_headers,
        json={
            "title": "API DAG",
            "auto_dispatch": False,
            "nodes": [
                {"id": "dl", "task_type": "data_incremental", "params": {"_t": tag}},
                {
                    "id": "bt",
                    "task_type": "backtest",
                    "params": {"code": "000001", "_t": tag},
                    "depends_on": ["dl"],
                },
            ],
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["success"] is True
    assert set(data["tasks"].keys()) == {"dl", "bt"}
    assert data["topo_order"] == ["dl", "bt"]
    assert len(data["edges"]) == 1

    # 循環依賴 → 400
    resp2 = client.post(
        "/api/tasks/dag",
        headers=auth_headers,
        json={
            "nodes": [
                {"id": "x", "task_type": "backtest", "depends_on": ["y"]},
                {"id": "y", "task_type": "backtest", "depends_on": ["x"]},
            ]
        },
    )
    assert resp2.status_code == 400
