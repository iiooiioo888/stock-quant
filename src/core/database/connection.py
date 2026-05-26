"""
SQLite 連線管理 — 線程本地連接池 + PRAGMA 調優
"""
from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager

from src.config import settings

_thread_local = threading.local()


def _configure_connection(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-32000")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA mmap_size=268435456")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")


def _get_thread_conn() -> sqlite3.Connection:
    conn = getattr(_thread_local, "conn", None)
    if conn is None:
        conn = sqlite3.connect(
            settings.db_path,
            check_same_thread=False,
            timeout=10.0,
        )
        _configure_connection(conn)
        _thread_local.conn = conn
    return conn


@contextmanager
def get_conn():
    """獲取數據庫連接（上下文管理器，使用線程本地連接池）"""
    conn = _get_thread_conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def reset_thread_connection() -> None:
    """關閉當前線程連接（測試或切換庫路徑時使用）"""
    conn = getattr(_thread_local, "conn", None)
    if conn is not None:
        try:
            conn.close()
        except Exception:
            pass
        _thread_local.conn = None
