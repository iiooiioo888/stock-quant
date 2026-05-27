"""大數據集 NDJSON 流式 API"""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.ndjson import ndjson_response
from src.core.auth import require_auth
from src.core.portfolio_settlement import get_portfolio_settlement_service

router = APIRouter(tags=["stream"])

_CURRENCY_RE = re.compile(r"^(HKD|MOP|USD|CNY)$")


def _parse_currency(value: str | None) -> str | None:
    if value is None:
        return None
    c = value.strip().upper()
    if not _CURRENCY_RE.match(c):
        raise HTTPException(400, "currency 必須為 HKD、MOP、USD 或 CNY")
    return c


@router.get("/api/portfolio/trend/stream")
async def portfolio_trend_stream(
    currency: str | None = Query(None),
    days: int = Query(90, ge=7, le=365),
    chunk_size: int = Query(50, ge=10, le=200),
    user=Depends(require_auth),
):
    """組合淨值趨勢 — NDJSON 分塊（每行為 series 子陣列）。"""
    target = _parse_currency(currency)
    payload = get_portfolio_settlement_service().get_trend(
        user.id, days=days, currency=target
    )
    series = payload.get("series") or []
    return ndjson_response(series, chunk_size=chunk_size)


@router.get("/api/backtest/{task_id}/equity/stream")
async def backtest_equity_stream(
    task_id: str,
    chunk_size: int = Query(100, ge=10, le=500),
    user=Depends(require_auth),
):
    """回測任務權益曲線 — NDJSON 分塊。"""
    from src.core.task_manager import get_task

    task = get_task(task_id)
    if not task:
        raise HTTPException(404, "任務不存在")
    result = task.get("result") or {}
    curve = result.get("equity_curve")
    if curve is None:
        raise HTTPException(404, "任務尚無權益曲線結果")
    if not isinstance(curve, list):
        raise HTTPException(400, "權益曲線格式無效")
    return ndjson_response(curve, chunk_size=chunk_size)
