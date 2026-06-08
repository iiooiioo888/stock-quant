"""
邀請碼管理 — 生成、驗證、使用追蹤。
"""

from __future__ import annotations

import secrets
import sqlite3
from datetime import datetime
from typing import Optional

from src.core.db import get_conn
from src.utils.logger import logger


def _ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS invite_codes (
            code TEXT PRIMARY KEY,
            created_by INTEGER NOT NULL,
            max_uses INTEGER DEFAULT 1,
            uses INTEGER DEFAULT 0,
            expires_at TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()


def generate_code(
    created_by: int, max_uses: int = 1, expires_at: Optional[str] = None
) -> str:
    """生成邀請碼，返回 code 字符串。"""
    code = secrets.token_urlsafe(8).upper()  # ~11 chars
    with get_conn() as conn:
        _ensure_table(conn)
        conn.execute(
            "INSERT INTO invite_codes (code, created_by, max_uses, uses, expires_at) VALUES (?, ?, ?, 0, ?)",
            (code, created_by, max_uses, expires_at),
        )
    logger.info(f"邀請碼已生成: {code} (max_uses={max_uses})")
    return code


def validate_code(code: str) -> tuple[bool, str]:
    """
    驗證邀請碼是否可用。
    返回 (valid, reason)。
    """
    code = (code or "").strip().upper()
    if not code:
        return False, "邀請碼不能為空"

    with get_conn() as conn:
        _ensure_table(conn)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM invite_codes WHERE code = ?", (code,)
        ).fetchone()

    if not row:
        return False, "邀請碼不存在"

    if row["uses"] >= row["max_uses"]:
        return False, "邀請碼已用完"

    if row["expires_at"]:
        try:
            exp = datetime.fromisoformat(row["expires_at"])
            if exp < datetime.now():
                return False, "邀請碼已過期"
        except ValueError:
            pass

    return True, ""


def use_code(code: str) -> bool:
    """標記邀請碼已使用一次。返回是否成功。"""
    code = (code or "").strip().upper()
    if not code:
        return False

    with get_conn() as conn:
        _ensure_table(conn)
        cursor = conn.execute(
            "UPDATE invite_codes SET uses = uses + 1 WHERE code = ? AND uses < max_uses",
            (code,),
        )
        return cursor.rowcount > 0


def list_codes(created_by: Optional[int] = None) -> list[dict]:
    """列出邀請碼（管理員可看全部，或按創建者篩選）。"""
    with get_conn() as conn:
        _ensure_table(conn)
        conn.row_factory = sqlite3.Row
        if created_by is not None:
            rows = conn.execute(
                "SELECT * FROM invite_codes WHERE created_by = ? ORDER BY created_at DESC",
                (created_by,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM invite_codes ORDER BY created_at DESC"
            ).fetchall()

    return [dict(row) for row in rows]


def delete_code(code: str) -> bool:
    """刪除邀請碼。"""
    code = (code or "").strip().upper()
    if not code:
        return False

    with get_conn() as conn:
        _ensure_table(conn)
        cursor = conn.execute("DELETE FROM invite_codes WHERE code = ?", (code,))
        return cursor.rowcount > 0
