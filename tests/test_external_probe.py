"""對外接口探活。"""
from unittest.mock import patch

import pytest


class TestExternalProbe:
    def test_registry_probe(self):
        from src.core.external_probe import probe_registry
        row = probe_registry()
        assert row["id"] == "registry"
        assert "health" in row.get("detail", {}) or row.get("ok") is not None

    def test_run_all_probes_mocked(self):
        from src.core.external_probe import run_all_probes

        fake = {
            "id": "binance",
            "name": "Binance",
            "category": "crypto",
            "ok": True,
            "latency_ms": 10,
            "message": "OK",
        }
        with patch("src.core.external_probe._PROBE_FUNCS", {"binance": lambda: fake}):
            result = run_all_probes(probe_ids=["binance"], max_workers=1)
        assert result["summary"]["total"] == 1
        assert result["summary"]["ok"] == 1


class TestExternalCheckAPI:
    def test_catalog(self, client):
        resp = client.get("/api/external/check/catalog")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 5

    def test_registry(self, client):
        resp = client.get("/api/external/check/registry")
        assert resp.status_code == 200
        assert "registry" in resp.json()
