"""TradingView / IB / 目錄測試"""

import pandas as pd
import pytest


class TestMarketCatalog:
    def test_lookup_and_groups(self):
        from src.core.market_catalog import (
            GROUP_LABELS,
            MARKET_INSTRUMENTS,
            lookup_instrument,
            instruments_by_group,
        )

        assert len(MARKET_INSTRUMENTS) >= 80
        assert "hk_stock" in GROUP_LABELS
        assert "utilities" in GROUP_LABELS
        assert "a_share" in GROUP_LABELS
        inst = lookup_instrument("000001.SS")
        assert inst is not None
        assert inst.tv == "SSE:000001"
        groups = instruments_by_group()
        assert "forex" in groups
        assert len(groups["crypto"]) >= 2


class TestTradingViewData:
    def test_fetch_tv_history_parses_ok_response(self, monkeypatch):
        from src.core import tradingview_data as tv

        class Resp:
            def raise_for_status(self):
                pass

            def json(self):
                return {
                    "s": "ok",
                    "t": [1700000000, 1700086400],
                    "o": [100.0, 101.0],
                    "h": [102.0, 103.0],
                    "l": [99.0, 100.0],
                    "c": [101.0, 102.0],
                    "v": [1000, 1100],
                }

        monkeypatch.setattr(tv._SESSION, "get", lambda *a, **k: Resp())
        df = tv.fetch_tv_history("FX:EURUSD", 30)
        assert len(df) == 2
        assert list(df.columns) == ["date", "open", "high", "low", "close", "volume"]


class TestIbData:
    def test_ib_status_when_disabled(self, monkeypatch):
        from src.core import ib_data as ib

        class S:
            ib_enabled = False
            ib_host = "127.0.0.1"
            ib_port = 7497

        monkeypatch.setattr(ib, "_settings", lambda: S())
        st = ib.ib_status()
        assert st["enabled"] is False
        assert st["reason"] == "disabled"

    def test_build_index_prefers_tv_when_configured(self, monkeypatch):
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
        quote = {
            "price": 102.5,
            "change_pct": 1.2,
            "change": 1.2,
            "source": "tradingview",
        }

        monkeypatch.setattr(
            mf,
            "_fetch_catalog_primary",
            lambda s, d: (df, quote, "tradingview"),
        )
        monkeypatch.setattr(mf, "fetch_history_df", lambda s, d: (pd.DataFrame(), ""))
        monkeypatch.setattr(mf, "fetch_quote", lambda s: ({}, ""))

        item = mf.build_index_chart_item("BTC-USD", "比特幣", 30)
        assert item is not None
        assert item["source"] == "TradingView"
        assert item["group"] == "crypto"
