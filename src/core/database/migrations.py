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


def _migration_005_performance_indexes(conn: sqlite3.Connection) -> None:
    """查詢加速：回測複合索引、任務狀態複合/部分索引。"""
    extra = [
        "CREATE INDEX IF NOT EXISTS idx_bt_code_strategy_created ON backtest_results(code, strategy, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_task_status_created ON task_log(status, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_task_active ON task_log(created_at DESC) WHERE status IN ('pending', 'running')",
    ]
    for idx in extra:
        try:
            conn.execute(idx)
        except sqlite3.OperationalError as e:
            logger.debug(f"索引跳過（可能已存在）: {e}")


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


def _migration_006_multi_currency(conn: sqlite3.Connection) -> None:
    """多幣種結算：用戶偏好幣種 + 日匯率表。"""
    if _table_exists(conn, "users") and not _column_exists(conn, "users", "preferred_currency"):
        try:
            conn.execute(
                "ALTER TABLE users ADD COLUMN preferred_currency TEXT DEFAULT 'MOP'"
            )
            conn.execute(
                """
                UPDATE users SET preferred_currency = 'MOP'
                WHERE preferred_currency IS NULL OR preferred_currency = ''
                """
            )
        except sqlite3.OperationalError as e:
            logger.debug(f"preferred_currency 欄位: {e}")

    if not _table_exists(conn, "fx_rates_daily"):
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS fx_rates_daily (
                base TEXT NOT NULL DEFAULT 'USD',
                target TEXT NOT NULL,
                rate REAL NOT NULL,
                date TEXT NOT NULL,
                PRIMARY KEY (base, target, date)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_fx_date ON fx_rates_daily(date DESC)"
        )


def _migration_007_portfolio_ledger(conn: sqlite3.Connection) -> None:
    """交易驅動資產庫：流水、物化持倉、日快照。"""
    from src.core.database.schema import (
        DDL_PORTFOLIO_HOLDINGS,
        DDL_PORTFOLIO_SNAPSHOTS,
        DDL_PORTFOLIO_TRANSACTIONS,
    )

    conn.execute(DDL_PORTFOLIO_TRANSACTIONS)
    conn.execute(DDL_PORTFOLIO_HOLDINGS)
    conn.execute(DDL_PORTFOLIO_SNAPSHOTS)
    for idx in (
        "CREATE INDEX IF NOT EXISTS idx_port_tx_user_sym_time ON portfolio_transactions(user_id, symbol, executed_at)",
        "CREATE INDEX IF NOT EXISTS idx_port_tx_user_time ON portfolio_transactions(user_id, executed_at)",
        "CREATE INDEX IF NOT EXISTS idx_port_hold_user ON portfolio_holdings(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_port_snap_user_date ON portfolio_snapshots(user_id, snapshot_date DESC)",
    ):
        try:
            conn.execute(idx)
        except sqlite3.OperationalError as e:
            logger.debug(f"portfolio 索引跳過: {e}")


def _migration_008_strategy_likes(conn: sqlite3.Connection) -> None:
    from src.core.database.schema import DDL_STRATEGY_LIKES

    conn.execute(DDL_STRATEGY_LIKES)
    try:
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_strategy_likes_key ON strategy_likes(strategy_key)"
        )
    except sqlite3.OperationalError as e:
        logger.debug(f"strategy_likes 索引跳過: {e}")


def _migration_009_user_isolation(conn: sqlite3.Connection) -> None:
    """回測/預警/信號添加 user_id 列，實現多用戶數據隔離。"""
    for table in ("backtest_results", "alert_log", "signal_log"):
        if _table_exists(conn, table) and not _column_exists(conn, table, "user_id"):
            try:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN user_id INTEGER")
            except sqlite3.OperationalError as e:
                logger.debug(f"{table}.user_id 欄位: {e}")

    extra_indexes = [
        "CREATE INDEX IF NOT EXISTS idx_bt_user ON backtest_results(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_alert_user_id ON alert_log(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_sig_user ON signal_log(user_id)",
    ]
    for idx in extra_indexes:
        try:
            conn.execute(idx)
        except sqlite3.OperationalError as e:
            logger.debug(f"user_isolation 索引跳過: {e}")


MIGRATIONS: list[tuple[int, str, MigrationFn]] = [
    (1, "baseline_schema", _migration_001_baseline),
    (2, "legacy_column_patches", _migration_002_legacy_columns),
    (3, "recover_stale_tasks", _migration_003_post_startup),
    (4, "task_log_pipeline_meta", _migration_004_task_log_meta),
    (5, "performance_indexes", _migration_005_performance_indexes),
    (6, "multi_currency_settlement", _migration_006_multi_currency),
    (7, "portfolio_transaction_ledger", _migration_007_portfolio_ledger),
    (8, "strategy_likes", _migration_008_strategy_likes),
    (9, "user_isolation_backtest_alerts_signals", _migration_009_user_isolation),
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
