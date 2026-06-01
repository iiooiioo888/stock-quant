"""
API 煙霧測試 — CI 內快速驗證核心端點（等同 test_all.sh 子集）
"""
import pytest


@pytest.fixture
def auth_headers(client):
    import uuid
    pw = "smoke_test_pw_2026"
    username = f"smokeuser_{uuid.uuid4().hex[:8]}"
    client.post("/api/auth/register", json={"username": username, "password": pw})
    resp = client.post("/api/auth/login", json={"username": username, "password": pw})
    token = resp.json().get("token", "")
    return {"Authorization": f"Bearer {token}"}


class TestSmokeAPI:
    def test_health_and_status(self, client):
        assert client.get("/api/health").status_code == 200
        assert client.get("/api/status").status_code == 200

    def test_config_and_strategies(self, client):
        assert client.get("/api/config").status_code == 200
        data = client.get("/api/strategies/list").json()
        assert data.get("total", 0) >= 19

    def test_auth_me(self, client, auth_headers):
        resp = client.get("/api/auth/me", headers=auth_headers)
        assert resp.status_code == 200
        user = resp.json().get("user") or {}
        assert "billing" in user
        assert user["billing"].get("plan_id") in ("free", "pro", "institutional")

    def test_billing_plans_public(self, client):
        resp = client.get("/api/billing/plans")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("success") is True
        plans = {p["id"]: p for p in (data.get("plans") or [])}
        assert "free" in plans and "pro" in plans and "institutional" in plans
        assert plans["pro"].get("highlight") is True

    def test_billing_checkout_dev(self, client, auth_headers):
        resp = client.post(
            "/api/billing/checkout",
            json={"plan_id": "pro"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json().get("plan_id") == "pro"
        me = client.get("/api/billing/me", headers=auth_headers).json()
        assert me.get("plan_id") == "pro"

    def test_tasks_list(self, client, auth_headers):
        assert client.get("/api/tasks", headers=auth_headers).status_code == 200

    def test_stock_universe_stats(self, client):
        assert client.get("/api/stock-universe/stats").status_code == 200

    def test_tasks_list_without_auth(self, client):
        """任務中心應在未登錄時可讀（本地/演示模式）"""
        resp = client.get("/api/tasks?limit=10")
        assert resp.status_code == 200
        data = resp.json()
        assert "tasks" in data
        assert "queue" in data

    def test_html_entrypoints(self, client):
        home = client.get("/")
        assert home.status_code == 200
        assert "site-portals" in home.text or "StockQ" in home.text
        assert "home-strat-grid" in home.text
        assert "strategy-catalog" in home.text or "支援的策略庫" in home.text

        app = client.get("/app")
        assert app.status_code == 200
        assert "pg-dashboard" in app.text
        assert "dashboard-root" in app.text
        assert "topbar-ticker-strip" in app.text
        assert "pg-assets" in app.text

        admin = client.get("/admin")
        assert admin.status_code == 200
        assert "admin-gate" in admin.text

        assert client.get("/static/js/app.js").status_code == 200

    def test_ws_auth_flag_in_health(self, client):
        data = client.get("/api/health").json()
        assert "ws_auth_required" in data

    def test_indices_charts(self, client):
        resp = client.get("/api/indices/charts?days=60")
        assert resp.status_code == 200
        data = resp.json()
        assert "indices" in data
        assert isinstance(data["indices"], list)
        assert "groups" in data
        assert "providers" in data
        assert "tradingview" in data["providers"]

    def test_indices_charts_topbar_days(self, client):
        """頂欄輕量請求允許 days≤14，不可再 422。"""
        resp = client.get("/api/indices/charts?days=14&scope=topbar")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("scope") == "topbar"
        assert data.get("days") == 14

    def test_indices_providers(self, client):
        resp = client.get("/api/indices/providers")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("catalog_size", 0) >= 80
        assert "hk_stock" in data.get("groups", {})
        assert "asset_classes" in data
        assert "tradingview" in data
        assert "ib" in data

    def test_assets_catalog(self, client):
        resp = client.get("/api/assets/catalog")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("total", 0) >= 200
        assert "instruments" in data
        assert "group_order" in data
        groups = data.get("groups") or {}
        assert "asia" in groups
        assert "us_stock" in groups
        # v4 assets: hierarchical classification
        inst = (data.get("instruments") or [None])[0] or {}
        assert "l2" in inst and "l2_label" in inst
        assert "l3" in inst and "l3_label" in inst
        assert "theme_packs" in data
        packs = {p["id"]: p for p in (data.get("theme_packs") or [])}
        assert "hstech" in packs and "csi300" in packs
        assert packs["hstech"].get("catalog_count", 0) >= 10
        assert data.get("theme_packs_locked") is True
        stock = next(
            (x for x in (data.get("instruments") or []) if x.get("symbol") == "0700.HK"),
            None,
        )
        if stock:
            assert (stock.get("themes") or []) == []

    def test_assets_detail(self, client):
        resp = client.get("/api/assets/detail?symbol=^GSPC&days=60")
        assert resp.status_code == 200
        resp_hk = client.get("/api/assets/detail?symbol=1299.HK&days=60")
        assert resp_hk.status_code == 200
        assert resp_hk.json().get("detail", {}).get("kline")
        resp_175 = client.get("/api/assets/detail?symbol=0175.HK&days=90")
        assert resp_175.status_code == 200
        d175 = resp_175.json().get("detail") or {}
        assert len(d175.get("profile", {}).get("intro", "")) > 20
        assert d175.get("stats", {}).get("period_high") is not None
        assert isinstance(d175.get("links"), list) and len(d175["links"]) >= 2
        resp_moutai = client.get("/api/assets/detail?symbol=600519.SS&days=90")
        if resp_moutai.status_code == 200:
            dm = resp_moutai.json().get("detail") or {}
            thesis = (dm.get("investment_thesis") or dm.get("one_liner") or "").strip()
            if thesis:
                assert len(thesis) >= 8
        data = resp.json()
        assert data.get("success") is True
        detail = data.get("detail") or {}
        assert detail.get("symbol") == "^GSPC"
        assert isinstance(detail.get("kline"), list)
        assert "quote" in detail
        assert "news" in detail

    @pytest.mark.parametrize(
        "path,keys",
        [
            ("/api/data/capital-flow?code=000001&days=5", ("flows",)),
            ("/api/data/market-flow", ("flows",)),
            ("/api/signals/current", ("signals",)),
            ("/api/scheduler/jobs", ("jobs",)),
            ("/api/strategies/params", ("strategies",)),
        ],
    )
    def test_demo_read_endpoints(self, client, path, keys):
        resp = client.get(path)
        assert resp.status_code == 200, resp.text[:200]
        data = resp.json()
        for key in keys:
            assert key in data, f"missing {key} in {path}"
