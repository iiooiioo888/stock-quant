"""
置換過擬合檢測（Permutation Test）測試

驗證：
1. _permute_price_df 保持結構與收益率分佈
2. permutation_test 對「無邊際優勢」策略判定不顯著
3. permutation_test 對「利用時序自相關」策略判定顯著
4. 參數校驗
"""

import numpy as np
import pandas as pd
import pytest

import src.core.walkforward as wf
from src.core.walkforward import _permute_price_df, permutation_test


def _make_df(returns: np.ndarray, start: str = "2023-01-02") -> pd.DataFrame:
    """由日收益率序列構造 OHLCV DataFrame"""
    n = len(returns) + 1
    close = 10.0 * np.exp(np.concatenate([[0.0], np.cumsum(returns)]))
    dates = pd.date_range(start, periods=n, freq="B")
    return pd.DataFrame(
        {
            "open": close * 0.999,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": np.full(n, 1_000_000.0),
            "date": dates.strftime("%Y-%m-%d"),
        }
    )


def test_permute_preserves_structure_and_distribution():
    rng = np.random.default_rng(42)
    rets = np.random.default_rng(7).normal(0.001, 0.02, 300)
    df = _make_df(rets)

    out = _permute_price_df(df, rng)

    # 結構保持
    assert len(out) == len(df)
    assert list(out.columns) == list(df.columns)
    # 首日收盤價不變
    assert out["close"].iloc[0] == pytest.approx(df["close"].iloc[0])
    # 對數收益率多重集不變（僅順序打亂）
    orig_rets = np.sort(np.diff(np.log(df["close"].to_numpy())))
    perm_rets = np.sort(np.diff(np.log(out["close"].to_numpy())))
    np.testing.assert_allclose(orig_rets, perm_rets, rtol=1e-9)
    # high >= close >= low 關係保持
    assert (out["high"] >= out["close"]).all()
    assert (out["low"] <= out["close"]).all()


@pytest.fixture
def mock_backtest(monkeypatch):
    """攔截數據載入與回測執行"""

    def _patch(df, score_fn):
        monkeypatch.setattr(wf, "load_daily_kline", lambda code: df.copy())
        monkeypatch.setattr(
            wf,
            "_run_backtest_on_df",
            lambda d, s, p, cash=100000: {
                "total_return_pct": 0.0,
                "sharpe_ratio": float(score_fn(d)),
                "max_drawdown_pct": 1.0,
                "total_trades": 10,
                "win_rate_pct": 50.0,
            },
        )

    return _patch


def test_permutation_not_significant_for_path_return(mock_backtest):
    """對置換不變的分數（上漲天數計數）：p_value 應為 1.0 → 不顯著"""
    rets = np.random.default_rng(1).normal(0.001, 0.02, 300)
    df = _make_df(rets)
    # 分數 = 上漲天數（整數計數，對置換精確不變，無浮點誤差）
    mock_backtest(
        df, lambda d: float(np.sum(np.diff(d["close"].to_numpy()) > 0))
    )

    out = permutation_test("TEST", "dual_ma", {"fast": 5, "slow": 20},
                           n_permutations=30, seed=42)
    assert out["n_permutations"] == 30
    assert out["p_value"] == 1.0
    assert out["significant"] is False
    assert "警告" in out["verdict"]


def test_permutation_significant_for_autocorrelation_edge(mock_backtest):
    """利用自相關的策略：真實序列高分、置換序列趨零 → 顯著"""
    # 構造強正自相關（趨勢）收益率序列
    rng = np.random.default_rng(3)
    noise = rng.normal(0, 0.01, 400)
    rets = np.zeros(400)
    rets[0] = noise[0]
    for i in range(1, 400):
        rets[i] = 0.6 * np.sign(rets[i - 1]) * 0.01 + noise[i]  # 動量延續
    df = _make_df(rets)

    def _momentum_score(d):
        c = d["close"].astype(float).to_numpy()
        r = np.diff(np.log(c))
        # 昨日漲則今日做多：收益 = sum(sign(r_{t-1}) * r_t)
        return float(np.sum(np.sign(r[:-1]) * r[1:]))

    mock_backtest(df, _momentum_score)

    out = permutation_test("TEST", "dual_ma", {"fast": 5, "slow": 20},
                           n_permutations=50, seed=42)
    assert out["real_score"] > out["perm_p95"], "真實分數應高於隨機 95 分位"
    assert out["p_value"] < 0.05
    assert out["significant"] is True
    assert "通過" in out["verdict"]


def test_permutation_validation(mock_backtest, monkeypatch):
    df = _make_df(np.random.default_rng(5).normal(0, 0.01, 100))
    mock_backtest(df, lambda d: 0.0)

    with pytest.raises(ValueError, match="未知策略"):
        permutation_test("TEST", "no_such_strategy", {"a": 1})
    with pytest.raises(ValueError, match="需要指定策略參數"):
        permutation_test("TEST", "dual_ma", {})

    # 無數據：load 返回空 DataFrame
    monkeypatch.setattr(wf, "load_daily_kline", lambda code: pd.DataFrame())
    with pytest.raises(ValueError, match="無數據"):
        permutation_test("GHOST_CODE", "dual_ma", {"fast": 5, "slow": 20})


def test_walk_forward_signature_has_permutation_n():
    """walk_forward 應接受 permutation_n 參數（默認 0 = 關閉）"""
    import inspect

    sig = inspect.signature(wf.walk_forward)
    assert "permutation_n" in sig.parameters
    assert sig.parameters["permutation_n"].default == 0
