"""股票篩選器測試"""

import pandas as pd
import numpy as np
from unittest.mock import patch

from src.core.screener import screen_stocks


def _fake_kline(n=120):
    dates = pd.date_range("2023-01-01", periods=n, freq="B")
    close = 10 + np.cumsum(np.random.randn(n) * 0.05)
    return pd.DataFrame(
        {
            "date": dates.strftime("%Y-%m-%d"),
            "open": close,
            "high": close + 0.3,
            "low": close - 0.3,
            "close": close,
            "volume": np.full(n, 5000.0),
            "amount": close * 5000,
            "turnover": 1.0,
            "market": "a_share",
        }
    )


def test_screen_stocks_ma_bullish(monkeypatch):
    monkeypatch.setattr(
        "src.core.db.load_daily_kline",
        lambda code: _fake_kline(),
    )
    results = screen_stocks(
        codes=["000001"],
        filters={"ma_bullish": True},
    )
    assert isinstance(results, list)
