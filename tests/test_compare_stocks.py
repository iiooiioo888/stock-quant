"""多股對比 API"""
import pytest


class TestCompareStocks:
    def test_compare_requires_codes(self, client):
        r = client.post("/api/stocks/compare", json={})
        assert r.status_code == 400

    def test_compare_indexes_list(self, client):
        r = client.get("/api/stocks/compare/indexes")
        assert r.status_code == 200
        data = r.json()
        assert data.get("indexes")
        codes = {x["code"] for x in data["indexes"]}
        assert "000300" in codes

    def test_compare_response_shape(self, client, monkeypatch):
        import pandas as pd

        def fake_ensure(code, start_date=None, min_bars=2):
            n = 30
            df = pd.DataFrame({
                "date": [f"2024-01-{i+1:02d}" for i in range(n)],
                "close": [10.0 + i * 0.1 + (0.05 if code == "600519" else 0) for i in range(n)],
            })
            return df, "test"

        def fake_benchmark(start_date=None, end_date=None):
            n = 30
            return {
                "dates": [f"2024-01-{i+1:02d}" for i in range(n)],
                "prices": [100.0 + i * 0.05 for i in range(n)],
                "returns": [0.0] + [0.001] * (n - 1),
                "nav": [1.0 + i * 0.001 for i in range(n)],
            }

        monkeypatch.setattr(
            "src.core.local_kline.ensure_daily_kline",
            fake_ensure,
        )
        monkeypatch.setattr(
            "src.core.benchmark.get_benchmark_returns",
            fake_benchmark,
        )
        r = client.post(
            "/api/stocks/compare",
            json={"codes": ["600519", "600036"], "days": 20, "benchmark": "600519", "index": "000300"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data.get("success") is True
        comp = data.get("comparison") or {}
        assert "600519" in comp
        assert "600036" in comp
        assert comp["600519"].get("stats")
        assert "total_return_pct" in comp["600519"]["stats"]
        corr = data.get("correlation")
        assert corr and corr.get("matrix")
        assert data.get("excess_return")
        assert data.get("index_overlay")
        assert data["index_overlay"].get("code") == "000300"
