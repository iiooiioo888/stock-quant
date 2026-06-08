"""paper 路由（P5 從 app.py 拆分）。"""

import json
import time
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse, HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from src.config import settings
from src.core.auth import require_auth, require_admin, get_current_user
from src.models.user import User
from src.utils.logger import logger

router = APIRouter()


@router.post("/api/paper/start")
async def start_paper_trading(body: dict = None):
    """啟動模擬交易"""
    from src.core.paper_trading import PaperTradingEngine

    if body is None:
        body = {}

    try:
        engine = PaperTradingEngine(
            capital=body.get("capital"),
            name=body.get("name", "默認模擬盤"),
            sizing_method=body.get("sizing_method", "atr"),
            min_signal_strength=body.get("min_signal_strength", 10.0),
        )
        engine.start()
        return {
            "success": True,
            "session_id": engine.session_id,
            "status": engine.get_status(),
        }
    except Exception as e:
        logger.error(f"啟動模擬交易失敗: {e}")
        raise HTTPException(500, str(e))


@router.post("/api/paper/{session_id}/tick")
async def paper_trading_tick(session_id: str):
    """執行一個模擬交易週期"""
    from src.core.paper_trading import PaperTradingEngine

    # 從數據庫恢復 session
    from src.core.paper_trading import get_paper_session

    session = get_paper_session(session_id)
    if not session:
        raise HTTPException(404, f"模擬盤不存在: {session_id}")

    try:
        config = {}
        if session.get("config"):
            import json

            config = json.loads(session["config"])

        engine = PaperTradingEngine(
            capital=session["initial_capital"],
            name=session["name"],
            session_id=session_id,
            sizing_method=config.get("sizing_method", "atr"),
            min_signal_strength=config.get("min_signal_strength", 10.0),
        )
        engine.start()
        trades = engine.tick()
        return {"success": True, "trades": trades, "status": engine.get_status()}
    except Exception as e:
        logger.error(f"模擬交易 tick 失敗: {e}")
        raise HTTPException(500, str(e))


@router.get("/api/paper/{session_id}/status")
async def paper_trading_status(session_id: str):
    """獲取模擬盤狀態"""
    from src.core.paper_trading import get_paper_session

    session = get_paper_session(session_id)
    if not session:
        raise HTTPException(404, f"模擬盤不存在: {session_id}")
    return {"success": True, "session": session}


@router.get("/api/paper/{session_id}/trades")
async def paper_trading_log(session_id: str, limit: int = 100):
    """獲取模擬盤交易日誌"""
    from src.core.paper_trading import PaperTradingEngine

    engine = PaperTradingEngine(session_id=session_id)
    return {"success": True, "trades": engine.get_trade_log(limit)}


@router.get("/api/paper/{session_id}/nav")
async def paper_trading_nav(session_id: str):
    """獲取模擬盤淨值歷史"""
    from src.core.paper_trading import PaperTradingEngine

    engine = PaperTradingEngine(session_id=session_id)
    return {"success": True, "nav_history": engine.get_nav_history()}


@router.get("/api/paper/sessions")
async def list_paper_sessions_api():
    """列出所有模擬盤"""
    from src.core.paper_trading import list_paper_sessions

    return {"success": True, "sessions": list_paper_sessions()}


@router.delete("/api/paper/{session_id}")
async def delete_paper_session_api(session_id: str):
    """刪除模擬盤"""
    from src.core.paper_trading import delete_paper_session

    success = delete_paper_session(session_id)
    if not success:
        raise HTTPException(404, f"模擬盤不存在: {session_id}")
    return {"success": True, "message": "已刪除"}


# ====== 調度器增強 API ======
