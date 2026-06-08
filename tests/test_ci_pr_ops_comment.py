"""ci_pr_ops_comment.py 邏輯（無 gh 呼叫）。"""

import importlib.util
import json
from pathlib import Path


def _load():
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "ci_pr_ops_comment",
        root / "scripts" / "ci_pr_ops_comment.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_marker_in_body():
    mod = _load()
    from ci_ops_summary import render_report

    body = f"{mod.MARKER}\n{render_report({'verdict': 'ok', 'verdict_zh': '正常', 'checks': []})}"
    assert mod.MARKER in body
