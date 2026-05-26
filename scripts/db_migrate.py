#!/usr/bin/env python3
"""手動執行資料庫遷移（等同 init_db 的 schema 部分）。"""
from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.core.database.migrations import (  # noqa: E402
    CURRENT_SCHEMA_VERSION,
    get_schema_version,
    run_migrations,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Stock Quant 資料庫遷移")
    parser.add_argument(
        "--target",
        type=int,
        default=None,
        help=f"目標版本（預設 {CURRENT_SCHEMA_VERSION}）",
    )
    parser.add_argument("--status", action="store_true", help="僅顯示當前 schema 版本")
    args = parser.parse_args()

    if args.status:
        print(f"schema version: {get_schema_version()} / {CURRENT_SCHEMA_VERSION}")
        return 0

    n = run_migrations(target_version=args.target)
    print(f"applied {n} migration(s); now at v{get_schema_version()}/{CURRENT_SCHEMA_VERSION}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
