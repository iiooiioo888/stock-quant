"""
統一數據爬取管線 — 快取節流、財報解析、批量寫入收尾。

原則：
  - 外網請求走各模塊降級鏈（market_fetch / fundamental / history）
  - 寫入 SQLite 後不逐條清空全站 LRU，改為 defer + 批量 flush
  - 財報：DB 命中且未過期 → 直接返回；否則 akshare 拉取並回寫 fundamentals 表
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

# 批量 K 線寫入時累計，由 indices 等批量任務結束後 flush
_deferred_cache_clears: int = 0


def get_deferred_cache_clear_count() -> int:
    """當前待 flush 的快取清理批次数（觀測用）。"""
    return _deferred_cache_clears


def defer_data_cache_clear() -> None:
    """標記需要刷新進程內 K 線 LRU（不立即執行）。"""
    global _deferred_cache_clears
    _deferred_cache_clears += 1
    try:
        from src.core.pipeline_observability import record_cache_defer

        record_cache_defer()
    except Exception:
        pass


def flush_deferred_data_cache_clear() -> bool:
    """若存在延遲標記則清空一次快取。返回是否執行了清除。"""
    global _deferred_cache_clears
    if _deferred_cache_clears <= 0:
        return False
    n = _deferred_cache_clears
    _deferred_cache_clears = 0
    from src.core.db import clear_data_cache

    clear_data_cache(quiet=True, reason=f"batch_kline_persist×{n}")
    try:
        from src.core.pipeline_observability import record_cache_flush

        record_cache_flush(n)
    except Exception:
        pass
    return True


def parse_ymd(value: Any) -> Optional[date]:
    if value is None:
        return None
    s = str(value).strip()[:10]
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def is_stale(update_date: Any, max_age_days: int = 7) -> bool:
    """無日期或早於 max_age_days 視為過期。"""
    if max_age_days <= 0:
        return False
    d = parse_ymd(update_date)
    if d is None:
        return True
    return (date.today() - d).days > max_age_days


def resolve_financials(
    code: str,
    *,
    allow_fetch: bool = True,
    max_age_days: int = 7,
) -> dict:
    """
    解析 A 股財報（供詳情頁 / analysis-page）。
    合併 fundamental 表與 stock_basics 展示格式。
    """
    from src.core.fundamental import fundamentals_row_to_fin, get_fundamentals
    from src.core.stock_basics import load_stock_financials

    code = str(code).strip()
    if code.isdigit() and len(code) < 6:
        code = code.zfill(6)

    row: dict = {}
    if allow_fetch:
        row = get_fundamentals(code, max_age_days=max_age_days) or {}
    else:
        from src.core.fundamental import load_fundamentals_db

        row = load_fundamentals_db(code) or {}

    if row:
        fin = fundamentals_row_to_fin(row)
        if fin.get("has_data"):
            if not allow_fetch:
                _record_resolve("db_only")
            else:
                src = str(row.get("source") or "")
                if "stale" in src:
                    _record_resolve("stale_fallback")
                elif src == "fundamentals_db":
                    _record_resolve("db_fresh")
                else:
                    _record_resolve("fetched")
            return fin

    # DB / 在線仍不足時，用 universe + snapshot 兜底（不發外網）
    fallback = load_stock_financials(code, allow_fetch=False) or {}
    _record_resolve("universe_fallback" if fallback.get("has_data") else "empty")
    return fallback


def _record_resolve(path: str) -> None:
    try:
        from src.core.pipeline_observability import record_financials_resolve

        record_financials_resolve(path)
    except Exception:
        pass
