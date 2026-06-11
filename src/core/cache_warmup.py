"""
啟動/腳本用緩存預熱 — 將常用標的 K 線載入進程 LRU 與 L2 緩存。
"""

from __future__ import annotations

import asyncio

from src.config import settings
from src.utils.logger import logger


def warmup_cache_sync(codes: list[str] | None = None) -> dict:
    """同步預熱（腳本或啟動後台線程調用）。"""
    from src.core.cache import get_cache, set_cached_kline
    from src.core.db import load_daily_kline, preload_kline_range

    targets = codes or list(settings.cache_warmup_codes or [])
    if not settings.cache_enabled:
        return {"warmed": 0, "skipped": True, "reason": "cache_disabled"}

    warmed = 0
    rows_total = 0
    for raw in targets:
        code = str(raw).strip()
        if not code:
            continue
        try:
            n = preload_kline_range(code)
            rows_total += n
            if n > 0:
                df = load_daily_kline(code)
                if not df.empty:
                    set_cached_kline(code, df.to_dict(orient="records"))
            warmed += 1
        except Exception as e:
            logger.debug(f"預熱跳過 {code}: {e}")

    indicator_warmed = 0
    if getattr(settings, "cache_warmup_indicators", True):
        from src.core.indicator_cache import warm_indicators_for_code

        for raw in targets:
            code = str(raw).strip()
            if code:
                warm_indicators_for_code(code)
                indicator_warmed += 1

    get_cache().stats()
    logger.info(
        f"緩存預熱完成: {warmed}/{len(targets)} 標的, K 線 {rows_total} 條, 指標 {indicator_warmed}"
    )
    return {
        "warmed": warmed,
        "codes": len(targets),
        "kline_rows": rows_total,
        "indicators": indicator_warmed,
    }


async def warmup_cache_async(codes: list[str] | None = None) -> dict:
    """非阻塞預熱（lifespan 背景任務）。"""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, warmup_cache_sync, codes)
