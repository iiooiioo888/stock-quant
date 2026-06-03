#!/usr/bin/env python3
"""將 ops-report.json 轉為 GitHub Actions Step Summary（Markdown）。"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def render_report(data: dict) -> str:
    """將 ops check JSON 轉為 Markdown 字串。"""
    verdict = data.get("verdict", "?")
    verdict_zh = data.get("verdict_zh", verdict)
    tag = {"ok": "[OK]", "attention": "[WARN]", "critical": "[FAIL]"}.get(verdict, "[?]")
    lines = [
        f"## {tag} Ops SOP — {verdict_zh}\n",
        "| 欄位 | 值 |",
        "|------|-----|",
        f"| verdict | `{verdict}` |",
        f"| exit_code | `{data.get('exit_code', '?')}` |",
    ]
    if data.get("ci_mode"):
        lines.append("| ci_mode | `true` |")
    checks = data.get("checks") or []
    if checks:
        lines.append("\n### 檢查項\n")
        for c in checks:
            mark = "OK" if c.get("ok") else "FAIL"
            lines.append(f"- {mark} **{c.get('name', '?')}**: {c.get('detail', '')}")
    recs = data.get("recommendations") or []
    if recs:
        lines.append("\n### 建議\n")
        for r in recs:
            lines.append(f"- {r}")
    return "\n".join(lines) + "\n"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    path = Path(sys.argv[1] if len(sys.argv) > 1 else "ops-report.json")
    if not path.is_file():
        print("## Ops SOP 健檢\n\n_Report file not found._")
        return 0

    data = json.loads(path.read_text(encoding="utf-8"))
    print(render_report(data), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
