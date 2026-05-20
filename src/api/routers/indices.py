"""全球主要指數 K 線 API（儀表盤首頁）"""
from concurrent.futures import ThreadPoolExecutor, as_completed

from fastapi import APIRouter, Query

from src.core.market_fetch import build_index_chart_item
from src.utils.logger import logger

router = APIRouter(tags=["indices"])

# 首頁展示的核心指數（symbol, 中文名）
HOME_INDICES = [
    ("000001.SS", "上證綜指"),
    ("399001.SZ", "深證成指"),
    ("399006.SZ", "創業板指"),
    ("^HSI", "恒生指數"),
    ("^GSPC", "標普 500"),
    ("^IXIC", "納斯達克"),
    ("^DJI", "道瓊斯"),
    ("^N225", "日經 225"),
]


@router.get("/api/indices/charts")
async def get_indices_charts(days: int = Query(90, ge=30, le=365)):
    """
    獲取首頁全球主要指數 K 線。
    多源降級：本地庫 → Yahoo → 東財 → Twelve Data。
    """
    from src.core.api_cache import cached_response

    def _build():
        indices = []
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {
                pool.submit(build_index_chart_item, sym, name, days): sym
                for sym, name in HOME_INDICES
            }
            for fut in as_completed(futures):
                sym = futures[fut]
                try:
                    item = fut.result()
                    if item:
                        indices.append(item)
                except Exception as e:
                    logger.debug(f"指數 {sym} 載入失敗: {e}")

        order = {sym: i for i, (sym, _) in enumerate(HOME_INDICES)}
        indices.sort(key=lambda x: order.get(x["symbol"], 999))
        sources_used = sorted({i.get("source", "") for i in indices if i.get("source")})
        return {
            "indices": indices,
            "days": days,
            "count": len(indices),
            "sources": sources_used,
        }

    return cached_response(f"api:indices:charts:{days}", ttl=120, builder=_build)
