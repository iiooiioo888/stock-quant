"""
版本化資料庫遷移 — 在現有 stock.db 上安全升級，不丟數據
"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Callable

from src.core.database.connection import get_conn
from src.core.database.schema import INDEX_DDL, TABLE_DDL
from src.utils.logger import logger

MigrationFn = Callable[[sqlite3.Connection], None]


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r[1] == column for r in rows)


def _migration_001_baseline(conn: sqlite3.Connection) -> None:
    """建立全部表（IF NOT EXISTS）。"""
    for _name, ddl in TABLE_DDL:
        conn.execute(ddl)


def _migration_002_legacy_columns(conn: sqlite3.Connection) -> None:
    """兼容舊庫欄位 + 建立全部索引（須在欄位補齊後）。"""
    if _table_exists(conn, "daily_kline") and not _column_exists(conn, "daily_kline", "market"):
        conn.execute("ALTER TABLE daily_kline ADD COLUMN market TEXT DEFAULT 'a_share'")

    if _table_exists(conn, "task_log") and not _column_exists(conn, "task_log", "params_json"):
        conn.execute("ALTER TABLE task_log ADD COLUMN params_json TEXT")

    if _table_exists(conn, "fundamentals"):
        for col, typ in (("ps_ttm", "REAL"), ("revenue_yoy", "REAL"), ("profit_yoy", "REAL")):
            if not _column_exists(conn, "fundamentals", col):
                try:
                    conn.execute(f"ALTER TABLE fundamentals ADD COLUMN {col} {typ}")
                except sqlite3.OperationalError:
                    pass

    if _table_exists(conn, "stock_universe") and not _column_exists(conn, "stock_universe", "intro"):
        try:
            conn.execute("ALTER TABLE stock_universe ADD COLUMN intro TEXT")
        except sqlite3.OperationalError:
            pass

    for idx in INDEX_DDL:
        conn.execute(idx)


def _migration_003_post_startup(conn: sqlite3.Connection) -> None:
    """啟動後修復：將重啟前未完成的任務標記失敗。"""
    if not _table_exists(conn, "task_log"):
        return
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        """
        UPDATE task_log
        SET status = 'failed', error = '服務重啟', completed_at = ?
        WHERE status IN ('pending', 'running')
        """,
        (now,),
    )


def _migration_004_task_log_meta(conn: sqlite3.Connection) -> None:
    """任務日誌擴展欄位：管道、父任務、meta 快照。"""
    if not _table_exists(conn, "task_log"):
        return
    for col, typ in (
        ("parent_task_id", "TEXT"),
        ("pipeline_id", "TEXT"),
        ("meta_json", "TEXT"),
    ):
        if not _column_exists(conn, "task_log", col):
            try:
                conn.execute(f"ALTER TABLE task_log ADD COLUMN {col} {typ}")
            except sqlite3.OperationalError:
                pass


MIGRATIONS: list[tuple[int, str, MigrationFn]] = [
    (1, "baseline_schema", _migration_001_baseline),
    (2, "legacy_column_patches", _migration_002_legacy_columns),
    (3, "recover_stale_tasks", _migration_003_post_startup),
    (4, "task_log_pipeline_meta", _migration_004_task_log_meta),
]

CURRENT_SCHEMA_VERSION = MIGRATIONS[-1][0] if MIGRATIONS else 0


def _get_applied_versions(conn: sqlite3.Connection) -> set[int]:
    if not _table_exists(conn, "schema_migrations"):
        return set()
    rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
    return {int(r[0]) for r in rows}


def _record_migration(conn: sqlite3.Connection, version: int, name: str) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        """
        INSERT OR IGNORE INTO schema_migrations (version, name, applied_at)
        VALUES (?, ?, ?)
        """,
        (version, name, now),
    )


def run_migrations(target_version: int | None = None) -> int:
    """
    執行待處理遷移。

    Returns:
        本次新執行的遷移數量
    """
    target = target_version if target_version is not None else CURRENT_SCHEMA_VERSION
    applied_count = 0

    with get_conn() as conn:
        # 確保遷移表存在
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                version INTEGER NOT NULL UNIQUE,
                name TEXT NOT NULL,
                applied_at TEXT NOT NULL
            )
            """
        )

        applied = _get_applied_versions(conn)

        for version, name, fn in MIGRATIONS:
            if version > target:
                break
            if version in applied:
                continue
            logger.info(f"資料庫遷移 v{version}: {name}")
            fn(conn)
            _record_migration(conn, version, name)
            applied_count += 1

    if applied_count:
        logger.info(f"資料庫遷移完成：新增 {applied_count} 個版本（目標 v{target}）")
    return applied_count


def get_schema_version() -> int:
    """當前已套用最高遷移版本。"""
    with get_conn() as conn:
        if not _table_exists(conn, "schema_migrations"):
            return 0
        row = conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
    return int(row[0] or 0)
