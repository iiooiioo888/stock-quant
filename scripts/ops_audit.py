#!/usr/bin/env python3
"""
全面運維稽核 — 本機 check +（可選）HTTP probe + 摘要。

用法:
  python scripts/ops_audit.py
  python scripts/ops_audit.py --with-probe --probe-url http://127.0.0.1:8000/api/health/sop
  python scripts/ops_audit.py --ci
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run(cmd: list[str]) -> tuple[int, str]:
    env = {
        **os.environ,
        "PYTHONUTF8": "1",
        "SQ_LOG_LEVEL": "ERROR",
    }
    r = subprocess.run(
        cmd,
        cwd=ROOT,
        text=True,
        capture_output=True,
        encoding="utf-8",
        env=env,
    )
    return r.returncode, (r.stdout or "").strip()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Stock-quant ops audit (check + optional probe)")
    p.add_argument("--ci", action="store_true", help="CI 退出碼（僅 critical 失敗）")
    p.add_argument("--with-probe", action="store_true", help="服務已啟動時追加 HTTP probe")
    p.add_argument(
        "--probe-url",
        default="http://127.0.0.1:8000/api/health/sop",
        help="probe 目標 URL",
    )
    p.add_argument("--json", action="store_true", help="輸出合併 JSON")
    args = p.parse_args(argv)

    py = sys.executable
    ci_flag = ["--ci"] if args.ci else []
    report: dict = {"steps": []}
    worst = 0

    code, out = _run([py, "main.py", "ops", "check", "--json", *ci_flag])
    check_data = {}
    try:
        check_data = json.loads(out) if out else {}
    except json.JSONDecodeError:
        check_data = {"parse_error": True, "raw": out[:500]}
    report["check"] = check_data
    report["steps"].append({"name": "ops_check", "exit_code": code})
    worst = max(worst, code)

    if args.with_probe:
        probe_cmd = [
            py,
            "main.py",
            "ops",
            "probe",
            "--url",
            args.probe_url,
            "--json",
            *ci_flag,
        ]
        pcode, pout = _run(probe_cmd)
        probe_data = {}
        try:
            probe_data = json.loads(pout)
        except json.JSONDecodeError:
            probe_data = {"raw": pout[:500]}
        report["probe"] = probe_data
        report["steps"].append({"name": "ops_probe", "exit_code": pcode})
        worst = max(worst, pcode)

    report["exit_code"] = worst
    report["verdict"] = check_data.get("verdict")
    report["verdict_zh"] = check_data.get("verdict_zh")

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("=== Stock-Quant 運維稽核 ===")
        print(f"check: {check_data.get('verdict_zh', '?')} (exit {code})")
        if args.with_probe:
            pv = report.get("probe", {})
            print(f"probe: {pv.get('verdict_zh', pv.get('error', '?'))} (exit {report['steps'][-1]['exit_code']})")
        print(f"overall exit: {worst}")

    return worst


if __name__ == "__main__":
    raise SystemExit(main())
