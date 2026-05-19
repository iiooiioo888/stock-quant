"""
測試配置 — 設置測試環境變量
"""
import os
import sys
import tempfile

# 確保項目根目錄在 sys.path 中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 測試環境配置（避免影響生產數據）
_test_db = os.path.join(tempfile.gettempdir(), "test_stock.db")
os.environ.setdefault("SQ_DB_PATH", _test_db)
os.environ.setdefault("SQ_REDIS_ENABLED", "false")
os.environ.setdefault("SQ_LOG_LEVEL", "WARNING")

import pytest


@pytest.fixture(scope="session", autouse=True)
def _init_test_db():
    """Session 級別：確保測試數據庫已初始化"""
    from src.core.db import init_db
    init_db()
