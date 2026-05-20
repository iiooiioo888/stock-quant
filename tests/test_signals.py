"""信號引擎測試"""
import pandas as pd
from unittest.mock import patch

from src.core.signals import SignalEngine


def _fake_kline(n=80):
    import numpy as np
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    close = 10 + np.cumsum(np.random.randn(n) * 0.1)
    return pd.DataFrame({
        "date": dates.strftime("%Y-%m-%d"),
        "open": close,
        "high": close + 0.5,
        "low": close - 0.5,
        "close": close,
        "volume": np.random.randint(1000, 5000, n),
        "amount": close * 1000,
        "turnover": 1.0,
        "market": "a_share",
    })


def test_compute_signals_empty_codes():
    engine = SignalEngine()
    assert engine.compute_signals([]) == []


def test_compute_signals_skips_short_history(monkeypatch):
    engine = SignalEngine()
    monkeypatch.setattr(
        "src.core.signals.load_daily_kline",
        lambda code: pd.DataFrame(),
    )
    monkeypatch.setattr("src.core.signals._save_signals", lambda s: None)
    out = engine.compute_signals(["000001"])
    assert out == []
