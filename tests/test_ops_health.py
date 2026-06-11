"""運維健檢評估邏輯。"""

from src.core.ops_health import (
    VERDICT_ATTENTION,
    VERDICT_CRITICAL,
    VERDICT_OK,
    build_health_sop_payload,
    evaluate_ops_health,
)


def test_evaluate_ok_minimal_snapshot():
    ev = evaluate_ops_health(
        {
            "database": {"total_stocks": 10, "db_size_mb": 1.0},
            "pipeline_metrics": {"cache": {"pending_deferred": 0}},
            "index_audit": {
                "ok": True,
                "missing": [],
                "present_count": 5,
                "expected_count": 5,
            },
            "data_sources": {
                "degraded_categories": [],
                "total_categories": 3,
                "healthy_categories": 3,
            },
        }
    )
    assert ev["verdict"] == VERDICT_OK
    assert ev["exit_code"] == 0


def test_evaluate_attention_pending_and_missing_index():
    ev = evaluate_ops_health(
        {
            "database": {"total_stocks": 0},
            "pipeline_metrics": {"cache": {"pending_deferred": 3}},
            "index_audit": {"ok": False, "missing": ["idx_klines_code_date"]},
            "data_sources": {
                "degraded_categories": ["a_share_history"],
                "total_categories": 2,
                "healthy_categories": 1,
            },
        }
    )
    assert ev["verdict"] in (VERDICT_ATTENTION, VERDICT_CRITICAL)
    assert ev["exit_code"] >= 1


def test_evaluate_critical_collect_errors():
    ev = evaluate_ops_health(
        {
            "collect_errors": ["database: locked"],
            "database": {"error": "locked"},
        }
    )
    assert ev["verdict"] == VERDICT_CRITICAL
    assert ev["exit_code"] == 2


def test_build_health_sop_payload_reuses_snapshot(monkeypatch):
    calls = {"n": 0}

    def _collect():
        calls["n"] += 1
        return {
            "pipeline_metrics": {},
            "index_audit": {"ok": True, "missing": []},
            "data_sources": {"degraded_categories": []},
        }

    monkeypatch.setattr("src.core.ops_health.collect_ops_snapshot", _collect)
    snap = {
        "pipeline_metrics": {"x": 1},
        "index_audit": {"ok": True, "missing": []},
        "data_sources": {},
    }
    build_health_sop_payload(snapshot=snap)
    assert calls["n"] == 0


def test_build_health_sop_payload_shape(monkeypatch):
    monkeypatch.setattr(
        "src.core.ops_health.collect_ops_snapshot",
        lambda: {
            "pipeline_metrics": {"cache": {"pending_deferred": 0}},
            "index_audit": {
                "ok": True,
                "missing": [],
                "present_count": 1,
                "expected_count": 1,
            },
            "data_sources": {
                "degraded_categories": [],
                "total_categories": 1,
                "healthy_categories": 1,
            },
            "database": {"total_stocks": 1},
        },
    )
    payload = build_health_sop_payload()
    assert payload["status"] == "ok"
    assert payload["sop"]["verdict"] == VERDICT_OK
    assert "checked_at" in payload
    assert "index_audit" in payload
    assert "data_sources" in payload


def test_ci_mode_suppresses_attention_exit():
    ev = evaluate_ops_health(
        {
            "database": {"total_stocks": 0},
            "pipeline_metrics": {"cache": {"pending_deferred": 0}},
            "index_audit": {"ok": True, "missing": []},
            "data_sources": {
                "degraded_categories": [],
                "total_categories": 1,
                "healthy_categories": 1,
            },
        },
        ci_mode=True,
    )
    assert ev["verdict"] == VERDICT_ATTENTION
    assert ev["exit_code"] == 0
