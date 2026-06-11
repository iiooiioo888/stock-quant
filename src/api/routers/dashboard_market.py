"""儀表盤 — 板塊與資金流向圖表 API"""

from fastapi import APIRouter, Query

from src.utils.logger import logger

router = APIRouter(tags=["dashboard"])


@router.get("/api/data/sectors/capital-flow")
async def sectors_capital_flow_rank(top_n: int = Query(20, ge=5, le=50)):
    """板塊主力淨流入排名（今日）"""
    from src.core.sector import get_sector_capital_flow_rank

    from src.core.sector import sector_flow_is_degraded

    try:
        sectors = get_sector_capital_flow_rank(top_n)
        degraded = sector_flow_is_degraded(sectors)
        return {
            "sectors": sectors,
            "total": len(sectors),
            "degraded": degraded,
            "degraded_message": (
                "資料降級：僅板塊漲跌，無主力淨額" if degraded else None
            ),
        }
    except Exception as e:
        logger.error(f"板塊資金排名失敗: {e}", exc_info=True)
        return {"sectors": [], "total": 0, "error": str(e)}


@router.get("/api/data/sectors/change-flow")
async def sectors_change_flow(
    sector_type: str = Query("industry"),
    top_n: int = Query(40, ge=10, le=80),
):
    """板塊漲跌幅 × 資金流向矩陣（散點圖）"""
    from src.core.sector import get_sector_change_flow_matrix

    try:
        items = get_sector_change_flow_matrix(sector_type=sector_type, top_n=top_n)
        return {"sectors": items, "total": len(items), "type": sector_type}
    except Exception as e:
        logger.error(f"板塊漲跌資金矩陣失敗: {e}", exc_info=True)
        return {"sectors": [], "total": 0, "error": str(e)}


@router.get("/api/dashboard/market-charts")
async def dashboard_market_charts(days: int = Query(20, ge=5, le=60)):
    """
    儀表盤資金與板塊圖表數據（單次請求，帶緩存）。
    含：板塊資金排名、漲跌×資金、熱力圖、概念板塊、大盤/北向資金。
    """
    from src.core.api_cache import cached_response

    def _build():
        from src.core.capital_flow import get_market_capital_flow, get_north_flow
        from src.core.sector import (
            get_sector_capital_flow_rank,
            get_sector_change_flow_matrix,
            get_sector_heatmap_data,
            get_sector_performance,
        )

        sector_flow = get_sector_capital_flow_rank(15)
        sector_scatter = get_sector_change_flow_matrix("industry", 45)
        sector_heatmap = get_sector_heatmap_data("industry")[:50]
        concept_sectors = get_sector_performance(sector_type="concept", top_n=12)

        market_flow = get_market_capital_flow() or []
        if len(market_flow) > days:
            market_flow = market_flow[-days:]

        north_flow = get_north_flow(days=days) or []

        def _pick_source(items: list) -> str:
            if not items:
                return ""
            src = items[0].get("source") or ""
            if all((i.get("source") or "") == src for i in items[:5]):
                return src
            return "mixed"

        from src.core.sector import sector_flow_is_degraded

        flow_degraded = sector_flow_is_degraded(sector_flow)
        return {
            "sector_flow": sector_flow,
            "sector_flow_degraded": flow_degraded,
            "sector_flow_degraded_message": (
                "資料降級：僅板塊漲跌，無主力淨額" if flow_degraded else None
            ),
            "sector_scatter": sector_scatter,
            "sector_heatmap": sector_heatmap,
            "concept_sectors": concept_sectors,
            "market_flow": market_flow,
            "north_flow": north_flow,
            "days": days,
            "sources": {
                "sector_flow": _pick_source(sector_flow),
                "sector_scatter": _pick_source(sector_scatter),
                "sector_heatmap": _pick_source(sector_heatmap),
                "concept_sectors": _pick_source(concept_sectors),
                "market_flow": _pick_source(market_flow),
                "north_flow": _pick_source(north_flow),
            },
        }

    return cached_response(f"api:dashboard:market:{days}", ttl=90, builder=_build)
