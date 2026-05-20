"""數據中心"""
import json
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends, Query, UploadFile, File, Request
from src.config import settings
from src.core.auth import require_auth, require_admin
from src.core.db import get_conn
from src.utils.logger import logger
from src.api.constants import STOCK_NAMES
from src.api.dispatch import dispatch_async_task

router = APIRouter()

@router.get("/api/data/minutes")
async def get_minutes_data(code: str, period: str = "5m"):
    """獲取分鐘 K 線數據"""
    from src.core.db import load_minute_kline
    
    # 先從數據庫讀取
    df = load_minute_kline(code, period)
    
    if df.empty:
        # 數據庫無數據，嘗試下載
        try:
            from src.core.history import download_minute_data
            download_minute_data(code, period)
            df = load_minute_kline(code, period)
        except Exception as e:
            logger.error(f"分鐘K線下載失敗: {e}")
            raise HTTPException(500, f"分鐘K線數據獲取失敗: {e}")
    
    if df.empty:
        raise HTTPException(404, f"{code} {period} 無分鐘K線數據")
    
    records = df.to_dict(orient="records")
    return {"code": code, "period": period, "data": records, "count": len(records)}


@router.post("/api/data/minutes/download")
async def download_minutes_api(code: str, period: str = "5m"):
    """下載分鐘 K 線數據"""
    from src.core.history import download_minute_data
    
    try:
        count = download_minute_data(code, period)
        return {"success": True, "code": code, "period": period, "records": count}
    except Exception as e:
        logger.error(f"分鐘K線下載失敗: {e}")
        raise HTTPException(500, str(e))


@router.get("/api/data/sectors")
async def get_sectors(sector_type: str = "industry", top_n: int = 30):
    """獲取板塊列表（行業/概念）"""
    from src.core.sector import get_sector_list, get_sector_performance
    
    try:
        sectors = get_sector_performance(sector_type=sector_type, top_n=top_n)
        from_snapshot = bool(sectors and sectors[0].get("from_snapshot"))
        snapshot_date = sectors[0].get("snapshot_date") if from_snapshot else None
        source = sectors[0].get("source") if sectors else None
        return {
            "success": True,
            "sectors": sectors,
            "total": len(sectors),
            "type": sector_type,
            "from_snapshot": from_snapshot,
            "snapshot_date": snapshot_date,
            "source": source,
            "hint": (
                "實時板塊接口暫不可用且無本地快照；請稍後重試，或收盤後調用 POST /api/data/sectors/snapshot 保存快照"
                if not sectors else None
            ),
        }
    except Exception as e:
        logger.error(f"獲取板塊列表失敗: {e}", exc_info=True)
        raise HTTPException(500, str(e))


@router.get("/api/data/sector/{name}/stocks")
async def get_sector_stocks_api(name: str, sector_type: str = "industry"):
    """獲取板塊成分股"""
    from src.core.sector import get_sector_stocks
    
    try:
        stocks = get_sector_stocks(name, sector_type=sector_type)
        return {"sector": name, "stocks": stocks, "total": len(stocks)}
    except Exception as e:
        logger.error(f"獲取板塊 {name} 成分股失敗: {e}")
        raise HTTPException(500, str(e))


@router.get("/api/data/sectors/rotation")
async def get_sector_rotation_api(days: int = 10):
    """板塊輪動分析 — 排名變化最大的板塊"""
    from src.core.sector import get_sector_rotation
    try:
        rotation = get_sector_rotation(days)
        return {"rotation": rotation, "total": len(rotation), "days": days}
    except Exception as e:
        logger.error(f"板塊輪動分析失敗: {e}")
        raise HTTPException(500, str(e))


@router.get("/api/data/sector/{name}/trend")
async def get_sector_trend_api(name: str, days: int = 20):
    """板塊歷史趨勢 — 近 N 天漲跌走勢"""
    from src.core.sector import get_sector_trend
    try:
        trend = get_sector_trend(name, days)
        return {"sector": name, "trend": trend, "total": len(trend)}
    except Exception as e:
        logger.error(f"獲取板塊 {name} 趨勢失敗: {e}")
        raise HTTPException(500, str(e))


@router.post("/api/data/sectors/snapshot")
async def save_sector_snapshot_api(sector_type: str = "industry"):
    """保存當日板塊快照（收盤後調用）"""
    from src.core.sector import save_sector_snapshot
    try:
        count = save_sector_snapshot(sector_type)
        return {"success": True, "count": count, "sector_type": sector_type}
    except Exception as e:
        logger.error(f"保存板塊快照失敗: {e}")
        raise HTTPException(500, str(e))


