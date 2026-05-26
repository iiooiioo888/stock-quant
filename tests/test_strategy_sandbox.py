"""策略上傳沙箱 — 安全校驗單元測試"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.strategy_sandbox import (
    sanitize_strategy_filename,
    validate_strategy_source,
)

_SAFE_TEMPLATE = '''
from src.core.strategy_base import UserStrategy

class DemoStrategy(UserStrategy):
    name = "demo"
    def buy_signal(self, df, index):
        return False
    def sell_signal(self, df, index):
        return False
'''


def test_sanitize_filename_rejects_traversal():
    assert sanitize_strategy_filename("../evil.py") is None
    assert sanitize_strategy_filename("ok_strategy.py") == "ok_strategy.py"


def test_validate_accepts_minimal_strategy():
    r = validate_strategy_source(_SAFE_TEMPLATE)
    assert r.ok, r.error


def test_validate_rejects_os_import():
    bad = _SAFE_TEMPLATE + "\nimport os\n"
    r = validate_strategy_source(bad)
    assert not r.ok
    assert "禁止" in r.error


def test_validate_rejects_eval():
    bad = _SAFE_TEMPLATE.replace(
        "return False",
        "eval('1')",
        1,
    )
    r = validate_strategy_source(bad)
    assert not r.ok


def test_validate_rejects_dunder_escape():
    bad = _SAFE_TEMPLATE + "\nx = ().__class__.__bases__\n"
    r = validate_strategy_source(bad)
    assert not r.ok


def test_validate_rejects_open_call():
    bad = _SAFE_TEMPLATE + "\nopen('/etc/passwd')\n"
    r = validate_strategy_source(bad)
    assert not r.ok
