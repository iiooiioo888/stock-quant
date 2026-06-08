"""策略目錄靜態檔與 API 一致性。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "static" / "data" / "strategy-catalog.json"


def test_strategy_catalog_json_exists_and_valid():
    assert (
        CATALOG_PATH.is_file()
    ), "static/data/strategy-catalog.json 缺失，請執行 scripts/build_strategy_catalog.py"
    data = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    assert isinstance(data.get("cats"), list) and len(data["cats"]) >= 10
    strats = data.get("strats") or []
    assert len(strats) >= 100
    impl = [
        s for s in strats if s.get("status") == "implemented" and s.get("backend_key")
    ]
    assert len(impl) >= 25
    for s in impl:
        assert s.get("id") and s.get("name") and s.get("cat")


def test_strategies_list_matches_catalog_impl(client):
    r = client.get("/api/strategies/list")
    assert r.status_code == 200
    body = r.json()
    builtin_keys = {b["name"] for b in body.get("builtin") or []}
    data = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    catalog_keys = {
        s["backend_key"]
        for s in data.get("strats", [])
        if s.get("status") == "implemented" and s.get("backend_key")
    }
    assert builtin_keys == catalog_keys
