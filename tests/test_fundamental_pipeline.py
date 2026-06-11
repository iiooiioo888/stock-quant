"""財報與數據管線單元測試"""

from datetime import date, timedelta

from src.core.data_pipeline import (
    defer_data_cache_clear,
    flush_deferred_data_cache_clear,
    is_stale,
    parse_ymd,
)
from src.core.fundamental import (
    fundamentals_row_to_fin,
    get_fundamentals,
    load_fundamentals_db,
)


class TestDataPipeline:
    def test_parse_ymd(self):
        assert parse_ymd("2024-06-01") == date(2024, 6, 1)
        assert parse_ymd("20240601") == date(2024, 6, 1)

    def test_is_stale(self):
        old = (date.today() - timedelta(days=30)).isoformat()
        recent = date.today().isoformat()
        assert is_stale(old, max_age_days=7) is True
        assert is_stale(recent, max_age_days=7) is False
        assert is_stale(None, max_age_days=7) is True

    def test_defer_cache_clear_once(self):
        defer_data_cache_clear()
        defer_data_cache_clear()
        assert flush_deferred_data_cache_clear() is True
        assert flush_deferred_data_cache_clear() is False


class TestFundamentals:
    def test_row_to_fin(self):
        fin = fundamentals_row_to_fin(
            {
                "code": "600519",
                "pe_ttm": 25.0,
                "pb": 8.0,
                "update_date": "2024-01-01",
            }
        )
        assert fin.get("has_data") is True
        assert fin.get("pe_ttm") == 25.0

    def test_get_fundamentals_returns_dict_for_a_share(self):
        row = load_fundamentals_db("600519")
        out = get_fundamentals("600519", max_age_days=365, force_refresh=False)
        assert isinstance(out, dict)
        if row:
            assert (
                out.get("code") == "600519"
                or out == row
                or out.get("pe_ttm") is not None
            )
