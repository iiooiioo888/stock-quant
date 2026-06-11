"""kline_fetcher / yahoo_finance 資料源穩定性單元測試。"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest


def _sample_chart_json():
    return {
        "chart": {
            "result": [{
                "timestamp": [1704067200, 1704153600],
                "indicators": {
                    "quote": [{
                        "open": [10.0, 10.5],
                        "high": [10.8, 11.0],
                        "low": [9.8, 10.2],
                        "close": [10.5, 10.8],
                        "volume": [1000, 1200],
                    }],
                },
            }],
        },
    }


def test_yahoo_429_exponential_backoff(monkeypatch):
    from src.config import settings
    from src.core import yahoo_finance as yf

    monkeypatch.setattr(settings, "yahoo_enabled", True)
    monkeypatch.setattr(settings, "yahoo_max_retries", 2)
    monkeypatch.setattr(settings, "yahoo_request_interval", 0.2)

    session = MagicMock()
    resp_429 = MagicMock()
    resp_429.status_code = 429
    resp_429.headers = {"Retry-After": "1"}
    resp_ok = MagicMock()
    resp_ok.status_code = 200
    resp_ok.json.return_value = _sample_chart_json()
    resp_ok.raise_for_status = MagicMock()
    session.get.side_effect = [resp_429, resp_ok]
    monkeypatch.setattr(yf, "_yahoo_session", lambda: session)
    monkeypatch.setattr(yf, "_get_yahoo_data_source", lambda: None)

    sleeps: list[float] = []
    monkeypatch.setattr(yf.time, "sleep", lambda s: sleeps.append(s))

    df = yf.yahoo_chart("600519.SS", range_str="1y")
    assert not df.empty
    assert len(df) == 2
    assert sleeps == [1.0]


def test_yahoo_empty_result_raises(monkeypatch):
    from src.config import settings
    from src.core.yahoo_finance import YahooEmptyResult, yahoo_chart

    monkeypatch.setattr(settings, "yahoo_enabled", True)
    monkeypatch.setattr(settings, "yahoo_max_retries", 1)

    session = MagicMock()
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"chart": {"result": []}}
    resp.raise_for_status = MagicMock()
    session.get.return_value = resp
    monkeypatch.setattr("src.core.yahoo_finance._yahoo_session", lambda: session)
    monkeypatch.setattr("src.core.yahoo_finance._get_yahoo_data_source", lambda: None)

    with pytest.raises(YahooEmptyResult):
        yahoo_chart("000001.SZ", range_str="1y")


def test_yahoo_disabled_skipped_in_adapter(monkeypatch):
    from src.config import settings
    from src.core.kline_fetcher import _YahooHistoryAdapter

    monkeypatch.setattr(settings, "yahoo_enabled", False)
    adapter = _YahooHistoryAdapter()
    assert adapter.fetch_history("600519", start_date="20240101") is None


def test_execute_with_fallback_skips_yahoo_when_disabled(monkeypatch):
    from src.config import settings
    from src.core.data_sources import execute_with_fallback, register_fetch_handler

    monkeypatch.setattr(settings, "yahoo_enabled", False)
    monkeypatch.setattr(settings, "akshare_enabled", False)

    class _StubEastmoney:
        def fetch_history(self, code, *, start_date=None, days=400):
            return pd.DataFrame({
                "date": ["2024-01-02", "2024-01-03"],
                "open": [1.0, 1.1],
                "high": [1.2, 1.3],
                "low": [0.9, 1.0],
                "close": [1.1, 1.2],
                "volume": [100, 110],
                "amount": [0, 0],
                "turnover": [0, 0],
            })

    register_fetch_handler("a_share_history", "東方財富", _StubEastmoney())
    df = execute_with_fallback(
        "a_share_history",
        "fetch_history",
        "600519",
        start_date="20240101",
        days=90,
    )
    assert df is not None
    assert len(df) == 2


def test_record_rate_limit_429_metric():
    from src.core import pipeline_observability as obs

    obs.reset_pipeline_metrics()
    obs.record_rate_limit_429("yahoo")
    metrics = obs.get_pipeline_metrics()
    assert metrics["kline"]["rate_limit_429_by_source"]["yahoo"] == 1


def test_fetch_a_share_history_fallback_after_yahoo_failure(monkeypatch):
    from src.config import settings
    from src.core.data_sources import DataSource, register_fetch_handler
    from src.core.kline_fetcher import fetch_a_share_history

    monkeypatch.setattr(settings, "yahoo_enabled", True)
    monkeypatch.setattr(settings, "akshare_enabled", False)

    yahoo_calls = {"n": 0}

    class _FailingYahoo:
        def fetch_history(self, code, *, start_date=None, days=400):
            yahoo_calls["n"] += 1
            return None

    class _StubEastmoney:
        def fetch_history(self, code, *, start_date=None, days=400):
            return pd.DataFrame({
                "date": ["2024-06-01", "2024-06-02"],
                "open": [1.0, 1.0],
                "high": [1.0, 1.0],
                "low": [1.0, 1.0],
                "close": [1.0, 1.0],
                "volume": [1, 1],
                "amount": [0, 0],
                "turnover": [0, 0],
            })

    register_fetch_handler("a_share_history", "Yahoo Finance", _FailingYahoo())
    register_fetch_handler("a_share_history", "東方財富", _StubEastmoney())

    fake_sources = [
        DataSource("Yahoo Finance", priority=1, rate_limit=0.1),
        DataSource("東方財富", priority=2, rate_limit=0.1),
    ]
    monkeypatch.setattr(
        "src.core.data_sources.get_sources",
        lambda category: fake_sources if category == "a_share_history" else [],
    )

    with patch("src.core.local_kline.persist_kline_df", lambda code, df: None):
        df, src = fetch_a_share_history("600519", start_date="20240101", skip_local=True)

    assert yahoo_calls["n"] == 1
    assert not df.empty
    assert src == "eastmoney"
