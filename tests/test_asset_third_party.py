from src.core.asset_detail import _external_links, _third_party_widgets, _yahoo_ticker


def test_yahoo_ticker_a_share_and_us():
    assert _yahoo_ticker("600519", "a_share") == "600519.SS"
    assert _yahoo_ticker("000001", "a_share") == "000001.SZ"
    assert _yahoo_ticker("AAPL.US", "us_stock") == "AAPL"
    assert _yahoo_ticker("0700.HK", "hk_stock") == "0700.HK"


def test_external_links_cover_major_vendors():
    us = _external_links("AAPL.US", "Apple", "NASDAQ:AAPL", "us_stock")
    sources = {x["source"] for x in us}
    assert "TradingView" in sources
    assert "Yahoo" in sources
    assert "Google" in sources
    assert "Finviz" in sources
    assert "Seeking Alpha" in sources
    assert "SEC" in sources

    a = _external_links("600519", "茅台", "SSE:600519", "a_share")
    a_src = {x["source"] for x in a}
    assert "東財" in a_src
    assert "新浪" in a_src
    assert "雪球" in a_src

    hk = _external_links("0700.HK", "騰訊", "HKEX:700", "hk_stock")
    hk_src = {x["source"] for x in hk}
    assert "AASTOCKS" in hk_src
    assert "HKEX" in hk_src


def test_widgets_include_tradingview_embeds():
    widgets = _third_party_widgets("AAPL.US", "NASDAQ:AAPL", "us_stock")
    kinds = {w["kind"] for w in widgets}
    assert "tradingview_chart" in kinds
    assert "tradingview_mini" in kinds
    chart = next(w for w in widgets if w["kind"] == "tradingview_chart")
    assert "tradingview.com" in chart["src"]
