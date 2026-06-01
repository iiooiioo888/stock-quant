"""
多因子選股 API — 因子定義、計算、IC 分析、正交化、選股打分
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from src.core.auth import require_auth
from src.models.user import User
from src.utils.logger import logger

router = APIRouter()


@router.get("/api/factors/definitions")
async def factor_definitions():
    """列出所有因子定義（名稱、類別、方向、說明）"""
    from src.core.factor_engine import list_factor_definitions, list_factor_categories
    return {
        "success": True,
        "factors": list_factor_definitions(),
        "categories": list_factor_categories(),
    }


@router.post("/api/factors/screen")
async def factor_screen(body: dict, user: User = Depends(require_auth)):
    """
    多因子選股打分。

    body:
        codes: list[str] — 股票代碼列表
        weights: dict[str, float] — 因子權重（可選，默認等權）
        top_n: int — 返回前 N 名（默認 20）
    """
    from src.core.factor_engine import screen_by_factors
    from src.core.fundamental import get_fundamentals
    from src.core.db import load_daily_kline

    codes = body.get("codes") or []
    if not codes:
        raise HTTPException(400, "請提供股票代碼列表 (codes)")
    if len(codes) > 500:
        raise HTTPException(400, "最多支持 500 只股票")

    weights = body.get("weights")
    top_n = body.get("top_n", 20)

    # 載入基本面數據
    fundamentals_map = {}
    for code in codes:
        try:
            fund = get_fundamentals(code, max_age_days=30)
            if fund:
                fundamentals_map[code] = fund
        except Exception:
            pass

    # 載入 K 線數據
    import pandas as pd
    kline_map = {}
    for code in codes:
        try:
            df = load_daily_kline(code)
            if df is not None and not df.empty:
                kline_map[code] = df
        except Exception:
            pass

    results = screen_by_factors(
        codes=codes,
        fundamentals_map=fundamentals_map,
        kline_map=kline_map,
        weights=weights,
        top_n=top_n,
    )

    return {
        "success": True,
        "results": results,
        "total": len(codes),
        "returned": len(results),
    }


@router.post("/api/factors/ic")
async def factor_ic_analysis(body: dict, user: User = Depends(require_auth)):
    """
    因子 IC 分析。

    body:
        factor_values: list[float] — 因子值序列
        forward_returns: list[float] — 對應的未來收益率
    """
    from src.core.factor_engine import compute_ic

    fv = body.get("factor_values") or []
    fr = body.get("forward_returns") or []

    if not fv or not fr:
        raise HTTPException(400, "請提供 factor_values 和 forward_returns")

    result = compute_ic(fv, fr)
    return {"success": True, "result": result}