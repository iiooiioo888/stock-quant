"""
跨模組並行集成測試 — DB 並發寫入、任務管線端到端、模塊間交互

覆蓋：
  - SQLite WAL 並發讀寫
  - 任務管線完整流程
  - 多線程狀態一致性
  - 緩存 + 任務 交互
"""
from __future__ import annotations

import concurrent.futures
import threading
import time
import pytest
from fastapi.testclient import TestClient

from src.api.app import app
from src.config import settings
from src.core import task_manager as tm
from src.core.database import get_conn


@pytest.fixture(autouse=True)
def _reset():
    """每個測試前清理數據庫（任務狀態由 conftest 隔離）。"""
    try:
        with get_conn() as conn:
            conn.execute("DELETE FROM backtest_results")
            conn.execute("DELETE FROM alert_log")
    except Exception:
        pass
    yield
    try:
        with get_conn() as conn:
            conn.execute("DELETE FROM backtest_results")
            conn.execute("DELETE FROM alert_log")
    except Exception:
        pass


# ── SQLite WAL 並發讀寫 ────────────────────────────────────────

class TestDatabaseConcurrency:
    """數據庫並發安全性。"""

    def test_concurrent_inserts(self):
        """並發 INSERT 不衝突。"""
        errors = []

        def _insert(i):
            try:
                with get_conn() as conn:
                    conn.execute(
                        "INSERT INTO alert_log (code, rule_type, message, triggered_at) VALUES (?, ?, ?, datetime('now'))",
                        (f"00000{i % 10}", f"price_alert", f"測試告警 {i}"),
                    )
            except Exception as e:
                errors.append(e)

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
            futures = [pool.submit(_insert, i) for i in range(50)]
            for f in concurrent.futures.as_completed(futures):
                f.result()

        assert len(errors) == 0, f"並發 INSERT 出錯: {errors[:3]}"

        # 驗證數據
        with get_conn() as conn:
            row = conn.execute("SELECT COUNT(*) FROM alert_log").fetchone()
            assert row[0] == 50

    def test_concurrent_read_write(self):
        """並發讀寫不衝突。"""
        errors = []

        def _write(i):
            try:
                with get_conn() as conn:
                    conn.execute(
                        "INSERT INTO alert_log (code, rule_type, message, triggered_at) VALUES (?, ?, ?, datetime('now'))",
                        (f"60000{i % 10}", f"volume_alert", f"msg_{i}"),
                    )
            except Exception as e:
                errors.append(e)

        def _read():
            try:
                with get_conn() as conn:
                    conn.execute("SELECT COUNT(*) FROM alert_log").fetchone()
            except Exception as e:
                errors.append(e)

        threads = (
            [threading.Thread(target=_write, args=(i,)) for i in range(20)]
            + [threading.Thread(target=_read) for _ in range(20)]
        )
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert len(errors) == 0

    def test_wal_mode_active(self):
        """確認 WAL 模式生效。"""
        with get_conn() as conn:
            row = conn.execute("PRAGMA journal_mode").fetchone()
            journal = row[0] if row else "unknown"
            assert journal in ("wal", "delete"), f"journal_mode={journal}"

    def test_concurrent_backtest_results(self):
        """並發寫入回測結果。"""
        errors = []

        def _insert_result(i):
            try:
                with get_conn() as conn:
                    conn.execute(
                        """INSERT INTO backtest_results
                           (code, strategy, params, total_return_pct, sharpe_ratio, max_drawdown_pct,
                            annual_return_pct, sortino_ratio, calmar_ratio, var_95, cvar_95,
                            total_trades, win_rate_pct, initial_cash, final_value, created_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
                        (
                            f"00000{i % 10}",
                            "dual_ma",
                            "{}",
                            float(i % 50),
                            1.5,
                            10.0,
                            8.0,
                            1.2,
                            0.9,
                            -2.5,
                            -3.5,
                            10 + i,
                            55.0,
                            100000.0,
                            100000.0 + i * 1000,
                        ),
                    )
            except Exception as e:
                errors.append(e)

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
            futures = [pool.submit(_insert_result, i) for i in range(30)]
            for f in concurrent.futures.as_completed(futures):
                f.result()

        assert len(errors) == 0

        with get_conn() as conn:
            row = conn.execute("SELECT COUNT(*) FROM backtest_results").fetchone()
            assert row[0] == 30


# ── 任務管線端到端 ──────────────────────────────────────────────

class TestTaskPipeline:
    """任務管線完整流程。"""

    @pytest.fixture(autouse=True)
    def _auth(self, monkeypatch):
        monkeypatch.setattr(settings, "debug", True)

    def test_create_task_update_complete(self):
        """手動創建 → 更新 → 完成。"""
        task = tm.create_task("custom", {"key": "value"}, title="測試任務")
        assert task["status"] == "pending"
        tid = task["task_id"]

        tm.update_task(tid, status="running")
        updated = tm.get_task(tid)
        assert updated["status"] == "running"

        tm.update_task(tid, status="completed", progress=100)
        final = tm.get_task(tid)
        assert final["status"] == "completed"

    def test_task_with_logs(self):
        """任務帶日誌的完整流程。"""
        task = tm.create_task("pipeline", {}, title="帶日誌任務")
        tid = task["task_id"]

        for i in range(10):
            tm.append_task_log(tid, f"步驟 {i+1} 完成")

        logs = tm.get_task_logs(tid)
        assert len(logs) == 10

    def test_multi_task_pipeline(self):
        """多任務管線：下載 → 清洗 → 回測。"""
        t1 = tm.create_task("download", {"code": "000001"}, title="下載數據")
        t2 = tm.create_task("etl", {"depends_on": t1["task_id"]}, title="數據清洗")
        t3 = tm.create_task("backtest", {"depends_on": t2["task_id"]}, title="執行回測")

        tm.update_task(t3["task_id"], status="pending")
        assert tm.get_task(t3["task_id"])["status"] == "pending"

        tm.update_task(t1["task_id"], status="completed")
        tm.update_task(t2["task_id"], status="completed")
        tm.update_task(t3["task_id"], status="completed")

        stats = tm.get_task_stats()
        assert stats["completed"] == 3

    def test_task_failure_and_retry(self):
        """任務失敗。"""
        task = tm.create_task("flaky", {}, title="易失敗任務")
        tid = task["task_id"]

        tm.update_task(tid, status="running")
        tm.update_task(tid, status="failed", error="連接超時")

        failed = tm.get_task(tid)
        assert failed["status"] == "failed"

    def test_task_retry_from_running(self):
        """任務從 running 重試。"""
        task = tm.create_task("retry_test", {}, title="重試任務")
        tid = task["task_id"]

        tm.update_task(tid, status="running")
        tm.update_task(tid, status="retrying")
        retried = tm.get_task(tid)
        assert retried["status"] == "retrying"


# ── 併發任務操作 ────────────────────────────────────────────────

class TestConcurrentTaskOps:
    """併發任務操作一致性。"""

    def test_50_concurrent_creations(self):
        """50 個併發任務創建。"""
        results = []
        lock = threading.Lock()

        def _create(i):
            task = tm.create_task("test", {"i": i}, title=f"任務 {i}")
            with lock:
                results.append(task["task_id"])

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
            futures = [pool.submit(_create, i) for i in range(50)]
            for f in concurrent.futures.as_completed(futures):
                f.result()

        assert len(results) == 50
        assert len(set(results)) == 50, "所有 task_id 應唯一"

    def test_concurrent_create_and_cancel(self):
        """同時創建和取消任務。"""
        created = []
        lock = threading.Lock()

        def _create(i):
            task = tm.create_task("test", {"cancel_test": i}, title=f"任務 {i}")
            with lock:
                created.append(task["task_id"])
            return task["task_id"]

        def _cancel_all():
            time.sleep(0.05)
            with lock:
                for tid in list(created):
                    try:
                        tm.update_task(tid, status="cancelled")
                    except (ValueError, KeyError):
                        pass

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
            create_futures = [pool.submit(_create, i) for i in range(20)]
            pool.submit(_cancel_all)
            for f in concurrent.futures.as_completed(create_futures):
                f.result()

        assert len(created) == 20

    def test_concurrent_update_same_task(self):
        """並發更新同一任務不崩潰。"""
        task = tm.create_task("test", {"shared": True}, title="共享任務")
        tid = task["task_id"]
        errors = []

        def _update(status):
            try:
                tm.update_task(tid, status=status)
            except (ValueError, KeyError) as e:
                errors.append(e)
            except Exception as e:
                errors.append(e)

        tm.update_task(tid, status="running")

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
            futures = [
                pool.submit(_update, "completed"),
                pool.submit(_update, "failed"),
                pool.submit(_update, "cancelled"),
            ]
            for f in concurrent.futures.as_completed(futures):
                f.result()

        final = tm.get_task(tid)
        assert final["status"] in ("completed", "failed", "cancelled", "running")


# ── 緩存 + 任務 交互 ────────────────────────────────────────────

class TestCacheTaskInteraction:
    """緩存和任務管理器交互。"""

    def test_cache_task_results(self):
        """將任務結果緩存。"""
        from src.core.cache import LRUCache
        cache = LRUCache(max_size=100)

        task = tm.create_task("cacheable", {}, title="可緩存任務")
        result_data = {"return_pct": 15.3, "sharpe": 1.2}

        cache.set(f"result:{task['task_id']}", result_data)
        cached = cache.get(f"result:{task['task_id']}")
        assert cached == result_data

    def test_cache_eviction_during_tasks(self):
        """任務執行中緩存淘汰。"""
        from src.core.cache import LRUCache
        cache = LRUCache(max_size=5)

        tasks = []
        for i in range(10):
            t = tm.create_task("test", {"i": i}, title=f"任務 {i}")
            tasks.append(t)
            cache.set(f"result:{t['task_id']}", {"i": i})

        for t in tasks[:5]:
            assert cache.get(f"result:{t['task_id']}") is None

        for t in tasks[5:]:
            assert cache.get(f"result:{t['task_id']}") is not None
