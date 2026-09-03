"""週線/月線重採樣與復權正規化。"""

import pandas as pd

from src.core.kline_timeframe import (
    _resample_ohlcv,
    list_timeframes,
    normalize_adj,
    normalize_timeframe,
)


def test_timeframe_aliases_week_month():
    assert normalize_timeframe("weekly") == "1w"
    assert normalize_timeframe("1W") == "1w" or normalize_timeframe("week") == "1w"
    assert normalize_timeframe("monthly") == "1mo"
    ids = {x["id"] for x in list_timeframes()}
    assert "1w" in ids and "1mo" in ids and "1d" in ids


def test_normalize_adj():
    assert normalize_adj("qfq") == "qfq"
    assert normalize_adj("hfq") == "hfq"
    assert normalize_adj("none") == "none"
    assert normalize_adj("bfq") == "none"


def test_resample_weekly_reduces_bars():
    idx = pd.date_range("2024-01-02", periods=20, freq="B")
    df = pd.DataFrame(
        {
            "Open": range(20),
            "High": range(1, 21),
            "Low": range(20),
            "Close": range(20),
            "Volume": [100] * 20,
        },
        index=idx,
    )
    w = _resample_ohlcv(df, "W-FRI")
    assert 1 <= len(w) < 20
    assert set(w.columns) == {"Open", "High", "Low", "Close", "Volume"}
