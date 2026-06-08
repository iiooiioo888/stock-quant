"""PostgreSQL 連接配置 — P6 多實例數據共享。

支持雙後端：SQLite（開發）+ PostgreSQL（生產）。
通過 SQ_DATABASE_URL 環境變量切換。
"""

from __future__ import annotations

import os

from src.config import settings


def get_database_url() -> str:
    url = getattr(settings, "database_url", "") or os.environ.get("SQ_DATABASE_URL", "")
    if url:
        return url
    return f"sqlite:///{settings.db_path}"


def is_postgres() -> bool:
    return get_database_url().startswith("postgresql")


def get_engine_args() -> dict:
    url = get_database_url()
    if url.startswith("sqlite"):
        return {"connect_args": {"check_same_thread": False}, "pool_pre_ping": True}
    return {
        "pool_size": int(os.environ.get("SQ_PG_POOL_SIZE", "10")),
        "max_overflow": int(os.environ.get("SQ_PG_MAX_OVERFLOW", "20")),
        "pool_pre_ping": True,
        "pool_recycle": int(os.environ.get("SQ_PG_POOL_RECYCLE", "3600")),
    }
