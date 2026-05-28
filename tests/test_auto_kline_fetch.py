"""自動選源下載 — 單元測試（無外網）。"""
from src.core.auto_kline_fetch import (
    SOURCE_SLUG,
    days_from_start_date,
    download_one_auto,
    source_slug,
)
from src.core.local_kline import normalize_kline_code


def test_normalize_kline_yahoo_suffix():
    assert normalize_kline_code("600519.SS") == "600519"
    assert normalize_kline_code("000001.SZ") == "000001"
    assert normalize_kline_code("600519") == "600519"


def test_source_slug_mapping():
    assert source_slug("Yahoo Finance") == "yahoo"
    assert source_slug("Interactive Brokers") == "ib"
    assert "eastmoney" in SOURCE_SLUG.values()


def test_days_from_start_date():
    assert days_from_start_date(None) == 400
    assert days_from_start_date("20200101") >= 30


def test_detect_market_routes_without_network(monkeypatch):
    """僅驗證路由與返回型別，不發真實請求。"""
    monkeypatch.setattr(
        "src.core.auto_kline_fetch._try_pipeline_fetch",
        lambda code, market, start_date: (0, ""),
    )
    monkeypatch.setattr(
        "src.core.history._download_crypto",
        lambda code, start_date: 0,
    )

    n, src = download_one_auto("BTCUSDT", market="crypto")
    assert n == 0
    assert src == ""
