import numpy as np
import pandas as pd

from src.core.alerts import AlertEngine
from src.core.combo_ga import optimize_weights
from src.core.factor_expression import FactorExpressionError, eval_factor_expression
from src.core.indicators.fast_indicators import compute_macd, compute_rsi, compute_sma
from src.core.indicators.indicator_cache import cache_clear, cache_stats, chunked_apply
from src.core.vectorized_backtest import _signals, can_use_vectorized


def test_factor_expression_ok():
    v = eval_factor_expression("pe_ttm + roe * 2", {"pe_ttm": 10.0, "roe": 3.0})
    assert v == 16.0


def test_factor_expression_rejects_call():
    try:
        eval_factor_expression("__import__('os').system('x')", {})
        assert False
    except FactorExpressionError:
        pass


def test_indicator_cache_hits():
    cache_clear()
    x = np.linspace(10, 20, 80)
    a = compute_rsi(x, 14)
    n1 = cache_stats()["size"]
    b = compute_rsi(x, 14)
    assert np.allclose(a, b, equal_nan=True)
    assert cache_stats()["size"] == n1
    compute_sma(x, 5)
    line, sig, hist = compute_macd(x)
    assert len(line) == len(x) == len(sig) == len(hist)


def test_chunked_sma_matches_full():
    from src.core.indicators.fast_indicators import _sma_core

    rng = np.random.default_rng(0)
    x = np.cumsum(rng.normal(0, 1, 9000)) + 100
    full = _sma_core(x.astype(np.float64), 20)
    chunked = chunked_apply(x.astype(np.float64), lambda a: _sma_core(a, 20), chunk_size=3000, overlap=60)
    assert np.allclose(full[200:], chunked[200:], equal_nan=True, rtol=1e-6, atol=1e-6)


def test_simulate_long_roundtrip():
    from src.core.vectorized_sim import simulate_long

    n = 40
    close = np.linspace(10, 15, n)
    vol = np.full(n, 1e6)
    buy = np.zeros(n, dtype=np.int8)
    sell = np.zeros(n, dtype=np.int8)
    buy[10] = 1
    sell[25] = 1
    eq, npair, *_rest = simulate_long(
        close.astype(np.float64),
        vol.astype(np.float64),
        buy,
        sell,
        100000.0,
        0.00025,
        5.0,
        0.0005,
        0.00001,
        0.0,
        np.int8(0),
        0.05,
        2.0,
        np.int64(0),
        np.int8(0),
        np.int8(0),
        0.10,
        close.astype(np.float64),
        close.astype(np.float64),
        0.0,
        0.0,
        0.0,
    )
    assert len(eq) == n
    assert int(npair) == 1
    close = np.array([10.0] * 10 + list(np.linspace(10, 20, 30)), dtype=float)
    buy, sell = _signals("dual_ma", close, {"fast": 3, "slow": 8})
    assert buy.dtype == bool
    assert len(buy) == len(close)
    assert buy.sum() + sell.sum() >= 0


def test_vectorized_signals_ema_and_boll():
    close = np.array([10.0] * 15 + list(np.linspace(10, 22, 40)), dtype=float)
    b, s = _signals("ema_cross", close, {"fast": 5, "slow": 12})
    assert len(b) == len(close)
    bb, ss = _signals("bollinger", close, {"period": 10, "devfactor": 2.0})
    assert bb.dtype == bool


def test_can_use_vectorized_respects_sl():
    assert can_use_vectorized("dual_ma", engine="auto")
    assert can_use_vectorized("ema_cross", engine="auto")
    assert can_use_vectorized("dual_ma", stop_loss_pct=5, engine="auto")
    assert not can_use_vectorized("turtle", engine="auto")
    assert not can_use_vectorized("dual_ma", engine="backtrader")
    assert not can_use_vectorized("dual_ma", max_position_pct=0.3, engine="auto")


def test_vectorized_stop_loss_exits():
    from src.core.vectorized_sim import simulate_long

    n = 30
    close = np.array([10.0] * 8 + list(np.linspace(10, 7, n - 8)), dtype=np.float64)
    vol = np.full(n, 1e6)
    buy = np.zeros(n, dtype=np.int8)
    sell = np.zeros(n, dtype=np.int8)
    buy[5] = 1
    eq, npair, *_rest = simulate_long(
        close,
        vol,
        buy,
        sell,
        100000.0,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        np.int8(0),
        0.05,
        2.0,
        np.int64(0),
        np.int8(0),
        np.int8(0),
        0.10,
        close,
        close,
        0.08,
        0.0,
        0.0,
    )
    assert int(npair) == 1


def test_combo_ga_weights_sum_to_one():
    rng = np.random.default_rng(1)
    r = rng.normal(0.001, 0.01, size=(80, 3))
    out = optimize_weights(r, generations=8, pop_size=12, seed=1)
    assert abs(sum(out["weights"]) - 1) < 1e-5
    assert len(out["weights"]) == 3


def test_alert_volume_and_rsi(monkeypatch):
    from src.config import settings

    settings.alert_rules["999999"] = {
        "name": "測試",
        "volume_mult": 2,
        "rsi_above": 70,
    }
    settings.alert_cooldown_sec = 0
    eng = AlertEngine()
    row = pd.Series(
        {
            "code": "999999",
            "price": 10.0,
            "change_pct": 0.1,
            "volume": 2000,
            "avg_volume": 500,
            "rsi": 80,
        }
    )
    msgs = eng.check(row)
    assert any("成交量" in m for m in msgs)
    assert any("RSI" in m for m in msgs)
