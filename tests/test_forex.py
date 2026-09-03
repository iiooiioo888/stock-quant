"""外匯模組單元測試（mock HTTP）。"""

from unittest.mock import MagicMock, patch

import pandas as pd

from src.core.forex import FOREX_PAIRS, _split_pair, get_forex_pairs, get_forex_realtime


def test_forex_pairs_catalog():
    pairs = get_forex_pairs()
    assert "USDCNY" in pairs
    assert "EURUSD" in FOREX_PAIRS
    assert pairs is not FOREX_PAIRS


def test_split_pair_standard():
    assert _split_pair("USDCNY") == ("USD", "CNY")
    assert _split_pair("EUR/USD") == ("EUR", "USD")
    assert _split_pair("usd-jpy") == ("USD", "JPY")


def test_get_forex_realtime_mock():
    payload = {"amount": 1, "base": "USD", "date": "2026-01-02", "rates": {"CNY": 7.2}}
    mock_resp = MagicMock()
    mock_resp.json.return_value = payload
    mock_resp.raise_for_status = MagicMock()
    with patch("src.core.forex.requests.get", return_value=mock_resp):
        row = get_forex_realtime("USDCNY")
    assert row["price"] == 7.2
    assert row["base"] == "USD"
    assert row["source"] == "frankfurter"


def test_download_forex_kline_empty_on_error():
    from src.core.forex import download_forex_kline

    with patch("src.core.forex.requests.get", side_effect=RuntimeError("net")):
        df = download_forex_kline("USDCNY", start_date="20260101", end_date="20260110")
    assert df is None or (isinstance(df, pd.DataFrame) and (df.empty or len(df) == 0))
