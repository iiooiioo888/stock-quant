"""
Stock Quant 資料庫層 — 連線、Schema、遷移

對外 API（建議新代碼使用）:
  from src.core.database import get_conn, init_database, run_migrations
"""
from src.core.database.bootstrap import init_database
from src.core.database.connection import get_conn, reset_thread_connection
from src.core.database.migrations import (
    CURRENT_SCHEMA_VERSION,
    get_schema_version,
    run_migrations,
)
from src.core.database.seed import seed_common_data, seed_universe_catalog

__all__ = [
    "get_conn",
    "reset_thread_connection",
    "init_database",
    "run_migrations",
    "get_schema_version",
    "CURRENT_SCHEMA_VERSION",
    "seed_common_data",
    "seed_universe_catalog",
]
