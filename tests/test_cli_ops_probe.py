"""CLI: python main.py ops probe"""
import argparse

import pytest

from src.cli.commands.ops import cmd_ops
from src.core import ops_probe_http


def test_ops_probe_delegates(monkeypatch):
    captured: list[list[str]] = []

    def _fake_main(argv):
        captured.append(list(argv))
        return 0

    monkeypatch.setattr(ops_probe_http, "main", _fake_main)

    args = argparse.Namespace(
        ops_action="probe",
        url="http://example/api/health/sop",
        timeout=5.0,
        json=True,
        ci=True,
    )
    with pytest.raises(SystemExit) as exc:
        cmd_ops(args)
    assert exc.value.code == 0
    assert captured
    flat = " ".join(captured[0])
    assert "http://example/api/health/sop" in flat
    assert "--ci" in flat
    assert "--json" in flat
