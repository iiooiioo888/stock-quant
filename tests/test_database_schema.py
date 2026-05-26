"""資料庫集中 schema 與版本化遷移測試"""
import os
import sqlite3
import tempfile

import pytest


@pytest.fixture
def isolated_db(monkeypatch):
    """每個用例使用獨立臨時庫，避免污染開發庫。"""
    path = os.path.join(tempfile.gettempdir(), f"test_schema_{os.getpid()}.db")
    if os.path.exists(path):
        os.remove(path)
    monkeypatch.setenv("SQ_DB_PATH", path)
    from src.config import settings
    from src.core.database.connection import reset_thread_connection

    settings.db_path = path
    reset_thread_connection()
    yield path
    reset_thread_connection()
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass


def _table_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return {r[0] for r in rows}


def test_init_database_creates_core_tables(isolated_db):
    from src.core.database import init_database, get_schema_version, CURRENT_SCHEMA_VERSION
    from src.core.database.connection import get_conn

    init_database()
    assert get_schema_version() == CURRENT_SCHEMA_VERSION

    with get_conn() as conn:
        tables = _table_names(conn)

    expected = {
        "daily_kline",
        "users",
        "task_log",
        "fundamentals",
        "stock_universe",
        "paper_trades",
        "polymarket_market_snapshot",
        "schema_migrations",
    }
    assert expected.issubset(tables)


def test_migrations_idempotent(isolated_db):
    from src.core.database import init_database, run_migrations, get_schema_version

    init_database()
    v1 = get_schema_version()
    applied = run_migrations()
    v2 = get_schema_version()
    assert applied == 0
    assert v1 == v2


def test_legacy_column_patch(isolated_db):
    """舊庫缺列時，遷移 v2 應補齊。"""
    from src.core.database.connection import get_conn
    from src.core.database.migrations import run_migrations

    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE daily_kline (
                code TEXT NOT NULL,
                date TEXT NOT NULL,
                open REAL, high REAL, low REAL, close REAL,
                volume REAL, amount REAL, turnover REAL,
                PRIMARY KEY (code, date)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE task_log (
                task_id TEXT PRIMARY KEY,
                task_type TEXT NOT NULL,
                params_hash TEXT NOT NULL,
                title TEXT,
                status TEXT NOT NULL,
                progress INTEGER DEFAULT 0,
                error TEXT,
                created_at TEXT,
                completed_at TEXT
            )
            """
        )

    run_migrations()

    with get_conn() as conn:
        dk_cols = {r[1] for r in conn.execute("PRAGMA table_info(daily_kline)").fetchall()}
        tl_cols = {r[1] for r in conn.execute("PRAGMA table_info(task_log)").fetchall()}

    assert "market" in dk_cols
    assert "params_json" in tl_cols


def test_init_db_compat(isolated_db):
    from src.core.db import init_db, get_conn

    init_db()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM schema_migrations"
        ).fetchone()
    assert row[0] >= 1
