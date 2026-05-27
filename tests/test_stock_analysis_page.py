"""個股分析頁 API"""
import pytest


class TestStockAnalysisPage:
    def test_analysis_page_endpoint(self, client):
        resp = client.get("/api/stocks/600519/analysis-page?kline_days=60&sparkline_days=30")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("success") is True
        assert data.get("code")
        assert "name" in data
        assert "profile" in data
        assert isinstance(data["profile"], dict)
        assert "sparkline" in data
        assert "overview" in data
        assert isinstance(data["overview"], dict)
        assert "signals" in data
        assert isinstance(data["signals"], dict)
        assert "signals" in data["signals"]
