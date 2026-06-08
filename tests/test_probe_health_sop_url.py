"""scripts/probe_health_sop_url.py / src.core.ops_probe_http"""

from fastapi.testclient import TestClient

from src.core import ops_probe_http as probe
from src.core.ops_health import exit_code_for_verdict
from src.api.app import app


def test_fetch_sop_via_testclient():
    client = TestClient(app)
    r = client.get("/api/health/sop")
    assert r.status_code == 200
    data = r.json()
    assert data["sop"]["verdict"] in ("ok", "attention", "critical")


def test_exit_code_for_verdict_ci_mode():
    assert exit_code_for_verdict("ok", ci_mode=False) == 0
    assert exit_code_for_verdict("attention", ci_mode=True) == 0
    assert exit_code_for_verdict("attention", ci_mode=False) == 1
    assert exit_code_for_verdict("critical", ci_mode=True) == 2


def test_main_json_ok(monkeypatch):
    payload = {
        "status": "ok",
        "checked_at": 1.0,
        "sop": {"verdict": "ok", "verdict_zh": "正常"},
    }

    monkeypatch.setattr(probe, "fetch_sop", lambda _url, _t: payload)
    rc = probe.main(["--json", "--url", "http://test/api/health/sop"])
    assert rc == 0


def test_main_critical(monkeypatch):
    monkeypatch.setattr(
        probe,
        "fetch_sop",
        lambda _u, _t: {"sop": {"verdict": "critical", "verdict_zh": "異常"}},
    )
    assert probe.main([]) == 2
