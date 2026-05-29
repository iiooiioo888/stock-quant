"""
策略市場 API 路由
"""
from fastapi import APIRouter, HTTPException, Query, Body
from typing import Optional, List
from datetime import datetime

from src.marketplace.models import (
    StrategyModel,
    StrategyRating,
    StrategyShare,
    StrategyVisibility,
    StrategyCategory,
)
from src.marketplace.registry import StrategyMarketplace


def get_marketplace_router() -> APIRouter:
    """獲取策略市場 API 路由"""
    router = APIRouter(prefix="/api/marketplace", tags=["marketplace"])
    
    @router.post("/strategies")
    async def upload_strategy(strategy_data: dict = Body(...)):
        """上傳策略"""
        marketplace = StrategyMarketplace()
        strategy = StrategyModel.from_dict(strategy_data)
        result = marketplace.upload_strategy(strategy)
        
        if not result["success"]:
            raise HTTPException(status_code=400, detail=result.get("error", "上傳失敗"))
        
        return result
    
    @router.get("/strategies")
    async def list_strategies(
        category: Optional[str] = Query(None),
        visibility: str = Query("public"),
        author: Optional[str] = Query(None),
        limit: int = Query(50, ge=1, le=100),
        offset: int = Query(0, ge=0),
    ):
        """列出策略"""
        marketplace = StrategyMarketplace()
        
        try:
            cat = StrategyCategory(category) if category else None
            vis = StrategyVisibility(visibility)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"無效的參數：{e}")
        
        strategies = marketplace.list_strategies(
            category=cat,
            visibility=vis,
            author=author,
            limit=limit,
            offset=offset,
        )
        
        return {
            "count": len(strategies),
            "strategies": [s.to_dict() for s in strategies],
        }
    
    @router.get("/strategies/{strategy_id}")
    async def get_strategy(strategy_id: str):
        """獲取策略詳情"""
        marketplace = StrategyMarketplace()
        strategy = marketplace.get_strategy(strategy_id)
        
        if not strategy:
            raise HTTPException(status_code=404, detail="策略不存在")
        
        # 增加下載計數
        marketplace.increment_download_count(strategy_id)
        
        return strategy.to_dict()
    
    @router.delete("/strategies/{strategy_id}")
    async def delete_strategy(strategy_id: str, user_id: str = Query(...)):
        """刪除策略"""
        marketplace = StrategyMarketplace()
        result = marketplace.delete_strategy(strategy_id, user_id)
        
        if not result["success"]:
            raise HTTPException(status_code=400, detail=result.get("error", "刪除失敗"))
        
        return result
    
    @router.post("/strategies/{strategy_id}/rate")
    async def rate_strategy(strategy_id: str, rating_data: dict = Body(...)):
        """評分策略"""
        marketplace = StrategyMarketplace()
        
        rating = StrategyRating(
            strategy_id=strategy_id,
            user_id=rating_data.get("user_id", "anonymous"),
            rating=rating_data.get("rating", 5),
            comment=rating_data.get("comment", ""),
        )
        
        result = marketplace.rate_strategy(rating)
        
        if not result["success"]:
            raise HTTPException(status_code=400, detail=result.get("error", "評分失敗"))
        
        return result
    
    @router.get("/strategies/{strategy_id}/ratings")
    async def get_strategy_ratings(strategy_id: str):
        """獲取策略評分"""
        marketplace = StrategyMarketplace()
        ratings = marketplace.get_ratings(strategy_id)
        avg_rating = marketplace._get_average_rating(strategy_id)
        
        return {
            "average_rating": avg_rating,
            "total_ratings": len(ratings),
            "ratings": [r.to_dict() for r in ratings],
        }
    
    @router.get("/strategies/{strategy_id}/stats")
    async def get_strategy_stats(strategy_id: str):
        """獲取策略統計數據"""
        marketplace = StrategyMarketplace()
        stats = marketplace.get_strategy_stats(strategy_id)
        
        if "error" in stats:
            raise HTTPException(status_code=404, detail=stats["error"])
        
        return stats
    
    @router.post("/strategies/{strategy_id}/share")
    async def share_strategy(
        strategy_id: str,
        share_data: dict = Body(...),
    ):
        """創建分享連結"""
        marketplace = StrategyMarketplace()
        
        expires_at = None
        if share_data.get("expires_at"):
            expires_at = datetime.fromisoformat(share_data["expires_at"])
        
        share = marketplace.share_strategy(
            strategy_id=strategy_id,
            shared_by=share_data.get("shared_by", "anonymous"),
            expires_at=expires_at,
        )
        
        if not share:
            raise HTTPException(status_code=400, detail="創建分享連結失敗")
        
        return share.to_dict()
    
    @router.get("/shares/{token}")
    async def get_strategy_by_token(token: str):
        """通過分享 token 獲取策略"""
        marketplace = StrategyMarketplace()
        strategy = marketplace.get_strategy_by_token(token)
        
        if not strategy:
            raise HTTPException(status_code=404, detail="分享連結無效或已過期")
        
        return strategy.to_dict()
    
    @router.get("/categories")
    async def list_categories():
        """列出所有策略分類"""
        return {
            "categories": [
                {"value": cat.value, "label": cat.name.replace("_", " ").title()}
                for cat in StrategyCategory
            ]
        }
    
    @router.get("/search")
    async def search_strategies(
        q: str = Query(..., description="搜索關鍵字"),
        category: Optional[str] = Query(None),
        limit: int = Query(20, ge=1, le=50),
    ):
        """搜索策略（簡單實現，可擴展為全文搜索）"""
        marketplace = StrategyMarketplace()
        
        # 獲取所有公開策略
        strategies = marketplace.list_strategies(
            category=StrategyCategory(category) if category else None,
            visibility=StrategyVisibility.PUBLIC,
            limit=100,
        )
        
        # 簡單關鍵字匹配
        q_lower = q.lower()
        matched = []
        for s in strategies:
            if (q_lower in s.name.lower() or 
                q_lower in s.description.lower() or
                q_lower in s.author.lower() or
                any(q_lower in tag.lower() for tag in s.tags)):
                matched.append(s)
                if len(matched) >= limit:
                    break
        
        return {
            "query": q,
            "count": len(matched),
            "strategies": [s.to_dict() for s in matched],
        }
    
    return router
