"""板塊拉取兜底邏輯"""
from src.core import sector as sec


def test_snapshot_preferred_before_http(monkeypatch):
    sec._sector_list_cache.clear()
    sec._sector_list_stale.clear()
    sec._sector_fetch_blocked_until.clear()

    called = {"http": 0}
    snapshot = [{
        "name": "銀行",
        "code": "",
        "change_pct": 1.0,
        "type": "industry",
        "from_snapshot": True,
        "snapshot_date": "2026-05-20",
    }]

    def _http(_t):
        called["http"] += 1
        return [], False

    monkeypatch.setattr(sec, "_cache_get_sector_list", lambda _t: None)
    monkeypatch.setattr(sec, "_load_sectors_from_snapshot", lambda _t: snapshot)
    monkeypatch.setattr(sec, "_load_sectors_from_local_kline", lambda _t: [])
    monkeypatch.setattr(sec, "_fetch_sector_list_em_http", _http)

    out = sec.get_sector_list("industry")
    assert out[0]["name"] == "銀行"
    assert out[0]["from_snapshot"] is True
    assert called["http"] == 0


def test_local_kline_preferred_before_http_when_no_snapshot(monkeypatch):
    sec._sector_list_cache.clear()
    sec._sector_list_stale.clear()
    sec._sector_fetch_blocked_until.clear()

    called = {"http": 0}
    local = [{"name": "券商", "change_pct": 0.5, "type": "industry", "from_local_kline": True}]

    def _http(_t):
        called["http"] += 1
        return [], False

    monkeypatch.setattr(sec, "_cache_get_sector_list", lambda _t: None)
    monkeypatch.setattr(sec, "_load_sectors_from_snapshot", lambda _t: [])
    monkeypatch.setattr(sec, "_load_sectors_from_local_kline", lambda _t: local)
    monkeypatch.setattr(sec, "_fetch_sector_list_em_http", _http)

    out = sec.get_sector_list("industry")
    assert out[0]["name"] == "券商"
    assert out[0]["from_local_kline"] is True
    assert called["http"] == 0


def test_stale_cache_on_connection_failure(monkeypatch):
    sec._sector_list_cache.clear()
    sec._sector_list_stale.clear()
    sec._sector_fetch_blocked_until.clear()

    stale_data = [{"name": "銀行", "code": "BK0475", "change_pct": 1.0, "type": "industry"}]
    sec._sector_list_stale["industry"] = stale_data
    sec._sector_list_cache["industry"] = (0, stale_data)  # 強制過期

    monkeypatch.setattr(sec, "_cache_get_sector_list", lambda _t: None)
    monkeypatch.setattr(
        sec,
        "_fetch_sector_list_em_http",
        lambda _t: ([], True),
    )
    monkeypatch.setattr(sec, "_fetch_sector_list_live", lambda _t: [])
    monkeypatch.setattr(sec, "_load_sectors_from_snapshot", lambda _t: [])
    monkeypatch.setattr(sec, "_load_sectors_from_local_kline", lambda _t: [])

    out = sec.get_sector_list("industry")
    assert len(out) == 1
    assert out[0]["name"] == "銀行"
    assert sec._sector_fetch_blocked_until["industry"] > sec.time.time()


def test_cooldown_skips_http(monkeypatch):
    sec._sector_list_cache.clear()
    sec._sector_list_stale.clear()
    sec._sector_fetch_blocked_until.clear()

    sec._sector_list_stale["concept"] = [{"name": "AI", "change_pct": 2.0, "type": "concept"}]
    sec._sector_fetch_blocked_until["concept"] = sec.time.time() + 60

    called = {"http": 0}

    def _http(_t):
        called["http"] += 1
        return [], True

    monkeypatch.setattr(sec, "_cache_get_sector_list", lambda _t: None)
    monkeypatch.setattr(sec, "_fetch_sector_list_em_http", _http)
    monkeypatch.setattr(sec, "_load_sectors_from_snapshot", lambda _t: [])

    out = sec.get_sector_list("concept")
    assert called["http"] == 0
    assert out[0]["name"] == "AI"


def test_sector_flow_is_degraded_detects_fallback_rows():
    items = [
        {
            "name": "銀行",
            "main_net": 0.0,
            "source": "sector_list_fallback",
            "degraded": True,
        },
    ]
    assert sec.sector_flow_is_degraded(items) is True


def test_sector_flow_is_degraded_false_when_real_flow():
    items = [
        {"name": "銀行", "main_net": 1.5e8, "main_net_pct": 2.1, "source": "eastmoney"},
    ]
    assert sec.sector_flow_is_degraded(items) is False
