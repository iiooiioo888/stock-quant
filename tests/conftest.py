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
def _reset_task_manager_state():
    """隔離任務管理器內存狀態，避免並行/重型任務測試互相污染。"""
    import src.core.task_manager as tm

    def _clear():
        with tm._lock:
            tm._tasks.clear()
            tm._dispatched.clear()
            tm._cancel_flags.clear()
            tm._progress_throttle.clear()
            tm._task_logs.clear()
            tm._pipelines.clear()

    _clear()
    yield
    _clear()


@pytest.fixture(autouse=True)
def _reset_rate_limiters():
    """每個用例清空限流桶，避免 register/login 連續觸發 429"""
    from src.core.rate_limiter import _memory_limiters
    for limiter in _memory_limiters.values():
        limiter._store.clear()
        limiter._last_seen.clear()
    yield


# 測試用管理員控制開關（關閉 invite_only，允許自由註冊）
_TEST_CONTROLS = {
    "version": 3,
    "public_enabled": True,
    "features_enabled": True,
    "strategies_enabled": True,
    "tasks_enabled": True,
    "users_enabled": True,
    "watchlist_enabled": True,
    "scopes": {
        "features": {"enabled": True, "backtest": True, "backtest_advanced": True,
                     "backtest_multi": True, "optimize": True, "portfolio": True,
                     "walkforward": True, "auto_optimize": True, "target_search": True},
        "strategies": {"enabled": True, "list": True, "params": True, "create": True,
                       "builtin_enabled": True, "user_enabled": True,
                       "allowed_names": [], "blocked_names": []},
        "users": {"enabled": True, "register": True, "invite_only": False},
        "watchlist": {"enabled": True, "add": True},
        "tasks": {"enabled": True, "list": True, "queue": True, "types": True, "stats": True,
                  "detail": True, "params": True, "full": True, "logs": True,
                  "cancel": True, "delete": True, "retry": True, "pipeline": True,
                  "batch_cancel": True, "batch_delete": True, "cancel_pending": True,
                  "clear_completed": True, "cleanup": True},
    },
}


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
    # monkeypatch load_controls 使得 lifespan 中 apply_controls_on_startup 使用測試配置
    import src.core.admin_controls as ac
    monkeypatch.setattr(ac, "load_controls", lambda: dict(_TEST_CONTROLS))
    ac._controls = dict(_TEST_CONTROLS)
    from src.api.app import app
    yield TestClient(app)
    ac._controls = None


@pytest.fixture(scope="session", autouse=True)
def _init_test_db():
    """Session 級別：確保測試數據庫已初始化"""
    from src.core.db import init_db
    init_db()


@pytest.fixture(autouse=True)
def _ensure_db_tables():
    """每個用例前確認 DB 表存在（防止並行測試清空 DB）"""
    import sqlite3
    from src.config import settings
    db_path = settings.db_path
    try:
        conn = sqlite3.connect(db_path)
        has_users = conn.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='users'"
        ).fetchone()[0]
        conn.close()
        if not has_users:
            from src.core.db import init_db
            init_db()
    except Exception:
        from src.core.db import init_db
        init_db()
    yield
