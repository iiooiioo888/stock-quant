"""板塊熱力圖數據測試"""

import pytest


class TestSectorHeatmap:
    def test_heatmap_fills_amount_when_missing(self, monkeypatch):
        from src.core import sector as sec

        monkeypatch.setattr(
            sec,
            "get_sector_list",
            lambda sector_type="industry": [
                {
                    "name": "銀行",
                    "change_pct": 2.5,
                    "amount": 0,
                    "rise_count": 10,
                    "fall_count": 5,
                },
                {
                    "name": "電子",
                    "change_pct": 0,
                    "amount": 0,
                    "rise_count": 0,
                    "fall_count": 0,
                },
            ],
        )
        rows = sec.get_sector_heatmap_data("industry")
        assert len(rows) == 2
        assert rows[0]["amount"] > 0
        assert rows[1]["amount"] == 1.0
