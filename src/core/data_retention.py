"""
歷史數據保留策略 — 依 SQ_DATA_RETENTION_YEARS 清理過期列。

years=0 表示關閉（預設，避免演示庫被誤刪）。
"""

from __future__ import annotations

from datetime import date, timedelta

from src.config import settings
from src.utils.logger import logger

# (table, date_column) — 僅清理帶日期欄的大表 / 日誌
_PURGE_TARGETS: list[tuple[str, str]] = [
    ("daily_kline", "date"),
    ("minute_kline", "datetime"),
    ("alert_log", "triggered_at"),
    ("signal_log", "triggered_at"),
    ("capital_flow", "date"),
    ("dragon_tiger", "date"),
    ("notification_history", "created_at"),
    ("task_log", "created_at"),
]


def retention_cutoff_iso(years: int | None = None) -> str | None:
    """返回截止日期 YYYY-MM-DD；未啟用時為 None。"""
    n = settings.data_retention_years if years is None else int(years)
    if n <= 0:
        return None
    cutoff = date.today() - timedelta(days=int(n * 365))
    return cutoff.isoformat()


def purge_old_data(
    years: int | None = None,
    *,
    dry_run: bool = False,
) -> dict:
    """
    刪除早於保留年限的列。

    Returns:
        {enabled, cutoff, dry_run, deleted: {table: n}, total_deleted}
    """
    cutoff = retention_cutoff_iso(years)
    if not cutoff:
        return {
            "enabled": False,
            "cutoff": None,
            "dry_run": dry_run,
            "deleted": {},
            "total_deleted": 0,
            "reason": "SQ_DATA_RETENTION_YEARS=0（未啟用）",
        }

    from src.core.db import get_conn

    deleted: dict[str, int] = {}
    with get_conn() as conn:
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        for table, col in _PURGE_TARGETS:
            if table not in tables:
                continue
            try:
                count_row = conn.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE {col} < ?",
                    (cutoff,),
                ).fetchone()
                n = int(count_row[0] if count_row else 0)
                if n and not dry_run:
                    conn.execute(f"DELETE FROM {table} WHERE {col} < ?", (cutoff,))
                deleted[table] = n if not dry_run else n
            except Exception as e:
                logger.warning(f"保留策略清理 {table} 失敗: {e}")
                deleted[table] = 0
        if not dry_run:
            try:
                conn.execute("VACUUM")
            except Exception as e:
                logger.debug(f"VACUUM 跳過: {e}")

    total = sum(deleted.values())
    logger.info(
        f"數據保留清理{'（dry-run）' if dry_run else ''}: cutoff={cutoff} 刪除 {total} 列"
    )
    return {
        "enabled": True,
        "cutoff": cutoff,
        "dry_run": dry_run,
        "deleted": deleted,
        "total_deleted": total,
    }
