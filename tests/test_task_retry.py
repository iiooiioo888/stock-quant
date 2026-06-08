"""task_retry 單元測試。"""

import pytest

from src.core.task_retry import RetryWorkerError, build_retry_worker


def test_build_retry_worker_backtest():
    fn = build_retry_worker(
        "backtest",
        {"code": "000001", "strategy": "dual_ma"},
        "tid-1",
    )
    assert callable(fn)


def test_build_retry_worker_unsupported():
    with pytest.raises(RetryWorkerError):
        build_retry_worker("heatmap", {"code": "000001"}, "tid-2")


def test_build_retry_worker_portfolio_unknown_method():
    fn = build_retry_worker(
        "portfolio",
        {"method": "not-a-real-method", "allocations": []},
        "tid-3",
    )
    with pytest.raises(RetryWorkerError):
        fn()
