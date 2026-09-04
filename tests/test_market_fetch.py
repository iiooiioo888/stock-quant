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

    def test_fetch_history_df_uses_local_without_catalog(self, monkeypatch):
        from src.core import market_fetch as mf

        local = pd.DataFrame(
            {
                "date": ["2026-01-01", "2026-01-02", "2026-01-03"],
                "open": [1.0, 1.1, 1.2],
                "high": [1.2, 1.3, 1.4],
                "low": [0.9, 1.0, 1.1],
                "close": [1.1, 1.2, 1.3],
                "volume": [10, 11, 12],
            }
        )
        called = {"catalog": 0}

        monkeypatch.setattr(mf, "_fetch_local_kline", lambda s, d: local)
        monkeypatch.setattr(
            mf,
            "_fetch_catalog_primary",
            lambda *a, **k: called.__setitem__("catalog", called["catalog"] + 1)
            or (pd.DataFrame(), "", ""),
        )
        df, src = mf.fetch_history_df("000001.SZ", 30)
        assert src == "local_db"
        assert len(df) == 3
        assert called["catalog"] == 0

    def test_fetch_history_df_empty_routes_to_buffer_not_catalog(self, monkeypatch):
        from src.core import market_fetch as mf

        called = {"catalog": 0, "ensure": 0}

        monkeypatch.setattr(mf, "_fetch_local_kline", lambda s, d: pd.DataFrame())
        monkeypatch.setattr(
            "src.core.data_fetch_buffer.is_inflight", lambda *a, **k: False
        )
        monkeypatch.setattr(
            "src.core.data_fetch_buffer.ensure_fetched",
            lambda *a, **k: called.__setitem__("ensure", called["ensure"] + 1),
        )
        monkeypatch.setattr(
            mf,
            "_fetch_catalog_primary",
            lambda *a, **k: called.__setitem__("catalog", called["catalog"] + 1)
            or (pd.DataFrame(), "", ""),
        )
        df, src = mf.fetch_history_df("000001.SZ", 30)
        assert src == ""
        assert df.empty
        assert called["ensure"] == 1
        assert called["catalog"] == 0

    def test_symbol_to_a_share_code(self):
        from src.core.market_fetch import symbol_to_a_share_code

        assert symbol_to_a_share_code("000001.SS") == "000001"
        assert symbol_to_a_share_code("399001.SZ") == "399001"
        assert symbol_to_a_share_code("600519") == "600519"
        assert symbol_to_a_share_code("^GSPC") is None
