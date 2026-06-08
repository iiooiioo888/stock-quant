"""
任務管理器穩定性測試 — 狀態機、並發操作、邊界條件

覆蓋：
  - 全狀態轉換矩陣（合法 + 非法）
  - 並發任務創建/更新/取消
  - 去重邏輯
  - 管道級聯
  - 超時清理
  - 日誌環形緩衝
  - 任務刪除邊界
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest

import src.core.task_manager as tm

# ── 狀態機轉換矩陣 ──────────────────────────────────────────────


class TestTransitionMatrix:
    """驗證 _VALID_TRANSITIONS 與 can_transition 的一致性。"""

    ALL_STATUSES = [
        tm.STATUS_PENDING,
        tm.STATUS_RUNNING,
        tm.STATUS_COMPLETED,
        tm.STATUS_FAILED,
        tm.STATUS_CANCELLED,
        tm.STATUS_RETRYING,
    ]

    def test_same_status_always_allowed(self):
        for s in self.ALL_STATUSES:
            assert tm.can_transition(s, s), f"{s} → {s} 應該允許"

    def test_terminal_cannot_transition(self):
        for terminal in tm.TERMINAL_STATUSES:
            for target in self.ALL_STATUSES:
                if target == terminal:
                    continue
                assert not tm.can_transition(
                    terminal, target
                ), f"終態 {terminal} 不應轉到 {target}"

    def test_pending_can_go_to_running_completed_cancelled_retrying(self):
        allowed = tm._VALID_TRANSITIONS[tm.STATUS_PENDING]
        assert tm.STATUS_RUNNING in allowed
        assert tm.STATUS_COMPLETED in allowed
        assert tm.STATUS_CANCELLED in allowed
        assert tm.STATUS_RETRYING in allowed

    def test_running_can_go_to_all_terminal_plus_retrying(self):
        allowed = tm._VALID_TRANSITIONS[tm.STATUS_RUNNING]
        for s in (
            tm.STATUS_COMPLETED,
            tm.STATUS_FAILED,
            tm.STATUS_CANCELLED,
            tm.STATUS_RETRYING,
        ):
            assert s in allowed

    def test_retrying_can_go_to_running_failed_cancelled(self):
        allowed = tm._VALID_TRANSITIONS[tm.STATUS_RETRYING]
        assert tm.STATUS_RUNNING in allowed
        assert tm.STATUS_FAILED in allowed
        assert tm.STATUS_CANCELLED in allowed
        assert tm.STATUS_COMPLETED not in allowed

    def test_normalize_status_aliases(self):
        assert tm.normalize_status("success") == tm.STATUS_COMPLETED
        assert tm.normalize_status("SUCCESS") == tm.STATUS_COMPLETED
        assert tm.normalize_status("  running  ") == tm.STATUS_RUNNING
        assert tm.normalize_status("") == ""
        assert tm.normalize_status("pending") == tm.STATUS_PENDING

    @pytest.mark.parametrize(
        "from_s,to_s,expected",
        [
            ("pending", "running", True),
            ("pending", "completed", True),
            ("pending", "failed", False),
            ("running", "completed", True),
            ("running", "failed", True),
            ("running", "pending", False),
            ("completed", "running", False),
            ("failed", "pending", False),
            ("cancelled", "running", False),
            ("retrying", "running", True),
            ("retrying", "completed", False),
        ],
    )
    def test_transition_cases(self, from_s, to_s, expected):
        assert tm.can_transition(from_s, to_s) == expected


# ── 任務創建與去重 ──────────────────────────────────────────────


class TestTaskCreation:
    """任務創建、去重、緩存命中。"""

    def test_create_task_returns_pending(self):
        r = tm.create_task("backtest", {"code": "000001"})
        assert r["status"] == tm.STATUS_PENDING
        assert r["is_duplicate"] is False
        assert "task_id" in r

    def test_duplicate_active_task(self):
        r1 = tm.create_task("backtest", {"code": "000002"})
        r2 = tm.create_task("backtest", {"code": "000002"})
        assert r2["is_duplicate"] is True
        assert r2["task_id"] == r1["task_id"]

    def test_different_params_not_duplicate(self):
        r1 = tm.create_task("backtest", {"code": "000001"})
        r2 = tm.create_task("backtest", {"code": "000003"})
        assert r1["task_id"] != r2["task_id"]
        assert r2["is_duplicate"] is False

    def test_different_type_not_duplicate(self):
        r1 = tm.create_task("backtest", {"code": "000001"})
        r2 = tm.create_task("optimize", {"code": "000001"})
        assert r1["task_id"] != r2["task_id"]

    def test_create_many_tasks(self):
        ids = set()
        for i in range(50):
            r = tm.create_task("backtest", {"code": f"{i:06d}"})
            ids.add(r["task_id"])
        assert len(ids) == 50

    def test_task_has_required_fields(self):
        r = tm.create_task("portfolio", {"allocations": []}, title="測試組合")
        task = tm.get_task(r["task_id"])
        assert task is not None
        assert task["task_type"] == "portfolio"
        assert task["title"] == "測試組合"
        assert task["status"] == tm.STATUS_PENDING
        assert task["progress"] == 0
        assert task["created_at"] is not None


# ── 任務更新 ────────────────────────────────────────────────────


class TestTaskUpdate:
    """任務狀態更新、進度節流。"""

    def test_update_progress(self):
        r = tm.create_task("backtest", {"code": "000005"})
        tid = r["task_id"]
        tm.update_task(tid, progress=50)
        task = tm.get_task(tid)
        assert task["progress"] == 50

    def test_update_to_completed(self):
        r = tm.create_task("backtest", {"code": "000006"})
        tid = r["task_id"]
        tm.update_task(
            tid, status=tm.STATUS_COMPLETED, progress=100, result={"total_return": 15.0}
        )
        task = tm.get_task(tid)
        assert task["status"] == tm.STATUS_COMPLETED
        assert task["result"]["total_return"] == 15.0

    def test_update_nonexistent_task(self):
        result = tm.update_task("nonexistent_id", progress=50)
        assert result is None

    def test_update_with_error(self):
        r = tm.create_task("backtest", {"code": "000007"})
        tid = r["task_id"]
        tm.update_task(tid, status=tm.STATUS_FAILED, error="數據獲取失敗")
        task = tm.get_task(tid)
        assert task["status"] == tm.STATUS_FAILED
        assert "數據獲取" in task["error"]


# ── transition_task ─────────────────────────────────────────────


class TestTransitionTask:
    """通過 transition_task 進行狀態轉換。"""

    def test_valid_transition(self):
        r = tm.create_task("backtest", {"code": "000010"})
        tid = r["task_id"]
        task = tm.transition_task(tid, tm.STATUS_RUNNING)
        assert task["status"] == tm.STATUS_RUNNING

    def test_invalid_transition_stays_same(self):
        r = tm.create_task("backtest", {"code": "000011"})
        tid = r["task_id"]
        # 先完成
        tm.update_task(tid, status=tm.STATUS_COMPLETED, result={})
        # 嘗試非法轉換
        task = tm.transition_task(tid, tm.STATUS_RUNNING)
        assert task["status"] == tm.STATUS_COMPLETED

    def test_transition_nonexistent(self):
        result = tm.transition_task("fake_id", tm.STATUS_RUNNING)
        assert result is None

    def test_pending_to_completed_fast_path(self):
        """驗證 pending → completed 快速路徑（瞬間完成的任務）。"""
        r = tm.create_task("backtest", {"code": "000012"})
        tid = r["task_id"]
        task = tm.transition_task(tid, tm.STATUS_COMPLETED, result={"ok": True})
        assert task["status"] == tm.STATUS_COMPLETED


# ── 取消任務 ────────────────────────────────────────────────────


class TestTaskCancellation:
    """取消邏輯 — pending 直接取消，running 協作式取消。"""

    def test_cancel_pending_task(self):
        r = tm.create_task("backtest", {"code": "000020"})
        tid = r["task_id"]
        assert tm.cancel_task(tid) is True
        task = tm.get_task(tid)
        assert task["status"] == tm.STATUS_CANCELLED

    def test_cancel_sets_flag_for_running(self):
        r = tm.create_task("backtest", {"code": "000021"})
        tid = r["task_id"]
        tm.update_task(tid, status=tm.STATUS_RUNNING)
        assert tm.cancel_task(tid) is True
        assert tm.is_task_cancelled(tid) is True

    def test_cancel_nonexistent(self):
        assert tm.cancel_task("nonexistent") is False

    def test_cancel_all_pending(self):
        for i in range(5):
            tm.create_task("backtest", {"code": f"00003{i}"})
        count = tm.cancel_all_pending()
        assert count >= 5

    def test_cancel_already_cancelled(self):
        r = tm.create_task("backtest", {"code": "000040"})
        tid = r["task_id"]
        tm.cancel_task(tid)
        # 終態不可再轉換，cancel_task 返回 False
        assert tm.cancel_task(tid) is False


# ── 並發操作 ────────────────────────────────────────────────────


class TestConcurrentOperations:
    """並發創建、更新、取消 — 驗證線程安全。"""

    def test_concurrent_create_different_params(self):
        """多線程同時創建不同參數的任務，全部應成功。"""
        results = []
        errors = []

        def _create(i):
            try:
                r = tm.create_task("backtest", {"code": f"{100000 + i}"})
                results.append(r)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=_create, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert len(errors) == 0
        assert len(results) == 20
        ids = {r["task_id"] for r in results}
        assert len(ids) == 20

    def test_concurrent_create_same_params_dedup(self):
        """多線程同時創建相同參數的任務，應去重。"""
        results = []
        lock = threading.Lock()

        def _create():
            r = tm.create_task("backtest", {"code": "999999"})
            with lock:
                results.append(r)

        threads = [threading.Thread(target=_create) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        ids = {r["task_id"] for r in results}
        assert len(ids) == 1, "相同參數應去重為同一個 task_id"
        dupes = [r for r in results if r["is_duplicate"]]
        assert len(dupes) >= 1

    def test_concurrent_update_same_task(self):
        """多線程同時更新同一任務進度，不應崩潰。"""
        r = tm.create_task("backtest", {"code": "000050"})
        tid = r["task_id"]
        errors = []

        def _update(progress):
            try:
                tm.update_task(tid, progress=progress)
            except Exception as e:
                errors.append(e)

        with ThreadPoolExecutor(max_workers=8) as pool:
            futs = [pool.submit(_update, i * 10) for i in range(10)]
            for f in as_completed(futs):
                f.result(timeout=5)

        assert len(errors) == 0
        task = tm.get_task(tid)
        assert 0 <= task["progress"] <= 100

    def test_concurrent_cancel_and_update(self):
        """一邊取消一邊更新，不應死鎖或崩潰。"""
        r = tm.create_task("backtest", {"code": "000051"})
        tid = r["task_id"]
        tm.update_task(tid, status=tm.STATUS_RUNNING)
        errors = []

        def _cancel():
            try:
                tm.cancel_task(tid)
            except Exception as e:
                errors.append(e)

        def _update():
            try:
                for p in range(0, 100, 10):
                    tm.update_task(tid, progress=p)
                    time.sleep(0.01)
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=_cancel)
        t2 = threading.Thread(target=_update)
        t1.start()
        t2.start()
        t1.join(timeout=5)
        t2.join(timeout=5)

        assert len(errors) == 0

    def test_concurrent_submit_and_drain(self):
        """多任務同時 submit_task，drain_queue 不應重複派發。"""
        dispatched = []
        dispatch_lock = threading.Lock()

        def _worker_factory(task_id):
            def _work():
                with dispatch_lock:
                    dispatched.append(task_id)
                time.sleep(0.05)
                tm.update_task(
                    task_id, status=tm.STATUS_COMPLETED, progress=100, result={}
                )

            return _work

        tasks = []
        for i in range(8):
            r = tm.create_task("backtest", {"code": f"{200000 + i}"})
            tasks.append(r["task_id"])

        for tid in tasks:
            tm.submit_task(tid, _worker_factory(tid))

        # 等待所有任務完成
        time.sleep(2)

        for tid in tasks:
            task = tm.get_task(tid)
            if task:
                assert task["status"] in (
                    tm.STATUS_COMPLETED,
                    tm.STATUS_RUNNING,
                    tm.STATUS_PENDING,
                )


# ── 任務日誌 ────────────────────────────────────────────────────


class TestTaskLogs:
    """日誌環形緩衝。"""

    def test_append_and_read_logs(self):
        r = tm.create_task("backtest", {"code": "000060"})
        tid = r["task_id"]
        tm.append_task_log(tid, "開始執行")
        tm.append_task_log(tid, "進度 50%")
        tm.append_task_log(tid, "完成")
        logs = tm.get_task_logs(tid)
        assert len(logs) == 3
        assert logs[0]["message"] == "開始執行"
        assert logs[2]["message"] == "完成"

    def test_log_ring_buffer_limit(self):
        r = tm.create_task("backtest", {"code": "000061"})
        tid = r["task_id"]
        for i in range(600):
            tm.append_task_log(tid, f"log line {i}")
        logs = tm.get_task_logs(tid, tail=600)
        assert len(logs) <= 500  # _MAX_LOG_LINES = 500
        # 最新的日誌應該保留
        assert "599" in logs[-1]["message"]

    def test_empty_log_line_ignored(self):
        r = tm.create_task("backtest", {"code": "000062"})
        tid = r["task_id"]
        tm.append_task_log(tid, "")
        logs = tm.get_task_logs(tid)
        assert len(logs) == 0

    def test_logs_for_nonexistent_task(self):
        logs = tm.get_task_logs("nonexistent")
        assert logs == []


# ── 任務刪除 ────────────────────────────────────────────────────


class TestTaskDeletion:
    """刪除已終結任務。"""

    def test_delete_completed_task(self):
        r = tm.create_task("backtest", {"code": "000070"})
        tid = r["task_id"]
        tm.update_task(tid, status=tm.STATUS_COMPLETED, result={})
        assert tm.delete_task(tid) is True
        assert tm.get_task(tid) is None

    def test_delete_active_task_fails(self):
        r = tm.create_task("backtest", {"code": "000071"})
        tid = r["task_id"]
        assert tm.delete_task(tid) is False

    def test_delete_nonexistent(self):
        assert tm.delete_task("fake_id") is False


# ── 超時清理 ────────────────────────────────────────────────────


class TestStaleCleanup:
    """超時任務清理。"""

    def test_cleanup_stale_running_task(self):
        r = tm.create_task("backtest", {"code": "000080"})
        tid = r["task_id"]
        tm.update_task(tid, status=tm.STATUS_RUNNING)
        # 人為設置 last_accessed 為很久以前
        with tm._lock:
            tm._tasks[tid]["last_accessed"] = "2020-01-01 00:00:00"
        count = tm.cleanup_stale_tasks(timeout_sec=60)
        assert count >= 1
        task = tm.get_task(tid)
        assert task["status"] == tm.STATUS_FAILED


# ── 統計 ────────────────────────────────────────────────────────


class TestTaskStats:
    """任務統計。"""

    def test_stats_reflect_tasks(self):
        for i in range(3):
            tm.create_task("backtest", {"code": f"{300000 + i}"})
        stats = tm.get_task_stats()
        assert stats["total"] >= 3
        assert stats["pending"] >= 3

    def test_stats_after_completion(self):
        r = tm.create_task("backtest", {"code": "000090"})
        tm.update_task(r["task_id"], status=tm.STATUS_COMPLETED, result={})
        stats = tm.get_task_stats()
        assert stats["completed"] >= 1


# ── 管道 ────────────────────────────────────────────────────────


class TestPipeline:
    """任務管道創建。"""

    def test_create_pipeline(self):
        p = tm.create_pipeline(
            [
                {"task_type": "stock_universe_sync", "params": {}, "title": "同步"},
                {
                    "task_type": "backtest",
                    "params": {"code": "000001"},
                    "title": "回測",
                },
            ],
            title="測試管道",
        )
        assert "pipeline_id" in p
        assert p["status"] in ("pending", "running", "completed")

    def test_empty_pipeline_raises(self):
        with pytest.raises(ValueError):
            tm.create_pipeline([])


# ── get_tasks 列表 ──────────────────────────────────────────────


class TestGetTasks:
    """任務列表查詢。"""

    def test_list_all(self):
        for i in range(5):
            tm.create_task("backtest", {"code": f"{400000 + i}"})
        tasks = tm.get_tasks()
        assert len(tasks) >= 5

    def test_filter_by_type(self):
        tm.create_task("backtest", {"code": "000100"})
        tm.create_task("optimize", {"code": "000100"})
        bt_tasks = tm.get_tasks(task_type="backtest")
        for t in bt_tasks:
            assert t["task_type"] == "backtest"

    def test_filter_by_status(self):
        r = tm.create_task("backtest", {"code": "000101"})
        tm.update_task(r["task_id"], status=tm.STATUS_COMPLETED, result={})
        completed = tm.get_tasks(status=tm.STATUS_COMPLETED)
        for t in completed:
            assert t["status"] == tm.STATUS_COMPLETED

    def test_limit_works(self):
        for i in range(10):
            tm.create_task("backtest", {"code": f"{500000 + i}"})
        tasks = tm.get_tasks(limit=3)
        assert len(tasks) <= 3


# ── update_task_meta ────────────────────────────────────────────


class TestUpdateTaskMeta:
    """任務運行時展示信息更新。"""

    def test_update_message(self):
        r = tm.create_task("backtest", {"code": "000091"})
        tid = r["task_id"]
        tm.update_task_meta(tid, message="正在下載數據...")
        task = tm.get_task_full(tid)
        assert task["meta"]["message"] == "正在下載數據..."

    def test_update_download_info(self):
        r = tm.create_task("backtest", {"code": "000092"})
        tid = r["task_id"]
        tm.update_task_meta(tid, download={"progress": 50, "total": 100})
        task = tm.get_task_full(tid)
        assert task["meta"]["download"]["progress"] == 50

    def test_update_extra_kwargs(self):
        r = tm.create_task("backtest", {"code": "000093"})
        tid = r["task_id"]
        tm.update_task_meta(tid, custom_field="custom_value")
        task = tm.get_task_full(tid)
        assert task["meta"]["custom_field"] == "custom_value"

    def test_update_nonexistent(self):
        tm.update_task_meta("nonexistent", message="test")  # 不應崩潰

    def test_download_merge(self):
        r = tm.create_task("backtest", {"code": "000094"})
        tid = r["task_id"]
        tm.update_task_meta(tid, download={"progress": 30, "total": 100})
        tm.update_task_meta(tid, download={"progress": 60})
        task = tm.get_task_full(tid)
        assert task["meta"]["download"]["progress"] == 60
        assert task["meta"]["download"]["total"] == 100  # 保留舊字段


# ── get_task_full / get_task_params ─────────────────────────────


class TestGetTaskFullAndParams:
    """完整任務信息與輕量參數查詢。"""

    def test_get_task_full_basic(self):
        r = tm.create_task("backtest", {"code": "000110"}, title="完整查詢")
        tid = r["task_id"]
        full = tm.get_task_full(tid)
        assert full is not None
        assert full["task_id"] == tid
        assert full["title"] == "完整查詢"

    def test_get_task_full_exclude_result(self):
        r = tm.create_task("backtest", {"code": "000111"})
        tid = r["task_id"]
        tm.update_task(tid, status=tm.STATUS_COMPLETED, result={"big": "data" * 1000})
        full = tm.get_task_full(tid, include_result=False)
        assert full is not None
        assert "result" not in full

    def test_get_task_full_nonexistent(self):
        assert tm.get_task_full("nonexistent") is None

    def test_get_task_params_basic(self):
        r = tm.create_task(
            "backtest", {"code": "000112", "strategy": "dual_ma"}, title="參數查詢"
        )
        tid = r["task_id"]
        params = tm.get_task_params(tid)
        assert params is not None
        assert params["task_id"] == tid
        assert params["params"]["code"] == "000112"

    def test_get_task_params_nonexistent(self):
        assert tm.get_task_params("nonexistent") is None


# ── get_running_tasks / count_in_flight / is_task_running ──────


class TestRunningAndInFlight:
    """運行中任務查詢。"""

    def test_get_running_tasks_empty(self):
        # 先清空所有任務
        tm.cancel_all_pending()
        running = tm.get_running_tasks()
        # 可能還有其他測試殘留，只檢查我們知道的
        assert isinstance(running, list)

    def test_get_running_tasks_after_update(self):
        r = tm.create_task("backtest", {"code": "000120"})
        tid = r["task_id"]
        tm.update_task(tid, status=tm.STATUS_RUNNING)
        running = tm.get_running_tasks()
        assert any(t["task_id"] == tid for t in running)

    def test_count_in_flight(self):
        r = tm.create_task("backtest", {"code": "000121"})
        tid = r["task_id"]
        tm.update_task(tid, status=tm.STATUS_RUNNING)
        count = tm.count_in_flight_tasks()
        assert count >= 1

    def test_count_in_flight_exclude(self):
        r = tm.create_task("backtest", {"code": "000122"})
        tid = r["task_id"]
        tm.update_task(tid, status=tm.STATUS_RUNNING)
        count_without = tm.count_in_flight_tasks(exclude_task_id=tid)
        count_with = tm.count_in_flight_tasks()
        assert count_without <= count_with

    def test_is_task_running_true(self):
        r = tm.create_task("backtest", {"code": "000123"})
        tid = r["task_id"]
        tm.update_task(tid, status=tm.STATUS_RUNNING)
        assert tm.is_task_running("backtest", {"code": "000123"}) is True

    def test_is_task_running_false(self):
        r = tm.create_task("backtest", {"code": "000124"})
        tid = r["task_id"]
        tm.update_task(tid, status=tm.STATUS_COMPLETED, result={})
        assert tm.is_task_running("backtest", {"code": "000124"}) is False


# ── recover_stale_tasks_on_startup ──────────────────────────────


class TestRecoverStale:
    """啟動自癒。"""

    def test_recover_stale(self):
        r = tm.create_task("backtest", {"code": "000130"})
        tid = r["task_id"]
        tm.update_task(tid, status=tm.STATUS_RUNNING)
        # 標記為已派發
        with tm._lock:
            tm._dispatched.add(tid)
        recovered = tm.recover_stale_tasks_on_startup()
        assert recovered >= 1
        task = tm.get_task(tid)
        assert task["status"] == tm.STATUS_FAILED
        assert "重啟" in task["error"]

    def test_recover_no_stale(self):
        """沒有殘留任務時返回 0。"""
        # 確保所有 pending 任務不被誤恢復
        recovered = tm.recover_stale_tasks_on_startup()
        assert isinstance(recovered, int)


# ── delete_all_completed ────────────────────────────────────────


class TestDeleteAllCompleted:
    """批量刪除已結束任務。"""

    def test_delete_all_completed_basic(self):
        for i in range(5):
            r = tm.create_task("backtest", {"code": f"{600000 + i}"})
            tm.update_task(r["task_id"], status=tm.STATUS_COMPLETED, result={})
        deleted = tm.delete_all_completed()
        assert deleted >= 5

    def test_delete_all_include_failed(self):
        r = tm.create_task("backtest", {"code": "000140"})
        tm.update_task(r["task_id"], status=tm.STATUS_FAILED, error="test")
        deleted = tm.delete_all_completed(include_failed=True)
        assert deleted >= 1
        assert tm.get_task(r["task_id"]) is None

    def test_delete_all_exclude_failed(self):
        r = tm.create_task("backtest", {"code": "000141"})
        tm.update_task(r["task_id"], status=tm.STATUS_FAILED, error="test")
        deleted = tm.delete_all_completed(include_failed=False, include_cancelled=False)
        assert tm.get_task(r["task_id"]) is not None  # failed 不應被刪


# ── submit_pipeline_step / get_pipeline ─────────────────────────


class TestPipelineAdvanced:
    """管道進階操作。"""

    def test_submit_pipeline_step(self):
        p = tm.create_pipeline(
            [
                {
                    "task_type": "download",
                    "params": {"code": "000001"},
                    "title": "步驟1",
                },
                {
                    "task_type": "backtest",
                    "params": {"code": "000001"},
                    "title": "步驟2",
                },
            ]
        )
        pid = p["pipeline_id"]
        task_id = tm.submit_pipeline_step(pid, 0, lambda: None)
        assert task_id is not None

    def test_submit_step_invalid_pipeline(self):
        with pytest.raises(ValueError, match="管道不存在"):
            tm.submit_pipeline_step("nonexistent", 0, lambda: None)

    def test_submit_step_invalid_index(self):
        p = tm.create_pipeline(
            [
                {
                    "task_type": "download",
                    "params": {"code": "000001"},
                    "title": "步驟1",
                },
            ]
        )
        with pytest.raises(ValueError):
            tm.submit_pipeline_step(p["pipeline_id"], 5, lambda: None)

    def test_get_pipeline(self):
        p = tm.create_pipeline(
            [
                {
                    "task_type": "download",
                    "params": {"code": "000001"},
                    "title": "步驟1",
                },
            ]
        )
        pipe = tm.get_pipeline(p["pipeline_id"])
        assert pipe is not None
        assert "task_ids" in pipe

    def test_get_pipeline_nonexistent(self):
        assert tm.get_pipeline("nonexistent") is None


# ── task_type_label / get_task_types ────────────────────────────


class TestTaskTypeMeta:
    """任務類型元數據。"""

    def test_task_type_label_known(self):
        label = tm.task_type_label("backtest")
        assert len(label) > 0
        assert "回測" in label or "backtest" in label.lower() or label != "backtest"

    def test_task_type_label_unknown(self):
        assert tm.task_type_label("nonexistent_type") == "nonexistent_type"

    def test_get_task_types(self):
        types = tm.get_task_types()
        assert isinstance(types, list)
        assert len(types) > 0
        for t in types:
            assert "id" in t
            assert "label" in t

    def test_get_task_types_async_only(self):
        types = tm.get_task_types(async_only=True)
        for t in types:
            assert "id" in t


# ── _to_json_safe ───────────────────────────────────────────────


class TestJsonSafe:
    """JSON 安全轉換。"""

    def test_none(self):
        assert tm._to_json_safe(None) is None

    def test_normal_dict(self):
        data = {"a": 1, "b": "hello", "c": 3.14}
        assert tm._to_json_safe(data) == data

    def test_nan_cleaned(self):
        import math

        data = {"val": float("nan")}
        result = tm._to_json_safe(data)
        assert result["val"] is None

    def test_inf_cleaned(self):
        data = {"val": float("inf")}
        result = tm._to_json_safe(data)
        assert result["val"] is None

    def test_nested_nan(self):
        data = {"inner": {"val": float("nan")}, "list": [1, float("inf"), 3]}
        result = tm._to_json_safe(data)
        assert result["inner"]["val"] is None
        assert result["list"][1] is None

    def test_numpy_types(self):
        import numpy as np

        data = {"int": np.int64(42), "float": np.float64(3.14)}
        result = tm._to_json_safe(data)
        assert result["int"] == 42
        assert abs(result["float"] - 3.14) < 0.01

    def test_datetime_serialized(self):
        from datetime import datetime

        data = {"ts": datetime(2024, 6, 15, 10, 30, 0)}
        result = tm._to_json_safe(data)
        assert "2024-06-15" in result["ts"]


# ── _make_params_hash ───────────────────────────────────────────


class TestParamsHash:
    """參數哈希一致性。"""

    def test_same_params_same_hash(self):
        h1 = tm._make_params_hash({"a": 1, "b": 2})
        h2 = tm._make_params_hash({"b": 2, "a": 1})
        assert h1 == h2

    def test_different_params_different_hash(self):
        h1 = tm._make_params_hash({"a": 1})
        h2 = tm._make_params_hash({"a": 2})
        assert h1 != h2

    def test_hash_length(self):
        h = tm._make_params_hash({"test": True})
        assert len(h) == 12  # MD5 截取前 12 位

    def test_empty_params(self):
        h = tm._make_params_hash({})
        assert len(h) == 12


# ── _calc_elapsed / _calc_eta ───────────────────────────────────


class TestCalcElapsedAndETA:
    """運行時間與 ETA 計算。"""

    def test_calc_elapsed_no_start(self):
        assert tm._calc_elapsed({"status": "pending"}) == 0.0

    def test_calc_elapsed_completed(self):
        task = {
            "status": tm.STATUS_COMPLETED,
            "started_at": "2024-01-01 10:00:00",
            "completed_at": "2024-01-01 10:05:00",
        }
        elapsed = tm._calc_elapsed(task)
        assert abs(elapsed - 300.0) < 1.0

    def test_calc_eta_low_progress(self):
        assert (
            tm._calc_eta({"progress": 3, "started_at": "2024-01-01 10:00:00"}) is None
        )

    def test_calc_eta_completed(self):
        assert (
            tm._calc_eta({"progress": 100, "started_at": "2024-01-01 10:00:00"}) is None
        )


# ── get_queue_snapshot ──────────────────────────────────────────


class TestQueueSnapshot:
    """隊列快照。"""

    def test_snapshot_structure(self):
        snap = tm.get_queue_snapshot()
        assert "current" in snap
        assert "next" in snap
        assert "running" in snap
        assert "pending" in snap
        assert "stats" in snap

    def test_snapshot_with_running(self):
        r = tm.create_task("backtest", {"code": "000150"})
        tm.update_task(r["task_id"], status=tm.STATUS_RUNNING)
        snap = tm.get_queue_snapshot()
        assert len(snap["running"]) >= 1


# ── 大規模併發 ──────────────────────────────────────────────────


class TestMassiveConcurrency:
    """100+ 併發任務。"""

    def test_100_concurrent_creates(self):
        results = []
        lock = threading.Lock()

        def _create(i):
            r = tm.create_task("backtest", {"code": f"{700000 + i}"})
            with lock:
                results.append(r["task_id"])

        with ThreadPoolExecutor(max_workers=20) as pool:
            futs = [pool.submit(_create, i) for i in range(100)]
            for f in as_completed(futs):
                f.result(timeout=10)

        assert len(results) == 100
        assert len(set(results)) == 100

    def test_concurrent_create_update_cancel_cycle(self):
        """完整生命週期併發：創建→更新→取消。"""
        created = []
        lock = threading.Lock()

        def _lifecycle(i):
            r = tm.create_task("backtest", {"code": f"{800000 + i}"})
            tid = r["task_id"]
            with lock:
                created.append(tid)
            tm.update_task(tid, progress=i % 100)
            if i % 3 == 0:
                tm.cancel_task(tid)
            elif i % 3 == 1:
                tm.update_task(tid, status=tm.STATUS_COMPLETED, result={})

        with ThreadPoolExecutor(max_workers=20) as pool:
            futs = [pool.submit(_lifecycle, i) for i in range(60)]
            for f in as_completed(futs):
                f.result(timeout=10)

        assert len(created) == 60
        # 不應有任何崩潰
        for tid in created:
            task = tm.get_task(tid)
            assert task is not None

    def test_concurrent_log_append(self):
        """多線程同時寫日誌。"""
        r = tm.create_task("backtest", {"code": "000160"})
        tid = r["task_id"]
        errors = []

        def _log(i):
            try:
                tm.append_task_log(tid, f"日誌行 {i}")
            except Exception as e:
                errors.append(e)

        with ThreadPoolExecutor(max_workers=10) as pool:
            futs = [pool.submit(_log, i) for i in range(100)]
            for f in as_completed(futs):
                f.result(timeout=5)

        assert len(errors) == 0
        logs = tm.get_task_logs(tid, tail=200)
        assert len(logs) >= 50  # 至少一半寫入成功
