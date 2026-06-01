"""
資料庫啟動流程 — 建目錄、跑遷移、初始化管理員
"""
from __future__ import annotations

import os

from src.config import settings
from src.core.database.migrations import CURRENT_SCHEMA_VERSION, get_schema_version, run_migrations
from src.utils.logger import logger


def init_database() -> None:
    """完整初始化：目錄 + 遷移 + 預設管理員。"""
    db_path = settings.db_path
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)

    run_migrations()

    try:
        from src.core.database.index_audit import ensure_missing_indexes

        idx_report = ensure_missing_indexes()
        applied = idx_report.get("applied") or []
        if applied:
            logger.info(f"已補建缺失索引 {len(applied)} 個: {applied[:5]}{'…' if len(applied) > 5 else ''}")
    except Exception as e:
        logger.debug(f"索引健檢跳過: {e}")

    try:
        from src.core.auth import ensure_default_admin
        ensure_default_admin()
    except Exception as e:
        logger.warning(f"默認管理員初始化跳過: {e}")

    ver = get_schema_version()
    logger.info(
        f"資料庫就緒: {db_path} (schema v{ver}/{CURRENT_SCHEMA_VERSION})"
    )
