"""CLI：運維健檢（對齊 docs/runbooks SOP）。"""

from __future__ import annotations

import argparse
import json
import sys

from src.cli.helpers import ensure_db
from src.core.ops_health import evaluate_ops_health, format_ops_report


def cmd_ops(args: argparse.Namespace) -> None:
    action = getattr(args, "ops_action", None)
    if action == "check":
        _ops_check(args)
        return
    if action == "probe":
        _ops_probe(args)
        return
    print("用法: python main.py ops {check|probe} [--json] [--ci]")


def _ops_probe(args: argparse.Namespace) -> None:
    from src.core.ops_probe_http import main as probe_main

    argv: list[str] = [
        "--url",
        getattr(args, "url", "http://127.0.0.1:8000/api/health/sop"),
    ]
    argv.extend(["--timeout", str(getattr(args, "timeout", 10.0))])
    if getattr(args, "json", False):
        argv.append("--json")
    if getattr(args, "ci", False):
        argv.append("--ci")
    raise SystemExit(probe_main(argv))


def _ops_check(args: argparse.Namespace) -> None:
    ensure_db()
    evaluation = evaluate_ops_health(ci_mode=bool(getattr(args, "ci", False)))
    if getattr(args, "json", False):
        print(json.dumps(evaluation, ensure_ascii=False, indent=2))
    else:
        print(
            format_ops_report(evaluation, verbose=bool(getattr(args, "verbose", False)))
        )
    raise SystemExit(evaluation["exit_code"])
