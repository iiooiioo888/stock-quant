"""
數據庫路由 — SQLite 單庫向後相容；預留讀寫分離擴展點。
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Literal

from src.core.database.connection import get_conn

Operation = Literal["read", "write"]


class DatabaseRouter:
    """當前僅主庫；未來可掛載 read_replica_path。"""

    def __init__(self, read_replica_path: str | None = None):
        self._read_replica = read_replica_path

    @contextmanager
    def connection(self, operation: Operation = "read"):
        # SQLite 單文件：讀寫共用連接池
        with get_conn() as conn:
            yield conn


_default_router: DatabaseRouter | None = None


def get_db_router() -> DatabaseRouter:
    global _default_router
    if _default_router is None:
        from src.config import settings
        replica = getattr(settings, "db_read_replica_path", None) or None
        _default_router = DatabaseRouter(read_replica_path=replica)
    return _default_router
