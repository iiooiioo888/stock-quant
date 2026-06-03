"""CLI、REST、MCP 共用判定一致性。"""
import json

from fastapi.testclient import TestClient

from src.api.app import app
from src.core.ops_health import (
    VERDICT_OK,
    build_health_sop_payload,
    collect_ops_snapshot,
    evaluate_ops_health,
    exit_code_for_verdict,
)
from src.integrations.mcp.tools_observability import handle_sq_ops_check


def test_evaluate_matches_build_payload_verdict():
    snap = collect_ops_snapshot()
    ev = evaluate_ops_health(snap)
    payload = build_health_sop_payload(snapshot=snap)
    assert payload["sop"]["verdict"] == ev["verdict"]
    assert payload["sop"]["exit_code"] == ev["exit_code"]
    assert payload["sop"]["checks"] == ev["checks"]


def test_rest_sop_matches_local_evaluation():
    snap = collect_ops_snapshot()
    ev = evaluate_ops_health(snap)
    client = TestClient(app)
    data = client.get("/api/health/sop").json()
    assert data["sop"]["verdict"] == ev["verdict"]


def test_mcp_sq_ops_check_matches_evaluation():
    snap = collect_ops_snapshot()
    ev = evaluate_ops_health(snap)
    raw = handle_sq_ops_check({})
    data = json.loads(raw)
    assert data["ok"] is True
    assert data["verdict"] == ev["verdict"]
    assert data["checks"] == ev["checks"]


def test_exit_code_for_verdict_table():
    assert exit_code_for_verdict(VERDICT_OK) == 0
    assert exit_code_for_verdict("attention", ci_mode=True) == 0
    assert exit_code_for_verdict("attention", ci_mode=False) == 1
    assert exit_code_for_verdict("critical", ci_mode=True) == 2
