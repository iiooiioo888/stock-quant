"""儀表盤資金與板塊 API 測試"""
import pytest


class TestDashboardMarketAPI:
    def test_market_charts_endpoint(self, client):
        resp = client.get("/api/dashboard/market-charts?days=10")
        assert resp.status_code == 200
        data = resp.json()
        assert "sector_flow" in data
        assert "market_flow" in data
        assert "north_flow" in data
        assert "sector_scatter" in data
        assert "sector_heatmap" in data

    def test_sectors_capital_flow_rank(self, client):
        resp = client.get("/api/data/sectors/capital-flow?top_n=5")
        assert resp.status_code == 200
        assert "sectors" in resp.json()
