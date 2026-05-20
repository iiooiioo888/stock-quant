# -*- coding: utf-8 -*-
"""本地優先 K 線邏輯"""
import pandas as pd
import pytest

from src.core.local_kline import ensure_daily_kline, has_local_kline, normalize_kline_code


def test_normalize_kline_code():
    assert normalize_kline_code("1") == "000001"
    assert normalize_kline_code("^GSPC") == "^GSPC"


def test_ensure_daily_kline_uses_local_without_fetch(monkeypatch):
    calls = {"download": 0}

    def fake_load(code, start_date=None, end_date=None):
        return pd.DataFrame({
            "date": ["2024-01-01", "2024-01-02"],
            "open": [1.0, 1.0],
            "high": [1.0, 1.0],
            "low": [1.0, 1.0],
            "close": [1.0, 1.0],
            "volume": [100, 100],
            "amount": [0, 0],
            "turnover": [0, 0],
            "market": ["a_share", "a_share"],
        })

    def fake_download(*args, **kwargs):
        calls["download"] += 1
        return 0

    monkeypatch.setattr("src.core.local_kline.load_daily_kline", fake_load)
    monkeypatch.setattr("src.core.history.download_one", fake_download)

    df, source = ensure_daily_kline("000001", min_bars=2)
    assert source == "local_db"
    assert len(df) == 2
    assert calls["download"] == 0
    assert has_local_kline("000001", min_bars=2)


def test_ensure_daily_kline_fetches_once_when_empty(monkeypatch):
    store = {"rows": pd.DataFrame()}

    def fake_load(code, start_date=None, end_date=None):
        return store["rows"].copy()

    def fake_download(code, start_date=None, market=None):
        store["rows"] = pd.DataFrame({
            "date": ["2024-01-01", "2024-01-02", "2024-01-03"],
            "open": [10.0, 11.0, 12.0],
            "high": [10.0, 11.0, 12.0],
            "low": [10.0, 11.0, 12.0],
            "close": [10.0, 11.0, 12.0],
            "volume": [1, 1, 1],
            "amount": [0, 0, 0],
            "turnover": [0, 0, 0],
            "market": ["a_share"] * 3,
        })
        return 3

    monkeypatch.setattr("src.core.local_kline.load_daily_kline", fake_load)
    monkeypatch.setattr("src.core.history.download_one", fake_download)
    monkeypatch.setattr("src.core.local_kline.clear_data_cache", lambda: None)

    df, source = ensure_daily_kline("600519", min_bars=2, auto_fetch=True)
    assert source == "fetched"
    assert len(df) == 3

    df2, source2 = ensure_daily_kline("600519", min_bars=2)
    assert source2 == "local_db"
    assert len(df2) == 3
