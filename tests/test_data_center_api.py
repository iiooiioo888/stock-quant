"""數據中心 API 可訪問性（未登錄白名單）"""

import pytest


class TestDataCenterAPI:
    def test_sectors_without_auth(self, client):
        resp = client.get("/api/data/sectors?sector_type=industry&top_n=5")
        assert resp.status_code == 200
        data = resp.json()
        assert "sectors" in data

    def test_north_flow_daily_shape(self, client):
        resp = client.get("/api/data/north-flow?days=5")
        assert resp.status_code == 200
        data = resp.json()
        assert "flows" in data
        assert "daily" in data

    def test_sector_heatmap_without_auth(self, client):
        resp = client.get("/api/data/sectors/heatmap?sector_type=industry")
        assert resp.status_code == 200
        assert "sectors" in resp.json()
