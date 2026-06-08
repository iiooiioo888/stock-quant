"""策略庫點讚 — 用戶點讚與全站計數。"""

from __future__ import annotations

import re
from datetime import datetime

from src.utils.logger import logger

_KEY_RE = re.compile(r"^[a-zA-Z0-9_.-]{1,64}$")


def normalize_strategy_key(key: str) -> str:
    k = (key or "").strip()
    if not k or not _KEY_RE.match(k):
        raise ValueError("無效的策略識別碼")
    return k


def get_like_counts() -> dict[str, int]:
    try:
        from src.core.db import get_conn

        with get_conn() as conn:
            if not _table_exists(conn):
                return {}
            rows = conn.execute("""SELECT strategy_key, COUNT(*) AS cnt
                   FROM strategy_likes
                   GROUP BY strategy_key""").fetchall()
        return {str(r[0]): int(r[1]) for r in rows}
    except Exception as e:
        logger.debug(f"讀取策略點讚計數跳過: {e}")
        return {}


def get_user_liked_keys(user_id: int) -> list[str]:
    try:
        from src.core.db import get_conn

        with get_conn() as conn:
            if not _table_exists(conn):
                return []
            rows = conn.execute(
                "SELECT strategy_key FROM strategy_likes WHERE user_id = ? ORDER BY created_at DESC",
                (user_id,),
            ).fetchall()
        return [str(r[0]) for r in rows]
    except Exception as e:
        logger.debug(f"讀取用戶策略點讚跳過: {e}")
        return []


def toggle_like(user_id: int, strategy_key: str) -> dict:
    key = normalize_strategy_key(strategy_key)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    liked = False
    try:
        from src.core.db import get_conn

        with get_conn() as conn:
            if not _table_exists(conn):
                raise RuntimeError("strategy_likes 表尚未建立")
            existing = conn.execute(
                "SELECT 1 FROM strategy_likes WHERE user_id = ? AND strategy_key = ?",
                (user_id, key),
            ).fetchone()
            if existing:
                conn.execute(
                    "DELETE FROM strategy_likes WHERE user_id = ? AND strategy_key = ?",
                    (user_id, key),
                )
                liked = False
            else:
                conn.execute(
                    "INSERT INTO strategy_likes (user_id, strategy_key, created_at) VALUES (?, ?, ?)",
                    (user_id, key, now),
                )
                liked = True
            row = conn.execute(
                "SELECT COUNT(*) FROM strategy_likes WHERE strategy_key = ?",
                (key,),
            ).fetchone()
        count = int(row[0]) if row else 0
        return {"key": key, "liked": liked, "count": count}
    except ValueError:
        raise
    except Exception as e:
        logger.error(f"策略點讚切換失敗 {user_id}/{key}: {e}")
        raise


def _table_exists(conn) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='strategy_likes'"
    ).fetchone()
    return row is not None
