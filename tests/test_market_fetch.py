"""多源行情拉取測試"""

import pandas as pd
import pytest


class TestMarketFetch:
    def test_build_index_chart_item_uses_fallback(self, monkeypatch):
        from src.core import market_fetch as mf

        df = pd.DataFrame(
            {
                "date": ["2026-01-01", "2026-01-02"],
                "open": [100.0, 101.0],
                "high": [102.0, 103.0],
                "low": [99.0, 100.0],
                "close": [101.0, 102.0],
                "volume": [1000, 1100],
            }
        )

        monkeypatch.setattr(
            mf, "fetch_history_df", lambda s, d, **kw: (df, "eastmoney")
        )
        monkeypatch.setattr(mf, "fetch_quote", lambda s: ({}, ""))

        item = mf.build_index_chart_item("^GSPC", "標普 500", 60)
        assert item is not None
        assert item["source"] == "東財"
        assert item["source_raw"] == "eastmoney"
        assert len(item["kline"]) == 2
        assert item["latest"] == 102.0

    def test_build_sparkline_empty(self, monkeypatch):
        from src.core import market_fetch as mf

        monkeypatch.setattr(mf, "fetch_history_df", lambda s, d: (pd.DataFrame(), ""))
        out = mf.build_sparkline_item("000001", 30)
        assert out["prices"] == []
        assert out["source"] == ""

    def test_symbol_to_a_share_code(self):
        from src.core.market_fetch import symbol_to_a_share_code

        assert symbol_to_a_share_code("000001.SS") == "000001"
        assert symbol_to_a_share_code("399001.SZ") == "399001"
        assert symbol_to_a_share_code("600519") == "600519"
        assert symbol_to_a_share_code("^GSPC") is None
