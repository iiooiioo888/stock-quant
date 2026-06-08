"""
SQLite 索引健檢 — 對照 schema.INDEX_DDL，發現缺失並可選修復。
"""

from __future__ import annotations

import re
import sqlite3
from typing import Any

from src.core.database.connection import get_conn, is_postgres
from src.core.database.schema import INDEX_DDL
from src.utils.logger import logger

_INDEX_NAME_RE = re.compile(
    r"CREATE\s+INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)",
    re.IGNORECASE,
)


def index_name_from_ddl(ddl: str) -> str | None:
    m = _INDEX_NAME_RE.search(ddl.strip())
    return m.group(1) if m else None


def expected_index_names() -> set[str]:
    names = {index_name_from_ddl(ddl) for ddl in INDEX_DDL}
    return {n for n in names if n}


def _list_existing_indexes(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("""
        SELECT name FROM sqlite_master
        WHERE type = 'index' AND name NOT LIKE 'sqlite_%'
        """).fetchall()
    return {r[0] for r in rows}


def audit_indexes(conn: sqlite3.Connection | None = None) -> dict[str, Any]:
    """
    比對預期索引與庫內實際索引。

    Returns:
        ok, expected_count, present_count, missing, extra_untracked
    """
    expected = expected_index_names()

    def _run(c: sqlite3.Connection) -> dict[str, Any]:
        existing = _list_existing_indexes(c)
        present = expected & existing
        missing = sorted(expected - existing)
        extra = sorted(n for n in (existing - expected) if n.startswith("idx_"))
        return {
            "ok": len(missing) == 0,
            "expected_count": len(expected),
            "present_count": len(present),
            "missing": missing,
            "extra_untracked": extra[:30],
            "extra_untracked_total": len(extra),
        }

    if conn is not None:
        return _run(conn)

    with get_conn() as c:
        return _run(c)


def ensure_missing_indexes(conn: sqlite3.Connection | None = None) -> dict[str, Any]:
    """建立 INDEX_DDL 中尚未存在的索引。返回 applied 列表。"""
    applied: list[str] = []

    def _run(c: sqlite3.Connection) -> dict[str, Any]:
        nonlocal applied
        report = audit_indexes(c)
        missing_set = set(report["missing"])
        for ddl in INDEX_DDL:
            name = index_name_from_ddl(ddl)
            if not name or name not in missing_set:
                continue
            try:
                c.execute(ddl)
                applied.append(name)
                logger.info(f"索引已建立: {name}")
            except sqlite3.OperationalError as e:
                logger.warning(f"索引建立失敗 {name}: {e}")
        after = audit_indexes(c)
        return {
            "applied": applied,
            "applied_count": len(applied),
            "audit_before": report,
            "audit_after": after,
        }

    if conn is not None:
        return _run(conn)

    with get_conn() as c:
        return _run(c)
