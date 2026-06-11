"""統一資料庫連線層 — SQLite + PostgreSQL (psycopg3)"""

from __future__ import annotations
import re, sqlite3, threading
from contextlib import contextmanager
from src.config import settings
from src.utils.logger import logger


def is_postgres() -> bool:
    url = getattr(settings, "database_url", "") or ""
    return url.startswith(("postgresql://", "postgres://"))


def convert_placeholders(sql: str) -> str:
    return sql.replace("?", "%s")


_DEFAULT_PK_MAP = {
    "daily_kline": ("code", "date"),
    "realtime_snapshot": ("code",),
    "minute_kline": ("code", "datetime", "period"),
    "sector_data": ("sector_name", "sector_type", "code"),
    "sector_snapshot": ("sector_name", "sector_type", "snapshot_date"),
    "capital_flow": ("code", "date", "flow_type"),
    "dragon_tiger": ("code", "date"),
    "fundamentals": ("code", "update_date"),
    "stock_universe": ("code", "market"),
    "task_log": ("task_id",),
    "schema_migrations": ("version",),
    "users": ("id",),
    "alert_log": ("id",),
    "backtest_results": ("id",),
    "signal_log": ("id",),
    "strategy_leaderboard": ("id",),
    "user_watchlists": ("id",),
    "user_alert_rules": ("id",),
    "paper_trades": ("id",),
    "paper_sessions": ("id",),
    "paper_positions": ("session_id", "code"),
    "fx_rates_daily": ("base", "target", "date"),
    "portfolio_transactions": ("id",),
    "portfolio_holdings": ("user_id", "symbol"),
    "portfolio_snapshots": ("user_id", "snapshot_date", "currency"),
    "strategies": ("id",),
    "ratings": ("id",),
}


class SQLiteRow:
    def __init__(self, cursor, values):
        desc = cursor.description
        self._col_names = [d[0] for d in desc] if desc else []
        self._values = values
        self._dict = dict(zip(self._col_names, self._values)) if self._col_names else {}

    def __getitem__(self, key):
        if isinstance(key, (int, slice)):
            return self._values[key]
        return self._dict[key]

    def __contains__(self, key):
        return key in self._dict

    def __iter__(self):
        return iter(self._values)

    def __len__(self):
        return len(self._values)

    def __repr__(self):
        return f"SQLiteRow({self._dict})"

    def keys(self):
        return self._col_names

    def __eq__(self, other):
        if isinstance(other, SQLiteRow):
            return self._values == other._values
        return NotImplemented

    def __hash__(self):
        return hash(self._values)


def _make_row_factory(cursor):
    def factory(values):
        return SQLiteRow(cursor, values)

    return factory


Row = SQLiteRow


class PGCursor:
    def __init__(self, pg_cursor):
        self._cur = pg_cursor
        self.lastrowid = None
        self.rowcount = 0
        self._row_factory = None

    @property
    def row_factory(self):
        return self._row_factory

    @row_factory.setter
    def row_factory(self, value):
        self._row_factory = value

    def execute(self, sql, parameters=()):
        converted = convert_placeholders(sql)
        _upper = sql.lstrip().upper()
        _is_insert = _upper.startswith("INSERT")
        if _is_insert and "RETURNING" not in _upper:
            converted = converted.rstrip().rstrip(";") + " RETURNING id"
        try:
            self._cur.execute(converted, parameters)
        except Exception as e:
            if _is_insert and "RETURNING" in converted:
                try:
                    self._cur.execute(
                        converted.replace(" RETURNING id", ""), parameters
                    )
                    self.rowcount = self._cur.rowcount or 0
                    return self
                except Exception:
                    pass
            raise
        self.rowcount = self._cur.rowcount or 0
        if _is_insert and self._cur.description:
            try:
                row = self._cur.fetchone()
                if row:
                    self.lastrowid = (
                        row[0]
                        if isinstance(row, (list, tuple))
                        else list(row.values())[0]
                    )
            except Exception:
                pass
        return self

    def executemany(self, sql, parameters_seq=()):
        converted = convert_placeholders(sql)
        if not parameters_seq:
            self.rowcount = 0
            return self
        self._cur.executemany(converted, parameters_seq)
        self.rowcount = self._cur.rowcount or 0
        return self

    def fetchone(self):
        row = self._cur.fetchone()
        if row is None:
            return None
        if self._row_factory:
            return self._row_factory(row)
        return row

    def fetchall(self):
        rows = self._cur.fetchall()
        if self._row_factory:
            return [self._row_factory(r) for r in rows]
        return rows

    @property
    def description(self):
        return self._cur.description

    def close(self):
        self._cur.close()


class PGConnection:
    def __init__(self, pg_conn):
        self._conn = pg_conn
        self._row_factory = None

    @property
    def row_factory(self):
        return self._row_factory

    @row_factory.setter
    def row_factory(self, value):
        self._row_factory = value

    def execute(self, sql, parameters=()):
        cur = self._conn.cursor()
        pg_cur = PGCursor(cur)
        if self._row_factory:
            pg_cur.row_factory = _make_row_factory(pg_cur)
        pg_cur.execute(sql, parameters)
        return pg_cur

    def executemany(self, sql, parameters_seq=()):
        cur = self._conn.cursor()
        pg_cur = PGCursor(cur)
        pg_cur.executemany(sql, parameters_seq)
        return pg_cur

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()


_pg_tls = threading.local()
_pg_warned = False


def _get_pg_conn():
    global _pg_warned
    conn = getattr(_pg_tls, "conn", None)
    if conn:
        try:
            # psycopg3 使用 execute 進行健康檢查
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
            return conn
        except Exception:
            try:
                conn.close()
            except Exception:
                pass
            _pg_tls.conn = None
    
    # 使用 psycopg3 (psycopg) 替代 psycopg2
    import psycopg
    from psycopg import Connection

    url = settings.database_url
    if not url:
        raise ValueError("database_url 為空")
    
    # psycopg3 支援直接傳入 URL
    pg_conn: Connection = psycopg.connect(url, autocommit=False)
    conn = PGConnection(pg_conn)
    _pg_tls.conn = conn
    if not _pg_warned:
        logger.info(f"PostgreSQL 連接已建立 (psycopg3)")
        _pg_warned = True
    return conn


def _reset_pg():
    conn = getattr(_pg_tls, "conn", None)
    if conn:
        try:
            conn.close()
        except Exception:
            pass
        _pg_tls.conn = None


_tls = threading.local()


def _configure_connection(conn):
    cache_kb = int(getattr(settings, "sqlite_cache_size_kb", 64000))
    if cache_kb > 0:
        cache_kb = -cache_kb
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute(f"PRAGMA cache_size={cache_kb}")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute(
        f"PRAGMA mmap_size={int(getattr(settings,'sqlite_mmap_size',268435456))}"
    )
    conn.execute(
        f"PRAGMA busy_timeout={int(getattr(settings,'sqlite_busy_timeout_ms',5000))}"
    )
    conn.execute("PRAGMA foreign_keys=ON")


def _get_thread_conn():
    conn = getattr(_tls, "conn", None)
    if conn is None:
        conn = sqlite3.connect(settings.db_path, check_same_thread=False, timeout=10.0)
        _configure_connection(conn)
        _tls.conn = conn
    return conn


@contextmanager
def get_conn():
    if is_postgres():
        conn = _get_pg_conn()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    else:
        conn = _get_thread_conn()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def reset_thread_connection():
    if is_postgres():
        _reset_pg()
    else:
        conn = getattr(_tls, "conn", None)
        if conn:
            try:
                conn.close()
            except Exception:
                pass
            _tls.conn = None
