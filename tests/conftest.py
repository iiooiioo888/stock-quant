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
os.environ.setdefault("SQ_DEBUG", "true")
os.environ.setdefault("SQ_DEMO_MODE", "true")
os.environ.setdefault("SQ_LOCAL_FIRST_AUTO_FETCH", "false")

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _reset_rate_limiters():
    """每個用例清空限流桶，避免 register/login 連續觸發 429"""
    from src.api import app as api_module
    for limiter in (api_module._rate_limiter, api_module._auth_rate_limiter):
        limiter._store.clear()
        limiter._last_seen.clear()
    yield


@pytest.fixture
def client(monkeypatch):
    """創建測試客戶端"""
    # API 單元測試只驗證路由契約，避免儀表盤/數據中心端點觸發外部行情源。
    monkeypatch.setattr("src.core.capital_flow.get_market_capital_flow", lambda: [])
    monkeypatch.setattr("src.core.capital_flow.get_north_flow", lambda days=30: [])
    monkeypatch.setattr("src.core.sector.get_sector_capital_flow_rank", lambda top_n=20: [])
    monkeypatch.setattr(
        "src.core.sector.get_sector_change_flow_matrix",
        lambda sector_type="industry", top_n=40: [],
    )
    monkeypatch.setattr(
        "src.core.sector.get_sector_heatmap_data",
        lambda sector_type="industry": [],
    )
    monkeypatch.setattr(
        "src.core.sector.get_sector_performance",
        lambda sector_type="industry", top_n=20: [],
    )
    from src.api.app import app
    return TestClient(app)


@pytest.fixture(scope="session", autouse=True)
def _init_test_db():
    """Session 級別：確保測試數據庫已初始化"""
    from src.core.db import init_db
    init_db()
