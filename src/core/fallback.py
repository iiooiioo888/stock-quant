"""
數據源自動降級 — 本地庫 → 自動選源拉取 → 過期緩存兜底。
"""

from __future__ import annotations

from typing import Optional, Tuple

import pandas as pd

from src.config import settings
from src.utils.logger import logger


class FallbackManager:
    """K 線拉取降級鏈（與 ensure_daily_kline 共用同一套自動選源，避免重複遞迴）。"""

    async def get_daily_kline_with_fallback(
        self,
        code: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        min_bars: int = 2,
    ) -> Tuple[pd.DataFrame, str]:
        from src.core.db import load_daily_kline
        from src.core.local_kline import ensure_daily_kline, normalize_kline_code

        code = normalize_kline_code(code)
        df, src = ensure_daily_kline(
            code,
            start_date=start_date,
            end_date=end_date,
            min_bars=min_bars,
            auto_fetch=settings.local_first_auto_fetch,
        )
        if len(df) >= min_bars:
            return df, src

        if not df.empty:
            return df, src or "partial"

        try:
            from src.core.cache import get_cached_kline

            cached = get_cached_kline(code)
            if cached:
                logger.warning(f"使用過期緩存兜底: {code}")
                return pd.DataFrame(cached), "stale_cache"
        except Exception as e:
            logger.debug(f"過期緩存兜底跳過 {code}: {e}")

        return (
            load_daily_kline(code, start_date=start_date, end_date=end_date),
            src or "empty",
        )


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
        asyncio.get_running_loop()
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
