"""全球資產庫 API — 目錄 + 詳情"""
from urllib.parse import unquote

from fastapi import APIRouter, HTTPException, Query

from src.core.market_catalog import (
    GROUP_LABELS,
    GROUP_ORDER,
    MARKET_INSTRUMENTS,
    catalog_summary,
)
from src.utils.logger import logger

router = APIRouter(tags=["assets"])


@router.get("/api/assets/catalog")
async def get_assets_catalog():
    """資產庫目錄（12 分組元數據）。"""
    from src.core.api_cache import cached_response

    def _build():
        return {
            **catalog_summary(),
            "instruments": [
                {
                    "symbol": i.symbol,
                    "name": i.name,
                    "group": i.group,
                    "group_label": GROUP_LABELS.get(i.group, i.group),
                    "asset_class": i.asset_class,
                    "tv": i.tv,
                    "topbar": i.topbar,
                }
                for i in MARKET_INSTRUMENTS
            ],
        }

    return cached_response("api:assets:catalog", ttl=300, builder=_build)


@router.get("/api/assets/detail")
async def get_asset_detail(
    symbol: str = Query(..., min_length=1, max_length=32),
    days: int = Query(180, ge=30, le=500),
):
    """單資產詳情：K 線、財報、新聞、Polymarket（A股）。"""
    from src.core.api_cache import cached_response
    from src.core.asset_detail import build_asset_detail

    sym = unquote(symbol).strip()
    if not sym:
        raise HTTPException(400, "symbol required")

    cache_key = f"api:assets:detail:{sym}:{days}"

    def _build():
        detail = build_asset_detail(sym, days)
        if not detail:
            raise HTTPException(404, f"無法載入標的 {sym}")
        return {"success": True, "detail": detail}

    try:
        return cached_response(cache_key, ttl=60, builder=_build)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"資產詳情 {sym} 失敗: {e}")
        raise HTTPException(500, str(e)) from e
