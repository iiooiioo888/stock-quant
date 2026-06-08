"""SOP 任務佇列檢查項。"""

from src.core.ops_health import VERDICT_ATTENTION, VERDICT_CRITICAL, evaluate_ops_health


def test_task_queue_critical_when_pending_high():
    ev = evaluate_ops_health(
        {
            "database": {"total_stocks": 1, "db_size_mb": 1},
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
            "task_queue": {"pending": 120, "running": 2, "retrying": 0, "in_flight": 2},
        }
    )
    assert ev["verdict"] == VERDICT_CRITICAL
    ids = [c["id"] for c in ev["checks"]]
    assert "task_queue" in ids


def test_task_queue_attention_when_pending_moderate():
    ev = evaluate_ops_health(
        {
            "database": {"total_stocks": 1},
            "pipeline_metrics": {"cache": {"pending_deferred": 0}},
            "index_audit": {"ok": True, "missing": []},
            "data_sources": {
                "degraded_categories": [],
                "total_categories": 1,
                "healthy_categories": 1,
            },
            "task_queue": {"pending": 25, "running": 0, "retrying": 0, "in_flight": 0},
        }
    )
    assert ev["verdict"] == VERDICT_ATTENTION


def test_task_queue_ok_when_low():
    ev = evaluate_ops_health(
        {
            "database": {"total_stocks": 1},
            "pipeline_metrics": {"cache": {"pending_deferred": 0}},
            "index_audit": {"ok": True, "missing": []},
            "data_sources": {
                "degraded_categories": [],
                "total_categories": 1,
                "healthy_categories": 1,
            },
            "task_queue": {"pending": 3, "running": 1, "retrying": 0, "in_flight": 1},
        }
    )
    tq = [c for c in ev["checks"] if c["id"] == "task_queue"][0]
    assert tq["ok"] is True
