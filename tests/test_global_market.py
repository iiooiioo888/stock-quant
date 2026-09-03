"""全球市場目錄與輔助函數測試。"""

from src.core.global_market import MARKET_CATALOG, get_market_catalog


def test_market_catalog_keys():
    cat = get_market_catalog()
    assert cat is not MARKET_CATALOG
    for key in ("us_stock", "hk_stock", "index", "etf", "commodity"):
        assert key in cat
        assert "symbols" in cat[key]
        assert cat[key]["symbols"]


def test_index_catalog_has_common_benchmarks():
    symbols = MARKET_CATALOG["index"]["symbols"]
    joined = " ".join(symbols.keys()).upper()
    assert "GSPC" in joined or "^GSPC" in joined or "SPX" in joined or "DJI" in joined
