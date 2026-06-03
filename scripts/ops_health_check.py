#!/usr/bin/env python3
"""運維健檢入口（委派 main.py ops check，供 CI / 排程呼叫）。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.cli.commands.ops import cmd_ops
import argparse


def main() -> None:
    argv = sys.argv[1:]
    cmd_ops(
        argparse.Namespace(
            ops_action="check",
            json="--json" in argv,
            verbose="--verbose" in argv,
            ci="--ci" in argv,
        )
    )


if __name__ == "__main__":
    main()
