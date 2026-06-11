"""ci_ops_summary.py 輸出。"""

import importlib.util
from pathlib import Path


def _load_module():
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "ci_ops_summary",
        root / "scripts" / "ci_ops_summary.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_render_report_markdown():
    mod = _load_module()
    out = mod.render_report(
        {
            "verdict": "attention",
            "verdict_zh": "需關注",
            "exit_code": 1,
            "checks": [{"name": "快取", "ok": False, "detail": "pending=3"}],
            "recommendations": ["檢查批量任務"],
        }
    )
    assert "需關注" in out
    assert "快取" in out
    assert "檢查批量任務" in out
    assert "[WARN]" in out