@router.get("/api/data/sectors/heatmap")
async def get_sector_heatmap_api(sector_type: str = "industry"):
    """板塊全景數據 — 用於前端熱力圖"""
    from src.core.sector import get_sector_heatmap_data
    try:
        sectors = get_sector_heatmap_data(sector_type)
        return {"sectors": sectors, "total": len(sectors), "type": sector_type}
    except Exception as e:
        logger.error(f"板塊全景數據失敗: {e}")
        raise HTTPException(500, str(e))


@router.get("/api/data/sector/{name}/capital-flow")
async def get_sector_capital_flow_api(name: str):
    """板塊資金流向"""
    from src.core.sector import get_sector_capital_flow
    try:
        flows = get_sector_capital_flow(name)
        return {"sector": name, "flows": flows, "total": len(flows)}
    except Exception as e:
        logger.error(f"獲取板塊 {name} 資金流向失敗: {e}")
        raise HTTPException(500, str(e))


@router.get("/api/data/capital-flow")
async def get_capital_flow_api(code: str, days: int = 30):
    """獲取個股資金流向"""
    from src.core.capital_flow import get_capital_flow
    
    try:
        flows = get_capital_flow(code, days=days)
        return {"code": code, "flows": flows, "total": len(flows)}
    except Exception as e:
        logger.error(f"獲取 {code} 資金流向失敗: {e}")
        raise HTTPException(500, str(e))


@router.get("/api/data/market-flow")
async def get_market_flow_api():
    """獲取大盤資金流向"""
    from src.core.capital_flow import get_market_capital_flow
    
    try:
        flows = get_market_capital_flow()
        return {"flows": flows, "total": len(flows)}
    except Exception as e:
        logger.error(f"獲取大盤資金流向失敗: {e}")
        raise HTTPException(500, str(e))


@router.get("/api/data/north-flow")
async def get_north_flow_api(days: int = 30):
    """獲取北向資金流入"""
    from src.core.capital_flow import get_north_flow
    
    try:
        from src.core.capital_flow import aggregate_north_flow_daily

        flows = get_north_flow(days=days)
        daily = aggregate_north_flow_daily(flows)
        return {"flows": flows, "daily": daily, "total": len(flows), "daily_total": len(daily)}
    except Exception as e:
        logger.error(f"獲取北向資金失敗: {e}")
        raise HTTPException(500, str(e))


@router.get("/api/data/dragon-tiger")
async def get_dragon_tiger_api(date: str = None):
    """獲取龍虎榜數據"""
    from src.core.dragon_tiger import get_dragon_tiger
    
    try:
        records = get_dragon_tiger(date=date)
        return {"date": date or "today", "records": records, "total": len(records)}
    except Exception as e:
        logger.error(f"獲取龍虎榜失敗: {e}")
        raise HTTPException(500, str(e))


@router.get("/api/data/dragon-tiger/{code}/history")
async def get_dragon_tiger_history_api(code: str, days: int = 30):
    """獲取股票龍虎榜歷史"""
    from src.core.dragon_tiger import get_dragon_tiger_history
    
    try:
        records = get_dragon_tiger_history(code, days=days)
        return {"code": code, "records": records, "total": len(records)}
    except Exception as e:
        logger.error(f"獲取 {code} 龍虎榜歷史失敗: {e}")
        raise HTTPException(500, str(e))


@router.get("/api/data/fundamentals")
async def get_fundamentals_api(code: str):
    """獲取股票基本面數據"""
    from src.core.fundamental import get_fundamentals
    
    try:
        data = get_fundamentals(code)
        if not data:
            raise HTTPException(404, f"{code} 無基本面數據")
        return {"fundamentals": data}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"獲取 {code} 基本面失敗: {e}")
        raise HTTPException(500, str(e))


@router.post("/api/data/fundamentals/screen")
async def screen_fundamentals_api(body: dict):
    """按基本面指標篩選股票"""
    from src.core.fundamental import screen_by_fundamentals
    
    filters = body.get("filters", {})
    if not filters:
        raise HTTPException(400, "請提供篩選條件，如 pe_max, pb_max, roe_min 等")
    
    try:
        results = screen_by_fundamentals(filters)
        return {"results": results, "total": len(results), "filters": filters}
    except Exception as e:
        logger.error(f"基本面篩選失敗: {e}")
        raise HTTPException(500, str(e))
