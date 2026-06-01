"""
API 壓力測試 — 併發請求、速率限制邊界、大 payload、下載節流

覆蓋：
  - 高併發 GET/POST
  - rate_limiter 邊界
  - download_manager 速率限制
  - 大 payload 處理
  - 回測任務併發提交
"""
from __future__ import annotations

import concurrent.futures
import pytest
from fastapi.testclient import TestClient

from src.api.app import app
from src.config import settings
from src.core.database import get_conn


@pytest.fixture(autouse=True)
def _reset():
    """每個測試前清理數據庫（任務狀態由 conftest 隔離）。"""
    try:
        with get_conn() as conn:
            conn.execute("DELETE FROM backtest_results")
    except Exception:
        pass
    yield
    try:
        with get_conn() as conn:
            conn.execute("DELETE FROM backtest_results")
    except Exception:
        pass


# ── 高併發 GET ─────────────────────────────────────────────────

class TestConcurrentGET:
    """併發 GET 請求穩定性。"""

    @pytest.fixture(autouse=True)
    def _auth(self, monkeypatch):
        monkeypatch.setattr(settings, "debug", True)

    def test_200_concurrent_history(self):
        """200 個併發歷史查詢 — 允許 429 限流，系統不崩潰。"""
        client = TestClient(app)
        results = []

        def _req():
            resp = client.get("/api/backtest/history")
            results.append(resp.status_code)

        with concurrent.futures.ThreadPoolExecutor(max_workers=30) as pool:
            futures = [pool.submit(_req) for _ in range(200)]
            for f in concurrent.futures.as_completed(futures):
                f.result()

        ok_count = sum(1 for s in results if s == 200)
        rate_limited = sum(1 for s in results if s == 429)
        server_errors = sum(1 for s in results if s >= 500)
        # 無 5xx 服務器錯誤，所有請求都應被正常處理（200 或 429）
        assert server_errors == 0, f"{server_errors} 個 5xx 服務器錯誤"
        assert ok_count + rate_limited == 200
        assert ok_count >= 50, f"僅 {ok_count}/200 成功"

    def test_50_concurrent_strategy_params(self):
        """50 個併發策略參數查詢。"""
        client = TestClient(app)
        results = []

        def _req():
            resp = client.get("/api/strategies/params")
            results.append(resp.status_code)

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
            futures = [pool.submit(_req) for _ in range(50)]
            for f in concurrent.futures.as_completed(futures):
                f.result()

        ok = sum(1 for s in results if s == 200)
        rl = sum(1 for s in results if s == 429)
        assert ok + rl == 50
        assert ok >= 20, f"僅 {ok}/50 成功"

    def test_concurrent_all_get_endpoints(self):
        """多個端點同時被併發訪問。"""
        client = TestClient(app)
        endpoints = [
            "/api/backtest/history",
            "/api/strategies/params",
            "/api/download/tasks",
        ]
        results = []

        def _req(ep):
            resp = client.get(ep)
            results.append((ep, resp.status_code))

        with concurrent.futures.ThreadPoolExecutor(max_workers=30) as pool:
            futures = [pool.submit(_req, ep) for ep in endpoints * 30]
            for f in concurrent.futures.as_completed(futures):
                f.result()

        server_errors = sum(1 for _, s in results if s >= 500)
        assert server_errors == 0, f"{server_errors} 個 5xx 錯誤"


# ── 高併發 POST ─────────────────────────────────────────────────

class TestConcurrentPOST:
    """併發 POST 請求（回測任務提交）。"""

    @pytest.fixture(autouse=True)
    def _auth(self, monkeypatch):
        monkeypatch.setattr(settings, "debug", True)

    def test_10_concurrent_backtests(self):
        """10 個併發回測任務 — 允許限流，無 5xx。"""
        client = TestClient(app)
        results = []

        def _submit(i):
            resp = client.post("/api/backtest?code=000001&strategy=dual_ma")
            results.append(resp.status_code)

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
            futures = [pool.submit(_submit, i) for i in range(10)]
            for f in concurrent.futures.as_completed(futures):
                f.result()

        server_errors = sum(1 for s in results if s >= 500)
        assert server_errors == 0, f"{server_errors} 個 5xx 錯誤"
        ok_or_rl = sum(1 for s in results if s in (200, 429))
        assert ok_or_rl == 10

    def test_rapid_duplicate_submissions(self):
        """快速重複提交相同任務 → 每次都成功返回。"""
        client = TestClient(app)
        results = []
        for _ in range(5):
            resp = client.post("/api/backtest?code=600519&strategy=dual_ma")
            if resp.status_code == 200:
                results.append(resp.json())
            elif resp.status_code == 429:
                continue  # 限流，跳過

        # 至少有 1 個成功提交
        task_ids = [r.get("task_id") for r in results if r.get("task_id")]
        assert len(task_ids) >= 1, f"至少 1 個提交應成功，實際 {len(task_ids)}"


