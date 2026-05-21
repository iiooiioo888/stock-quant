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
        "src.core.signals._get_prepared_df",
        lambda code: (_ for _ in ()).throw(ValueError("no data")),
    )
    monkeypatch.setattr("src.core.signals._save_signals", lambda s: None)
    out = engine.compute_signals(["000001"])
    assert out == []


def test_score_signal_strength_ignores_hold():
    from src.core.signals import score_signal_strength

    assert score_signal_strength([{"signal": "hold", "strength": 0}]) == 0.0
    s = score_signal_strength([
        {"signal": "buy", "strength": 50},
        {"signal": "hold", "strength": 0},
        {"signal": "buy", "strength": 40},
    ])
    assert s > 0


def test_score_signal_strength_sell_negative():
    from src.core.signals import score_signal_strength

    s = score_signal_strength([
        {"signal": "sell", "strength": -50},
        {"signal": "sell", "strength": -40},
    ])
    assert s < 0


def test_snapshot_cache_roundtrip():
    from src.core.signals import _get_cached_snapshot, _set_cached_snapshot

    payload = [{"code": "000001", "signals": [], "strength": 0}]
    _set_cached_snapshot(["000001"], payload)
    assert _get_cached_snapshot(["000001"]) == payload
