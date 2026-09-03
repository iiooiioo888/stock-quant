"""數據保留清理。"""

import os
import tempfile
import uuid

import pytest


@pytest.fixture
def isolated_db(monkeypatch):
    from src.config import settings
    from src.core.database.connection import reset_thread_connection

    reset_thread_connection()
    path = os.path.join(tempfile.gettempdir(), f"test_ret_{uuid.uuid4().hex}.db")
    monkeypatch.setenv("SQ_DB_PATH", path)
    settings.db_path = path
    reset_thread_connection()
    yield path
    reset_thread_connection()
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass


def test_retention_disabled_is_noop(isolated_db, monkeypatch):
    from src.config import settings
    from src.core.data_retention import purge_old_data
    from src.core.database import init_database

    init_database()
    monkeypatch.setattr(settings, "data_retention_years", 0)
    out = purge_old_data(dry_run=False)
    assert out["enabled"] is False
    assert out["total_deleted"] == 0


def test_retention_deletes_old_kline(isolated_db, monkeypatch):
    from src.config import settings
    from src.core.data_retention import purge_old_data
    from src.core.database import init_database
    from src.core.db import get_conn

    init_database()
    monkeypatch.setattr(settings, "data_retention_years", 1)
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO daily_kline(code, date, open, high, low, close, volume) VALUES (?,?,?,?,?,?,?)",
            ("000001", "2010-01-04", 1, 1, 1, 1, 1),
        )
        conn.execute(
            "INSERT INTO daily_kline(code, date, open, high, low, close, volume) VALUES (?,?,?,?,?,?,?)",
            ("000001", "2026-01-04", 2, 2, 2, 2, 2),
        )
    out = purge_old_data(years=1, dry_run=False)
    assert out["enabled"] is True
    assert out["deleted"].get("daily_kline", 0) >= 1
    with get_conn() as conn:
        left = conn.execute("SELECT date FROM daily_kline ORDER BY date").fetchall()
    assert any("2026" in str(r[0]) for r in left)
    assert not any("2010" in str(r[0]) for r in left)