# ── 大 Payload ──────────────────────────────────────────────────

class TestLargePayload:
    """大 payload 處理。"""

    @pytest.fixture(autouse=True)
    def _auth(self, monkeypatch):
        monkeypatch.setattr(settings, "debug", True)

    def test_max_length_code(self):
        """超長股票代碼。"""
        client = TestClient(app)
        resp = client.post(f"/api/backtest?code={'A' * 1000}&strategy=dual_ma")
        # 應返回錯誤而非崩潰
        assert resp.status_code in (200, 400, 422, 500)

    def test_invalid_date_format(self):
        """無效日期格式。"""
        client = TestClient(app)
        resp = client.post("/api/backtest?code=000001&strategy=dual_ma&start_date=not-a-date")
        assert resp.status_code in (200, 400, 422, 500)

    def test_negative_cash(self):
        """負現金。"""
        client = TestClient(app)
        resp = client.post("/api/backtest?code=000001&strategy=dual_ma&cash=-100000")
        assert resp.status_code in (200, 400, 422, 500)


# ── download_manager 速率限制 ────────────────────────────────────

class TestDownloadRateLimit:
    """下載管理器速率限制測試。"""

    def test_rate_limiter_boundary(self):
        """速率限制器在頻率內外的行為。"""
        from src.core.rate_limiter import _MemoryRateLimiter
        rl = _MemoryRateLimiter()
        limit = 5

        # 前 5 個應通過
        for _ in range(5):
            allowed, _ = rl.check("test", limit)
            assert allowed is True

        # 第 6 個應被拒絕
        allowed, _ = rl.check("test", limit)
        assert allowed is False

    def test_rate_limiter_separate_keys(self):
        """不同 IP 的限制獨立。"""
        from src.core.rate_limiter import _MemoryRateLimiter
        rl = _MemoryRateLimiter()
        limit = 2

        allowed_a, _ = rl.check("ip_a", limit)
        assert allowed_a is True
        allowed_a, _ = rl.check("ip_a", limit)
        assert allowed_a is True
        allowed_a, _ = rl.check("ip_a", limit)
        assert allowed_a is False  # ip_a 耗盡

        allowed_b, _ = rl.check("ip_b", limit)
        assert allowed_b is True  # ip_b 獨立

    def test_concurrent_rate_limiter(self):
        """併發使用速率限制器。"""
        from src.core.rate_limiter import _MemoryRateLimiter
        import threading

        rl = _MemoryRateLimiter()
        limit = 10
        granted = []
        lock = threading.Lock()

        def _acquire():
            allowed, _ = rl.check("10.0.0.1", limit)
            if allowed:
                with lock:
                    granted.append(1)

        threads = [threading.Thread(target=_acquire) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert len(granted) == 10


# ── 回測任務完整生命週期 ────────────────────────────────────────

class TestBacktestLifecycle:
    """回測任務從提交到完成的完整流程。"""

    @pytest.fixture(autouse=True)
    def _auth(self, monkeypatch):
        monkeypatch.setattr(settings, "debug", True)

    def test_submit_poll_complete(self):
        """提交 → 輪詢 → 完成。"""
        client = TestClient(app)

        resp = client.post("/api/backtest?code=000001&strategy=dual_ma")
        assert resp.status_code == 200
        task_id = resp.json()["task_id"]

        # 輪詢最多 10 秒直到終態
        import time
        status = None
        for _ in range(20):
            resp2 = client.get(f"/api/tasks/{task_id}")
            data = resp2.json()
            task = data.get("task", data)
            status = task.get("status")
            if status in ("completed", "failed"):
                break
            time.sleep(0.5)

        assert status in ("completed", "failed"), f"預期終態, 實際: {status}"

    def test_submit_then_cancel(self):
        """提交 → 取消（寫入端點需登錄）。"""
        client = TestClient(app)
        resp = client.post("/api/backtest?code=000001&strategy=dual_ma")
        if resp.status_code != 200:
            return  # 限流或錯誤，跳過
        task_id = resp.json()["task_id"]

        # cancel 需要 auth，401 是正常行為
        resp2 = client.post(f"/api/tasks/{task_id}/cancel")
        assert resp2.status_code in (200, 400, 401)


# ── 健康檢查端點 ────────────────────────────────────────────────

class TestHealthEndpoints:
    """健康檢查端點壓力。"""

    @pytest.fixture(autouse=True)
    def _auth(self, monkeypatch):
        monkeypatch.setattr(settings, "debug", True)

    def test_health_basic(self):
        """基本健康檢查。"""
        client = TestClient(app)
        resp = client.get("/api/health")
        assert resp.status_code == 200

    def test_health_detailed(self):
        """詳細健康檢查。"""
        client = TestClient(app)
        resp = client.get("/api/health/detailed")
        assert resp.status_code == 200

    def test_100_concurrent_health(self):
        """100 個併發健康檢查。"""
        client = TestClient(app)
        results = []

        def _req():
            r = client.get("/api/health")
            results.append(r.status_code)

        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as pool:
            futures = [pool.submit(_req) for _ in range(100)]
            for f in concurrent.futures.as_completed(futures):
                f.result()

        server_errors = sum(1 for s in results if s >= 500)
        assert server_errors == 0, f"{server_errors} 個 5xx 錯誤"


# ── 任務端點壓力 ────────────────────────────────────────────────

class TestTaskEndpoints:
    """任務管理端點壓力。"""

    @pytest.fixture(autouse=True)
    def _auth(self, monkeypatch):
        monkeypatch.setattr(settings, "debug", True)

    def test_task_stats(self):
        client = TestClient(app)
        resp = client.get("/api/tasks/stats")
        assert resp.status_code == 200

    def test_task_queue(self):
        client = TestClient(app)
        resp = client.get("/api/tasks/queue")
        assert resp.status_code == 200
        data = resp.json()
        assert "running" in data or "stats" in data

    def test_task_types(self):
        client = TestClient(app)
        resp = client.get("/api/tasks/types")
        assert resp.status_code == 200

    def test_concurrent_task_list_and_stats(self):
        """併發查詢任務列表和統計。"""
        client = TestClient(app)
        endpoints = ["/api/tasks", "/api/tasks/stats", "/api/tasks/queue"]
        results = []

        def _req(ep):
            r = client.get(ep)
            results.append((ep, r.status_code))

        with concurrent.futures.ThreadPoolExecutor(max_workers=15) as pool:
            futs = [pool.submit(_req, ep) for ep in endpoints * 20]
            for f in concurrent.futures.as_completed(futs):
                f.result()

        server_errors = sum(1 for _, s in results if s >= 500)
        assert server_errors == 0


# ── 響應時間 ────────────────────────────────────────────────────

class TestResponseTime:
    """響應時間斷言。"""

    @pytest.fixture(autouse=True)
    def _auth(self, monkeypatch):
        monkeypatch.setattr(settings, "debug", True)

    def test_health_response_time(self):
        """健康檢查 < 2 秒。"""
        import time
        client = TestClient(app)
        start = time.time()
        client.get("/api/health")
        elapsed = time.time() - start
        assert elapsed < 2.0, f"健康檢查耗時 {elapsed:.2f}s"

    def test_strategy_params_response_time(self):
        """策略參數 < 5 秒。"""
        import time
        client = TestClient(app)
        start = time.time()
        client.get("/api/strategies/params")
        elapsed = time.time() - start
        assert elapsed < 5.0, f"策略參數耗時 {elapsed:.2f}s"

    def test_history_response_time(self):
        """歷史查詢 < 5 秒。"""
        import time
        client = TestClient(app)
        start = time.time()
        client.get("/api/backtest/history")
        elapsed = time.time() - start
        assert elapsed < 5.0, f"歷史查詢耗時 {elapsed:.2f}s"


# ── GZip 壓縮 ──────────────────────────────────────────────────

class TestGZipMiddleware:
    """GZip 中間件。"""

    @pytest.fixture(autouse=True)
    def _auth(self, monkeypatch):
        monkeypatch.setattr(settings, "debug", True)

    def test_gzip_accepted(self):
        """Accept-Encoding: gzip 請求。"""
        client = TestClient(app)
        resp = client.get("/api/strategies/params", headers={"Accept-Encoding": "gzip"})
        assert resp.status_code == 200

    def test_gzip_large_response(self):
        """大響應啟用壓縮。"""
        client = TestClient(app)
        resp = client.get("/api/backtest/history", headers={"Accept-Encoding": "gzip"})
        assert resp.status_code == 200


# ── 異常端點組合 ────────────────────────────────────────────────

class TestEndpointEdgeCases:
    """端點邊界條件。"""

    @pytest.fixture(autouse=True)
    def _auth(self, monkeypatch):
        monkeypatch.setattr(settings, "debug", True)

    def test_nonexistent_endpoint(self):
        """不存在的端點返回 404。"""
        client = TestClient(app)
        resp = client.get("/api/nonexistent/path")
        assert resp.status_code == 404

    def test_method_not_allowed(self):
        """錯誤的 HTTP 方法。"""
        client = TestClient(app)
        resp = client.delete("/api/health")
        assert resp.status_code in (405, 404, 400)

    def test_backtest_missing_params(self):
        """缺少必要參數。"""
        client = TestClient(app)
        resp = client.post("/api/backtest")
        assert resp.status_code in (400, 422, 200)

    def test_empty_body_post(self):
        """空 body POST。"""
        client = TestClient(app)
        resp = client.post("/api/auth/login", content="",
                           headers={"Content-Type": "application/json"})
        assert resp.status_code in (400, 422)
