"""market_catalog instruments_for_charts 篩選邏輯"""

from src.core.market_catalog import (
    DASHBOARD_CHART_GROUPS,
    MARKET_INSTRUMENTS,
    instruments_for_charts,
    lookup_instrument,
)


def test_instruments_for_charts_all_excludes_placeholders():
    picked = instruments_for_charts("all")
    assert len(picked) <= 500
    assert all(i.detail_supported for i in picked)
    syms = {i.symbol for i in picked}
    assert not any(s.startswith("CN_OTC_OPT_") for s in syms)
    assert not any(s.startswith("CN_ALT_") for s in syms)


def test_instruments_for_dashboard_is_core_groups_only():
    picked = instruments_for_charts("dashboard")
    assert 8 <= len(picked) <= 40
    assert all(i.group in DASHBOARD_CHART_GROUPS for i in picked)
    assert all(i.detail_supported for i in picked)
    groups = {i.group for i in picked}
    assert "us_stock" not in groups
    assert "a_share" not in groups


def test_instruments_for_stocks_scope():
    picked = instruments_for_charts("stocks")
    assert len(picked) >= 100
    assert all(i.group in {"a_share", "hk_stock", "us_stock"} for i in picked)


def test_lookup_instrument_index():
    inst = lookup_instrument("600519.SS")
    assert inst is not None
    assert inst.name
    assert lookup_instrument("NOT_A_REAL_SYMBOL_XYZ") is None


def test_custom_scope_skips_non_tradeable():
    picked = instruments_for_charts("custom", symbols="600519.SS,CN_OTC_OPT_CSI300_1M")
    syms = {i.symbol for i in picked}
    assert "600519.SS" in syms
    assert "CN_OTC_OPT_CSI300_1M" not in syms


def test_custom_scope_empty_does_not_fallback_to_topbar():
    picked = instruments_for_charts("custom", symbols="")
    assert picked == []
    picked_none = instruments_for_charts("custom", symbols="NOT_A_REAL_SYMBOL_XYZ")
    assert picked_none == []
