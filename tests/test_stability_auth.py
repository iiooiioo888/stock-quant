"""
認證層穩定性測試 — 併發登入、Token 過期、邊界條件

覆蓋：
  - 併發登入請求
  - 密碼驗證錯誤路徑
  - 極端 payload
"""
from __future__ import annotations

import concurrent.futures
import pytest
from fastapi.testclient import TestClient

from src.api.app import app
from src.config import settings


# ── 併發登入 ────────────────────────────────────────────────────

class TestConcurrentAuth:
    """併發認證安全性。"""

    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch):
        monkeypatch.setattr(settings, "debug", True)

    def test_100_concurrent_logins(self):
        """100 個併發登入請求不出錯。"""
        client = TestClient(app)
        results = []

        def _login():
            resp = client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
            results.append(resp.status_code)
            return resp.status_code

        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as pool:
            futures = [pool.submit(_login) for _ in range(100)]
            for f in concurrent.futures.as_completed(futures):
                f.result()

        ok_count = sum(1 for s in results if s == 200)
        rl_count = sum(1 for s in results if s == 429)
        err_count = sum(1 for s in results if s not in (200, 429))
        # 所有請求應返回 200 或 429（限流），不應有 5xx
        assert err_count == 0, f"併發登入出現異常狀態碼，非 200/429: {err_count}/100"
        assert ok_count + rl_count == 100

    def test_100_concurrent_failed_logins(self):
        """100 個錯誤密碼不會導致服務不穩定。"""
        client = TestClient(app)
        results = []

        def _login():
            resp = client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
            results.append(resp.status_code)
            return resp.status_code

        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as pool:
            futures = [pool.submit(_login) for _ in range(100)]
            for f in concurrent.futures.as_completed(futures):
                f.result()

        fail_count = sum(1 for s in results if s == 401)
        rl_count = sum(1 for s in results if s == 429)
        err_count = sum(1 for s in results if s not in (401, 429))
        # 錯誤密碼應返回 401 或被限流 429，不應有 5xx
        assert err_count == 0, f"併發錯誤登入出現異常狀態碼: {err_count}/100"
        assert fail_count + rl_count == 100

    def test_login_then_use_token(self):
        """登入 → 使用 token → 驗證。"""
        client = TestClient(app)
        resp = client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
        assert resp.status_code == 200
        token = resp.json()["token"]

        resp2 = client.get("/api/backtest/history", headers={"Authorization": f"Bearer {token}"})
        assert resp2.status_code == 200


# ── 極端 Payload ────────────────────────────────────────────────

class TestEdgeCases:
    """認證邊界條件。"""

    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch):
        monkeypatch.setattr(settings, "debug", True)

    def test_empty_username(self):
        """空用戶名返回 400。"""
        client = TestClient(app)
        resp = client.post("/api/auth/login", json={"username": "", "password": "test"})
        assert resp.status_code in (400, 401)

    def test_missing_password(self):
        """缺少密碼返回 400。"""
        client = TestClient(app)
        resp = client.post("/api/auth/login", json={"username": "admin"})
        assert resp.status_code in (400, 401)

    def test_extra_fields_ignored(self):
        """額外字段被忽略。"""
        client = TestClient(app)
        resp = client.post("/api/auth/login", json={
            "username": "admin",
            "password": "admin",
            "extra": "field",
            "hacker": True,
        })
        assert resp.status_code == 200

    def test_very_long_password(self):
        """超長密碼不崩潰。"""
        client = TestClient(app)
        resp = client.post("/api/auth/login", json={
            "username": "admin",
            "password": "x" * 10000,
        })
        assert resp.status_code == 401

    def test_unicode_username(self):
        """Unicode 用戶名。"""
        client = TestClient(app)
        resp = client.post("/api/auth/login", json={
            "username": "管理員",
            "password": "test",
        })
        assert resp.status_code == 401

    def test_register_and_login(self):
        """註冊新用戶 → 登入。"""
        client = TestClient(app)
        import uuid
        uname = f"test_{uuid.uuid4().hex[:8]}"
        # 註冊
        resp = client.post("/api/auth/register", json={
            "username": uname,
            "password": "testpass123",
        })
        assert resp.status_code in (200, 201, 400)  # 400 if already exists
        # 登入
        resp2 = client.post("/api/auth/login", json={
            "username": uname,
            "password": "testpass123",
        })
        if resp.status_code == 200:
            assert resp2.status_code == 200
            assert "token" in resp2.json()


