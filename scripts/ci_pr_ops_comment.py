#!/usr/bin/env python3
"""
PR 運維評論 — 使用固定 marker 更新同一則評論，避免重複刷屏。

環境變數:
  GH_TOKEN / GITHUB_TOKEN
  PR_NUMBER — pull_request.number
  GITHUB_REPOSITORY — owner/repo
  OPS_PR_COMMENT_ALWAYS=1 — 即使 verdict=ok 也一律更新/建立評論
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

MARKER = "<!-- stock-quant-ops-check -->"

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from ci_ops_summary import render_report  # noqa: E402


def _run(cmd: list[str]) -> str:
    r = subprocess.run(cmd, text=True, capture_output=True, encoding="utf-8")
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout or "gh failed").strip())
    return (r.stdout or "").strip()


def _list_comments(repo: str, pr: str) -> list[dict]:
    raw = _run([
        "gh", "api",
        f"repos/{repo}/issues/{pr}/comments",
        "--paginate",
        "-q", ".[] | {id, body}",
    ])
    return json.loads(raw) if raw.startswith("[") else []


def _patch_comment(repo: str, comment_id: int, body: str) -> None:
    _run([
        "gh", "api",
        "-X", "PATCH",
        f"repos/{repo}/issues/comments/{comment_id}",
        "-f", f"body={body}",
    ])


def _create_comment(pr: str, body: str) -> None:
    _run(["gh", "pr", "comment", pr, "--body", body])


def main() -> int:
    report_path = Path(sys.argv[1] if len(sys.argv) > 1 else "ops-report.json")
    pr = os.environ.get("PR_NUMBER", "").strip()
    repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if not pr or not repo:
        print("skip: not a PR context")
        return 0
    if not report_path.is_file():
        print("skip: ops-report.json missing")
        return 0

    data = json.loads(report_path.read_text(encoding="utf-8"))
    verdict = data.get("verdict", "ok")
    body = f"{MARKER}\n{render_report(data)}"
    always = os.environ.get("OPS_PR_COMMENT_ALWAYS", "").strip() == "1"

    try:
        comments = _list_comments(repo, pr)
    except Exception as e:
        print(f"list comments failed: {e}")
        comments = []

    existing_id = None
    for c in comments:
        if MARKER in (c.get("body") or ""):
            existing_id = c.get("id")
            break

    if existing_id is not None:
        _patch_comment(repo, int(existing_id), body)
        print(f"updated comment {existing_id} ({verdict})")
        return 0

    if verdict == "ok" and not always:
        print("skip: ok, no existing PR comment")
        return 0

    if verdict not in ("attention", "critical") and not always:
        print(f"skip: verdict={verdict}")
        return 0

    _create_comment(pr, body)
    print(f"created PR comment ({verdict})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
