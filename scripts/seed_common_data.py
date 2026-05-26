#!/usr/bin/env python3
"""預載常見行情與元數據到本地 SQLite。"""
from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def main() -> int:
    parser = argparse.ArgumentParser(description="預載常見數據（日 K、股票庫、板塊等）")
    parser.add_argument(
        "--profile",
        choices=("quick", "standard", "full"),
        default="standard",
        help="quick≈7檔 | standard≈35檔（默認）| full=目錄全集",
    )
    parser.add_argument("--force", action="store_true", help="強制重新下載日 K")
    parser.add_argument("--no-download", action="store_true", help="僅寫目錄/元數據，不下載 K 線")
    parser.add_argument("--sync-universe", action="store_true", help="額外從行情源同步股票庫（較慢）")
    parser.add_argument("--with-backtest", action="store_true", help="生成示範回測記錄")
    parser.add_argument("--json", action="store_true", help="以 JSON 輸出結果")
    args = parser.parse_args()

    from src.core.database.seed import seed_common_data

    result = seed_common_data(
        args.profile,
        force=args.force,
        download=not args.no_download,
        backtest_samples=args.with_backtest or args.profile == "quick",
        sync_universe=args.sync_universe,
    )

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    else:
        dl = result.get("download") or {}
        if dl.get("skipped"):
            print("日 K：已存在，跳過")
        else:
            print(
                f"日 K：成功 {dl.get('ok', 0)}/{result.get('codes_planned', 0)} 檔，"
                f"共 {dl.get('total_records', 0)} 條"
            )
        if result.get("catalog_rows") is not None:
            print(f"股票庫目錄：+{result['catalog_rows']} 條")
        if result.get("realtime_rows"):
            print(f"實時快照：{result['realtime_rows']} 檔")
        if result.get("sector"):
            print(f"板塊快照：{result['sector']}")
        if result.get("fundamentals") is not None:
            print(f"基本面：{result['fundamentals']} 檔")
        if result.get("backtests"):
            print(f"示範回測：{result['backtests']} 條")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
