"""常見數據預載測試"""
import os
import tempfile

import pytest


@pytest.fixture
def isolated_db(monkeypatch):
    path = os.path.join(tempfile.gettempdir(), f"test_seed_{os.getpid()}.db")
    if os.path.exists(path):
        os.remove(path)
    monkeypatch.setenv("SQ_DB_PATH", path)
    from src.config import settings
    from src.core.database.connection import reset_thread_connection

    settings.db_path = path
    reset_thread_connection()
    yield path
    reset_thread_connection()


def test_seed_universe_catalog(isolated_db):
    from src.core.database import init_database, seed_universe_catalog
    from src.core.database.connection import get_conn

    init_database()
    n = seed_universe_catalog()
    assert n > 0

    with get_conn() as conn:
        row = conn.execute(
            "SELECT name FROM stock_universe WHERE code='600519' AND market='a_share'"
        ).fetchone()
    assert row is not None
    assert "茅台" in row[0]
