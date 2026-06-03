"""src.core.ops_probe_http"""
from fastapi.testclient import TestClient

from src.api.app import app
from src.core.ops_probe_http import fetch_sop, probe_sop_url


def test_fetch_sop_via_testclient():
    client = TestClient(app)
    r = client.get("/api/health/sop")
    assert r.status_code == 200
    # fetch_sop needs real URL — use TestClient transport via app test
    data = r.json()
    assert "sop" in data


def test_probe_sop_url_localhost_not_running():
    summary, code = probe_sop_url("http://127.0.0.1:59999/api/health/sop", timeout=0.5)
    assert summary.get("ok") is False
    assert code == 2


def test_probe_sop_url_with_testclient_server():
    client = TestClient(app)
    # TestClient does not bind TCP; probe uses urllib — monkeypatch fetch
    from src.core import ops_probe_http

    def _fake(_url, _timeout):
        return client.get("/api/health/sop").json()

    orig = ops_probe_http.fetch_sop
    ops_probe_http.fetch_sop = _fake
    try:
        summary, code = probe_sop_url("http://test/api/health/sop", ci_mode=True)
        assert summary.get("ok") is True
        assert summary["verdict"] in ("ok", "attention", "critical")
        assert code in (0, 1, 2)
    finally:
        ops_probe_http.fetch_sop = orig
