"""
認證層穩定性測試 — 併發登入、Token 過期、角色管理

覆蓋：
  - 併發登入請求
  - 角色與權限管理
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
            resp = client.post("/api/login", json={"username": "admin", "password": "admin123"})
            results.append(resp.status_code)
            return resp.status_code

        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as pool:
            futures = [pool.submit(_login) for _ in range(100)]
            for f in concurrent.futures.as_completed(futures):
                f.result()

        ok_count = sum(1 for s in results if s == 200)
        assert ok_count == 100, f"100 次併發登入應全部成功，實際 {ok_count}/100"

    def test_100_concurrent_failed_logins(self):
        """100 個錯誤密碼不會導致服務不穩定。"""
        client = TestClient(app)
        results = []

        def _login():
            resp = client.post("/api/login", json={"username": "admin", "password": "wrong"})
            results.append(resp.status_code)
            return resp.status_code

        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as pool:
            futures = [pool.submit(_login) for _ in range(100)]
            for f in concurrent.futures.as_completed(futures):
                f.result()

        fail_count = sum(1 for s in results if s == 401)
        assert fail_count == 100

    def test_login_then_use_token(self):
        """登入 → 使用 token → 驗證。"""
        client = TestClient(app)
        resp = client.post("/api/login", json={"username": "admin", "password": "admin123"})
        assert resp.status_code == 200
        token = resp.json()["token"]

        resp2 = client.get("/api/backtest/history", headers={"Authorization": f"Bearer {token}"})
        assert resp2.status_code == 200


# ── 角色與權限 ──────────────────────────────────────────────────

class TestRoles:
    """角色管理。"""

    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch):
        monkeypatch.setattr(settings, "debug", True)

    def test_login_roles_endpoint(self):
        """登入角色端點。"""
        client = TestClient(app)
        resp = client.get("/api/login/roles")
        assert resp.status_code == 200
        roles = resp.json()
        assert "admin" in roles

    def test_role_permissions_mapping(self):
        """角色權限映射完整性。"""
        client = TestClient(app)
        resp = client.get("/api/login/roles")
        roles = resp.json()
        for role, perms in roles.items():
            assert isinstance(perms, list)
            assert len(perms) > 0


# ── 極端 Payload ────────────────────────────────────────────────

class TestEdgeCases:
    """認證邊界條件。"""

    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch):
        monkeypatch.setattr(settings, "debug", True)

    def test_empty_username(self):
        """空用戶名。"""
        client = TestClient(app)
        resp = client.post("/api/login", json={"username": "", "password": "test"})
        assert resp.status_code == 401

    def test_missing_password(self):
        """缺少密碼。"""
        client = TestClient(app)
        resp = client.post("/api/login", json={"username": "admin"})
        assert resp.status_code == 401

    def test_extra_fields_ignored(self):
        """額外字段被忽略。"""
        client = TestClient(app)
        resp = client.post("/api/login", json={
            "username": "admin",
            "password": "admin123",
            "extra": "field",
            "hacker": True,
        })
        assert resp.status_code == 200

    def test_very_long_password(self):
        """超長密碼不崩潰。"""
        client = TestClient(app)
        resp = client.post("/api/login", json={
            "username": "admin",
            "password": "x" * 10000,
        })
        assert resp.status_code == 401

    def test_unicode_username(self):
        """Unicode 用戶名。"""
        client = TestClient(app)
        resp = client.post("/api/login", json={
            "username": "管理員",
            "password": "test",
        })
        assert resp.status_code == 401
