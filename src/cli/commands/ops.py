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
    print("用法: python main.py ops check [--json] [--verbose]")


def _ops_check(args: argparse.Namespace) -> None:
    ensure_db()
    evaluation = evaluate_ops_health(ci_mode=bool(getattr(args, "ci", False)))
    if getattr(args, "json", False):
        print(json.dumps(evaluation, ensure_ascii=False, indent=2))
    else:
        print(format_ops_report(evaluation, verbose=bool(getattr(args, "verbose", False))))
    raise SystemExit(evaluation["exit_code"])
