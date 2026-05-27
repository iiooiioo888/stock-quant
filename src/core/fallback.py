"""
數據源自動降級 — Yahoo / AKShare / 本地緩存。
"""
from __future__ import annotations

from typing import Optional, Tuple

import pandas as pd

from src.utils.logger import logger


class FallbackManager:
    """K 線拉取降級鏈（本地庫 → 主源 → 備選源）。"""

    async def get_daily_kline_with_fallback(
        self,
        code: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        min_bars: int = 2,
    ) -> Tuple[pd.DataFrame, str]:
        from src.core.local_kline import ensure_daily_kline
        df, src = ensure_daily_kline(code, start_date=start_date, end_date=end_date, min_bars=min_bars)
        if len(df) >= min_bars:
            return df, src

        try:
            from src.core.yahoo_finance import download_a_share_daily
            ydf = download_a_share_daily(code, start_date=start_date)
            if ydf is not None and not ydf.empty:
                from src.core.local_kline import persist_kline_df
                persist_kline_df(code, ydf)
                logger.warning(f"主源失敗後 Yahoo 降級成功: {code}")
                return ydf, "yahoo_fallback"
        except Exception as e:
            logger.debug(f"Yahoo 降級失敗 {code}: {e}")

        try:
            from src.core.history import download_one
            n = download_one(code, start_date=start_date)
            if n > 0:
                from src.core.db import load_daily_kline, clear_data_cache
                clear_data_cache(quiet=True, reason=f"fallback:{code}")
                df = load_daily_kline(code, start_date=start_date, end_date=end_date)
                return df, "akshare_fallback"
        except Exception as e:
            logger.debug(f"AKShare 降級失敗 {code}: {e}")

        from src.core.cache import get_cached_kline
        cached = get_cached_kline(code)
        if cached:
            logger.warning(f"使用過期緩存兜底: {code}")
            return pd.DataFrame(cached), "stale_cache"

        return df, src or "empty"


_manager: Optional[FallbackManager] = None


def get_fallback_manager() -> FallbackManager:
    global _manager
    if _manager is None:
        _manager = FallbackManager()
    return _manager


def get_daily_kline_with_fallback(
    code: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    min_bars: int = 2,
) -> Tuple[pd.DataFrame, str]:
    """同步入口（供非 async 模塊調用）。"""
    import asyncio
    mgr = get_fallback_manager()
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(
            mgr.get_daily_kline_with_fallback(code, start_date, end_date, min_bars)
        )
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(
            asyncio.run,
            mgr.get_daily_kline_with_fallback(code, start_date, end_date, min_bars),
        ).result()
