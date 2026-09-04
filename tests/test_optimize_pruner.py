"""
Optuna 多保真度剪枝（Pruner）測試

驗證：
1. _build_pruner 名稱映射與未知名稱回退
2. median / hyperband 剪枝下壞參數被提前剪枝（全保真度執行次數 < n_trials）
3. 數據量不足時自動退回單保真度
4. 返回結果契約不變（含 params/score/total_return_pct 等欄位）
"""

import numpy as np
import pandas as pd
import pytest

import src.core.optimize as opt_mod
from src.core.optimize import _build_pruner, _resolve_pruner_name, optuna_search


def _fake_df(n_bars: int = 600) -> pd.DataFrame:
    """合成 OHLCV DataFrame（僅供多保真度切片用，不進真實回測）"""
    idx = pd.date_range("2023-01-01", periods=n_bars, freq="B")
    base = np.linspace(10, 20, n_bars)
    return pd.DataFrame(
        {
            "Open": base,
            "High": base * 1.01,
            "Low": base * 0.99,
            "Close": base,
            "Volume": np.full(n_bars, 1_000_000.0),
        },
        index=idx,
    )


@pytest.fixture
def fake_run_single(monkeypatch):
    """用確定性評分替代真實回測：score = -((fast-8)^2 + (slow-30)^2)"""
    calls = {"full": 0, "sub": 0}

    def _fake(code, strategy_name, params, run_ctx=None, data_feed=None):
        score = -((params["fast"] - 8) ** 2 + (params["slow"] - 30) ** 2)
        if data_feed is not None:
            calls["sub"] += 1
        else:
            calls["full"] += 1
        return {
            "params": params,
            "total_return_pct": score / 100.0,
            "sharpe_ratio": float(score),
            "max_drawdown_pct": 5.0,
            "total_trades": 10,
            "win_rate_pct": 55.0,
            "final_value": 100000 + score,
        }

    monkeypatch.setattr(opt_mod, "_run_single", _fake)
    # 多保真度數據載入
    monkeypatch.setattr(
        "src.core.backtest._get_prepared_df", lambda code: _fake_df(600)
    )
    # OOS 驗證依賴 DB 數據，測試環境無此股票 → 自動跳過
    return calls


def test_build_pruner_mapping():
    import optuna

    assert _build_pruner("none") is None
    assert _build_pruner(None) is None
    assert isinstance(_build_pruner("median"), optuna.pruners.MedianPruner)
    assert isinstance(_build_pruner("percentile"), optuna.pruners.PercentilePruner)
    assert isinstance(_build_pruner("hyperband"), optuna.pruners.HyperbandPruner)
    assert _build_pruner("不存在的東西") is None


def test_resolve_pruner_name(monkeypatch):
    assert _resolve_pruner_name("Median") == "median"
    assert _resolve_pruner_name(None) == "none"  # settings 預設 none
    monkeypatch.setattr(opt_mod.settings, "optuna_pruner", "hyperband")
    assert _resolve_pruner_name(None) == "hyperband"
    monkeypatch.setattr(opt_mod.settings, "optuna_pruner", "none")


def test_median_pruner_prunes_bad_trials(fake_run_single, monkeypatch):
    """開啟 median 剪枝後，全保真度回測次數應明顯少於 n_trials"""
    import optuna

    # 固定 TPE 隨機種子，確保測試可重現
    real_create_study = optuna.create_study

    def _seeded_create_study(*args, **kwargs):
        kwargs.setdefault("sampler", optuna.samplers.TPESampler(seed=42))
        return real_create_study(*args, **kwargs)

    monkeypatch.setattr(optuna, "create_study", _seeded_create_study)

    n_trials = 30
    results = optuna_search(
        "TEST",
        "dual_ma",
        objective="sharpe",
        n_trials=n_trials,
        verbose=False,
        pruner="median",
    )

    assert isinstance(results, list) and results, "應返回優化結果"
    for r in results:
        assert "params" in r and "score" in r
        assert "total_return_pct" in r and "sharpe_ratio" in r

    # 剪枝生效：全保真度執行次數 < n_trials（壞參數在低保真階段被剪掉）
    assert fake_run_single["full"] < n_trials
    # 低保真度評估確實發生過
    assert fake_run_single["sub"] >= n_trials


def test_hyperband_pruner_runs(fake_run_single, monkeypatch):
    import optuna

    real_create_study = optuna.create_study

    def _seeded_create_study(*args, **kwargs):
        kwargs.setdefault("sampler", optuna.samplers.TPESampler(seed=7))
        return real_create_study(*args, **kwargs)

    monkeypatch.setattr(optuna, "create_study", _seeded_create_study)

    results = optuna_search(
        "TEST", "dual_ma", n_trials=20, verbose=False, pruner="hyperband"
    )
    assert isinstance(results, list) and results


def test_pruner_fallback_on_short_data(fake_run_single, monkeypatch):
    """數據量 < 400 根時自動退回單保真度，不報錯"""
    monkeypatch.setattr(
        "src.core.backtest._get_prepared_df", lambda code: _fake_df(100)
    )
    results = optuna_search(
        "TEST", "dual_ma", n_trials=8, verbose=False, pruner="median"
    )
    assert isinstance(results, list) and results
    # 退回單保真度：不應有低保真度子集調用
    assert fake_run_single["sub"] == 0


def test_pruner_none_keeps_legacy_behavior(fake_run_single):
    """pruner=none 時不應有多保真度子集調用"""
    results = optuna_search(
        "TEST", "dual_ma", n_trials=8, verbose=False, pruner="none"
    )
    assert isinstance(results, list) and results
    assert fake_run_single["sub"] == 0
    assert fake_run_single["full"] == 8
