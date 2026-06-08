"""主題包批量映射 — 回歸與性能相關行為"""

from src.core.stock_theme_packs import (
    THEME_PACK_ORDER,
    build_symbol_themes_map,
    count_themes_in_catalog,
    themes_for_symbol,
)


def test_build_symbol_themes_map_matches_single_lookup():
    symbols = ["0700.HK", "600519.SS", "AAPL", "NOT_IN_ANY_PACK"]
    bulk = build_symbol_themes_map(symbols)
    for sym in symbols:
        assert bulk.get(sym.upper(), []) == themes_for_symbol(sym)


def test_count_themes_in_catalog_covers_packs():
    symbols = ["0700.HK", "9988.HK", "600519.SS"]
    counts = count_themes_in_catalog(symbols)
    assert set(counts.keys()) == set(THEME_PACK_ORDER)
    assert counts.get("hstech", 0) >= 2
    assert counts.get("csi300", 0) >= 1
