"""
SQLite 連線管理 — 線程本地連接池 + PRAGMA 調優
"""
from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager

from src.config import settings

_thread_local = threading.local()

# 追蹤所有活躍連接（sqlite3.Connection 不支持弱引用，用 list + ID 集合）
_active_conns: list[sqlite3.Connection] = []
_conns_lock = threading.Lock()

# SQLite 頁大小默認 4KB；負數 cache_size 表示 KB（例：-64000 ≈ 64MB）
_DEFAULT_CACHE_PAGES_KB = -64000
_DEFAULT_MMAP_BYTES = 268435456  # 256MB
_DEFAULT_BUSY_TIMEOUT_MS = 5000


def _configure_connection(conn: sqlite3.Connection) -> None:
    cache_kb = int(getattr(settings, "sqlite_cache_size_kb", abs(_DEFAULT_CACHE_PAGES_KB)))
    if cache_kb > 0:
        cache_kb = -cache_kb
    mmap = int(getattr(settings, "sqlite_mmap_size", _DEFAULT_MMAP_BYTES))
    busy_ms = int(getattr(settings, "sqlite_busy_timeout_ms", _DEFAULT_BUSY_TIMEOUT_MS))

    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute(f"PRAGMA cache_size={cache_kb}")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute(f"PRAGMA mmap_size={mmap}")
    conn.execute(f"PRAGMA busy_timeout={busy_ms}")
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
        with _conns_lock:
            _active_conns.append(conn)
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
        with _conns_lock:
            try:
                _active_conns.remove(conn)
            except ValueError:
                pass
        _thread_local.conn = None


def close_idle_connections() -> int:
    """關閉所有追蹤的連接（供生命週期管理或定期清理調用）。

    返回關閉的連接數。
    """
    closed = 0
    with _conns_lock:
        conns_snapshot = list(_active_conns)
        _active_conns.clear()
    for conn in conns_snapshot:
        try:
            conn.close()
            closed += 1
        except Exception:
            pass
    return closed
