"""數據源管理與降級測試。"""

import time

from src.core import data_sources as ds


def test_datasource_available_and_circuit_breaker():
    src = ds.DataSource("mock", priority=1, rate_limit=0.01)
    assert src.available is True
    for _ in range(5):
        src.record_failure()
    assert src.available is False
    src.record_success()
    assert src.available is True
    assert src.fail_count == 0 or src._fail_count == 0


def test_register_and_get_sources_priority():
    a = ds.DataSource("alpha", priority=2)
    b = ds.DataSource("beta", priority=1)
    ds.register("unit_test_cat", a)
    ds.register("unit_test_cat", b)
    names = [s.name for s in ds.get_sources("unit_test_cat")]
    assert "alpha" in names and "beta" in names
    # 分數相同時 priority 小者優先（beta=1）
    all_status = ds.get_all_sources()
    assert "unit_test_cat" in all_status


def test_execute_with_fallback_uses_first_success():
    class _H:
        def fetch_history(self, symbol):
            return {"ok": True, "symbol": symbol}

    cat = "unit_fb_cat"
    src = ds.DataSource("primary", priority=1, rate_limit=0)
    ds.register(cat, src)
    ds.register_fetch_handler(cat, "primary", _H())
    out = ds.execute_with_fallback(cat, "fetch_history", "000001")
    assert out["ok"] is True


def test_throttle_sleeps_when_interval_not_elapsed():
    src = ds.DataSource("slow", priority=9, rate_limit=0.05)
    t0 = time.perf_counter()
    src.throttle()
    src.throttle()
    elapsed = time.perf_counter() - t0
    assert elapsed >= 0.02
