"""signals_heatmap 路由（P5 從 app.py 拆分）。"""
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


@router.post("/api/heatmap")
async def run_heatmap(
    code: str,
    strategy: str,
    param_x: str,
    param_y: str,
    grid_size: int = 10,
    objective: str = "sharpe",
    user: User = Depends(require_auth),
):
    """參數敏感度熱力圖"""
    from src.core.entitlements import gate_backtest_submit
    from src.core.heatmap import param_heatmap
    from src.core.result_cache import get_cached_compute, set_cached_compute

    gate_backtest_submit(user, advanced=True)

    param_x = (param_x or "").strip()
    param_y = (param_y or "").strip()
    if not param_x or not param_y:
        raise HTTPException(400, "請選擇參數 X 和參數 Y（不可為空）")

    cache_params = {
        "code": code, "strategy": strategy,
        "param_x": param_x, "param_y": param_y,
        "grid_size": grid_size, "objective": objective,
    }
    cached = get_cached_compute("heatmap", cache_params, code=code)
    if cached is not None:
        return {"success": True, "result": cached, "from_cache": True}

    try:
        result = param_heatmap(
            code=code, strategy_name=strategy,
            param_x=param_x, param_y=param_y,
            grid_size=grid_size, objective=objective,
        )
        set_cached_compute("heatmap", cache_params, result, code=code)
        return {"success": True, "result": result, "from_cache": False}
    except Exception as e:
        logger.error(f"熱力圖失敗: {e}")
        raise HTTPException(500, str(e))




@router.get("/api/heatmap/params/{strategy}")
async def get_strategy_params(strategy: str):
    """獲取策略的可調參數"""
    from src.core.backtest import STRATEGIES
    from src.core.optimize import PARAM_GRIDS

    if strategy not in STRATEGIES:
        raise HTTPException(400, f"未知策略: {strategy}")

    from src.core.heatmap import _get_default_params
    from src.core.strategy_params_meta import PARAM_LABELS

    defaults = _get_default_params(strategy)
    grid = PARAM_GRIDS.get(strategy, {})

    return {
        "strategy": strategy,
        "params": list(defaults.keys()),
        "defaults": defaults,
        "grid_values": grid,
        "labels": {k: PARAM_LABELS.get(k, k) for k in defaults.keys()},
    }


# ====== 股票篩選 ======



@router.get("/api/signals/current")
async def get_current_signals():
    """獲取所有監控股票的當前信號"""
    from src.api.routers.data_ops import _fetch_current_signals
    try:
        signals_data = _fetch_current_signals()
        return {"success": True, "signals": signals_data, "total": len(signals_data)}
    except Exception as e:
        logger.error(f"獲取當前信號失敗: {e}")
        raise HTTPException(500, str(e))




@router.get("/api/signals/trading")
async def get_trading_signals():
    """儀表盤交易信號（與 current 同源，兼容舊前端路由）"""
    from src.api.routers.data_ops import _fetch_current_signals
    try:
        signals_data = _fetch_current_signals()
        return {"success": True, "signals": signals_data, "data": signals_data, "total": len(signals_data)}
    except Exception as e:
        logger.error(f"獲取交易信號失敗: {e}")
        raise HTTPException(500, str(e))




@router.get("/api/signals/history")
async def get_signal_history(code: str = None, strategy: str = None, days: int = 30, user = Depends(get_current_user)):
    """獲取歷史信號記錄（登錄用戶優先看自己的數據）"""
    from src.core.signals import get_historical_signals
    from src.core.db import get_signal_logs

    user_id = user.id if user else None
    try:
        if code:
            logs = get_signal_logs(code=code, strategy=strategy, days=days, user_id=user_id)
            if not logs:
                logs = get_historical_signals(code=code, days=days, strategy=strategy)
            return {"success": True, "signals": logs, "total": len(logs)}
        else:
            logs = get_signal_logs(strategy=strategy, days=days, user_id=user_id)
            return {"success": True, "signals": logs, "total": len(logs)}
    except Exception as e:
        logger.error(f"獲取歷史信號失敗: {e}")
        raise HTTPException(500, str(e))




@router.get("/api/signals/strength")
async def get_signal_strength(code: str = None):
    """獲取信號強度綜合分數"""
    from src.core.signals import get_current_signals_for_codes, score_signal_strength

    if not code:
        raise HTTPException(400, "請提供股票代碼")

    try:
        rows = get_current_signals_for_codes([code])
        row = rows[0] if rows else {}
        latest_signals = row.get("signals") or []
        strength = score_signal_strength(latest_signals)
        return {
            "success": True,
            "code": code,
            "strength": strength,
            "signals": latest_signals,
            "signals_count": len(latest_signals),
            "updated_at": row.get("updated_at"),
        }
    except Exception as e:
        logger.error(f"獲取信號強度失敗: {e}")
        raise HTTPException(500, str(e))


# ====== 數據導出 ======



@router.get("/api/signals/backtest")
async def signals_backtest(
    codes: str = None,
    strategies: str = None,
    days: int = 250,
):
    """信號回測驗證 — 計算歷史信號的準確率和前向收益"""
    from src.core.signals import backtest_signals

    try:
        code_list = codes.split(",") if codes else None
        strat_list = strategies.split(",") if strategies else None

        result = backtest_signals(codes=code_list, strategies=strat_list, days=days)
        return {"success": True, "result": result}

    except Exception as e:
        logger.error(f"信號回測失敗: {e}")
        raise HTTPException(500, str(e))




@router.get("/api/signals/heatmap")
async def signals_heatmap(
    codes: str = None,
    days: int = 30,
):
    """信號熱力圖 — codes × dates × signal_strength 矩陣"""
    from src.core.signals import signal_heatmap

    try:
        code_list = codes.split(",") if codes else None
        result = signal_heatmap(codes=code_list, days=days)
        return {"success": True, "result": result}

    except Exception as e:
        logger.error(f"信號熱力圖失敗: {e}")
        raise HTTPException(500, str(e))




@router.get("/api/signals/ranking")
async def signals_ranking(
    codes: str = None,
):
    """綜合信號排名 — 按複合信號強度排名所有股票"""
    from src.core.signals import composite_signal_ranking

    try:
        code_list = codes.split(",") if codes else None
        result = composite_signal_ranking(codes=code_list)
        return {"success": True, "result": result, "total": len(result)}

    except Exception as e:
        logger.error(f"信號排名失敗: {e}")
        raise HTTPException(500, str(e))


# ====== 數據增強 API ======


# ====== 增強回測分析 API ======



