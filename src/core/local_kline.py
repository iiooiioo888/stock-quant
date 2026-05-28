"""
本地 K 線優先策略 — 僅在本地無數據時爬取一次並寫入 SQLite，之後一律讀庫。

業務規則：
  - 本地已有足夠 K 線 → 直接返回，不再請求外網
  - 本地為空或不足 → 調用 download_one 拉取並 save_daily_kline，再從庫讀取
  - 增量更新請用 history.download_incremental 或定時任務，不在此模塊自動全量重拉
"""
from __future__ import annotations

import pandas as pd

from src.config import settings
from src.core.db import load_daily_kline
from src.utils.logger import logger


def normalize_kline_code(code: str) -> str:
    """A 股 6 位補零，其餘原樣（如 ^GSPC、BTCUSDT）"""
    code = str(code).strip()
    if code.isdigit() and len(code) < 6:
        return code.zfill(6)
    return code


def has_local_kline(code: str, min_bars: int = 2) -> bool:
    code = normalize_kline_code(code)
    df = load_daily_kline(code)
    return len(df) >= min_bars


def ensure_daily_kline(
    code: str,
    start_date: str | None = None,
    end_date: str | None = None,
    market: str | None = None,
    min_bars: int = 2,
    auto_fetch: bool | None = None,
) -> tuple[pd.DataFrame, str]:
    """
    讀取日 K（本地優先）。

    Returns:
        (DataFrame, source) — source 為 local_db | fetched | partial | empty
    """
    code = normalize_kline_code(code)
    if auto_fetch is None:
        auto_fetch = settings.local_first_auto_fetch

    df = load_daily_kline(code, start_date=start_date, end_date=end_date)
    if len(df) >= min_bars:
        return df, "local_db"

    if not auto_fetch:
        return df, "empty" if df.empty else "partial"

    from src.core.history import detect_market, download_one

    mkt = market or detect_market(code)
    start = start_date or settings.history_start_date
    logger.info(f"本地無 {code} 日 K（{len(df)} 條），首次從外網拉取並寫入庫…")
    count = download_one(code, start_date=start, market=mkt)
    if count > 0:
        from src.core.db import clear_data_cache
        clear_data_cache(quiet=True, reason=f"ensure_daily_kline:{code}")

    df = load_daily_kline(code, start_date=start_date, end_date=end_date)
    if len(df) >= min_bars:
        return df, "fetched"
    if not df.empty:
        return df, "partial"

    try:
        from src.core.fallback import get_daily_kline_with_fallback

        fdf, fsrc = get_daily_kline_with_fallback(
            code, start_date=start_date, end_date=end_date, min_bars=min_bars,
        )
        if len(fdf) >= min_bars:
            return fdf, fsrc
        if not fdf.empty:
            return fdf, fsrc
    except Exception as e:
        logger.debug(f"K 線降級鏈跳過 {code}: {e}")

    return df, "empty"


def persist_kline_df(symbol: str, df: pd.DataFrame) -> int:
    """將已拉取的 DataFrame 寫入本地庫（供多源行情模塊使用）"""
    if df is None or df.empty:
        return 0
    from src.core.history import detect_market
    from src.core.db import save_daily_kline

    code = normalize_kline_code(symbol)
    if "date" not in df.columns:
        return 0
    out = df.copy()
    out["date"] = out["date"].astype(str).str[:10]
    market = detect_market(code)
    n = save_daily_kline(out, code, market=market)
    if n > 0:
        try:
            from src.core.pipeline_observability import record_kline_persist

            record_kline_persist(n)
        except Exception:
            pass
        from src.core.data_pipeline import defer_data_cache_clear
        defer_data_cache_clear()
    return n
