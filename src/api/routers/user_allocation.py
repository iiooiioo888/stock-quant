"""個人資產配置 API — 與 /api/portfolio/summary 共用 holdings 欄位。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from src.core.auth import require_auth
from src.core.user_allocation import (
    allocation_payload,
    list_positions,
    remove_position,
    replace_positions,
    upsert_position,
)

router = APIRouter(tags=["user-allocation"])


@router.get("/api/my-allocation")
async def get_my_allocation(
    user=Depends(require_auth),
    weight_mode: str = "market_value",
):
    return allocation_payload(user.id, weight_mode=weight_mode)


@router.put("/api/my-allocation")
async def put_my_allocation(body: dict, user=Depends(require_auth)):
    positions = body.get("positions") if isinstance(body, dict) else None
    if positions is None:
        positions = body.get("holdings") if isinstance(body, dict) else []
    if not isinstance(positions, list):
        raise HTTPException(400, "positions 必須為陣列")
    replace_positions(user.id, positions)
    return allocation_payload(user.id)


@router.post("/api/my-allocation/positions")
async def post_position(body: dict, user=Depends(require_auth)):
    if not isinstance(body, dict):
        raise HTTPException(400, "請提供 JSON 物件")
    try:
        upsert_position(user.id, body)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return allocation_payload(user.id)


@router.delete("/api/my-allocation/positions/{code}")
async def delete_position(code: str, user=Depends(require_auth)):
    remove_position(user.id, code)
    return allocation_payload(user.id)