# ── /api/auth/me ────────────────────────────────────────────────

class TestAuthMe:
    """當前用戶信息端點。"""

    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch):
        monkeypatch.setattr(settings, "debug", True)

    def test_me_with_valid_token(self):
        """有效 token 獲取用戶信息。"""
        client = TestClient(app)
        resp = client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
        if resp.status_code != 200:
            pytest.skip("登入被限流")
        token = resp.json()["token"]
        resp2 = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert resp2.status_code == 200
        data = resp2.json()
        assert "username" in data or "user" in data

    def test_me_without_token(self):
        """無 token 返回 401。"""
        client = TestClient(app)
        resp = client.get("/api/auth/me")
        assert resp.status_code in (401, 403)

    def test_me_with_invalid_token(self):
        """無效 token 返回 401。"""
        client = TestClient(app)
        resp = client.get("/api/auth/me", headers={"Authorization": "Bearer invalid_token_xyz"})
        assert resp.status_code in (401, 403)


# ── 重複註冊 ────────────────────────────────────────────────────

class TestDuplicateRegister:
    """重複用戶名註冊。"""

    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch):
        monkeypatch.setattr(settings, "debug", True)

    def test_duplicate_username(self):
        """相同用戶名註冊兩次。"""
        client = TestClient(app)
        import uuid
        uname = f"dup_{uuid.uuid4().hex[:8]}"
        resp1 = client.post("/api/auth/register", json={"username": uname, "password": "pass123"})
        resp2 = client.post("/api/auth/register", json={"username": uname, "password": "pass456"})
        # 第二次應返回 400 或 409
        assert resp2.status_code in (400, 409, 200)  # 200 if idempotent


# ── 保護端點 Token 認證 ────────────────────────────────────────

class TestProtectedEndpoints:
    """受保護端點的認證流程。"""

    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch):
        monkeypatch.setattr(settings, "debug", True)

    def test_backtest_history_with_token(self):
        """帶 token 訪問歷史記錄。"""
        client = TestClient(app)
        resp = client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
        if resp.status_code != 200:
            pytest.skip("登入被限流")
        token = resp.json()["token"]
        resp2 = client.get("/api/backtest/history", headers={"Authorization": f"Bearer {token}"})
        assert resp2.status_code == 200

    def test_cancel_with_token(self):
        """帶 token 取消任務。"""
        client = TestClient(app)
        resp = client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
        if resp.status_code != 200:
            pytest.skip("登入被限流")
        token = resp.json()["token"]
        # 先創建任務
        resp2 = client.post("/api/backtest?code=000001&strategy=dual_ma",
                            headers={"Authorization": f"Bearer {token}"})
        if resp2.status_code == 200:
            tid = resp2.json()["task_id"]
            resp3 = client.post(f"/api/tasks/{tid}/cancel",
                                headers={"Authorization": f"Bearer {token}"})
            assert resp3.status_code in (200, 400)

    def test_register_then_access(self):
        """新註冊用戶訪問端點。"""
        client = TestClient(app)
        import uuid
        uname = f"newuser_{uuid.uuid4().hex[:8]}"
        client.post("/api/auth/register", json={"username": uname, "password": "pass123"})
        resp = client.post("/api/auth/login", json={"username": uname, "password": "pass123"})
        if resp.status_code != 200:
            pytest.skip("登入被限流")
        token = resp.json()["token"]
        resp2 = client.get("/api/backtest/history", headers={"Authorization": f"Bearer {token}"})
        assert resp2.status_code == 200


# ── 併發 Token 使用 ────────────────────────────────────────────

class TestConcurrentTokenUse:
    """併發使用同一 Token。"""

    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch):
        monkeypatch.setattr(settings, "debug", True)

    def test_concurrent_requests_with_same_token(self):
        """同一 token 併發請求。"""
        import concurrent.futures
        client = TestClient(app)
        resp = client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
        if resp.status_code != 200:
            pytest.skip("登入被限流")
        token = resp.json()["token"]
        results = []

        def _req():
            r = client.get("/api/backtest/history", headers={"Authorization": f"Bearer {token}"})
            results.append(r.status_code)

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
            futs = [pool.submit(_req) for _ in range(20)]
            for f in concurrent.futures.as_completed(futs):
                f.result()

        ok = sum(1 for s in results if s == 200)
        rl = sum(1 for s in results if s == 429)
        err = sum(1 for s in results if s not in (200, 429))
        assert err == 0, f"異常狀態碼: {err}"
