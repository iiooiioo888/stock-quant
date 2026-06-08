"""多幣種資產結算 API"""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Query

from src.core.auth import require_auth
from src.core.exchange import SUPPORTED_CURRENCIES, get_exchange_service
from src.core.portfolio_settlement import (
    get_portfolio_settlement_service,
    get_user_preferred_currency,
    set_user_preferred_currency,
)

router = APIRouter(tags=["portfolio-settlement"])

_CURRENCY_RE = re.compile(r"^(HKD|MOP|USD|CNY)$")


def _parse_currency(value: str | None) -> str | None:
    if value is None:
        return None
    c = value.strip().upper()
    if not _CURRENCY_RE.match(c):
        raise HTTPException(400, "currency 必須為 HKD、MOP、USD 或 CNY")
    return c


@router.get("/api/portfolio/fx-rates")
async def get_fx_rates():
    """最新 USD 基準匯率（四幣種）。"""
    svc = get_exchange_service()
    rates = svc.get_rates()
    return {
        "success": True,
        "base": "USD",
        "rates": {k: rates[k] for k in sorted(SUPPORTED_CURRENCIES) if k in rates},
        "fx_updated": svc.fx_updated_iso(),
        "supported": sorted(SUPPORTED_CURRENCIES),
    }


@router.get("/api/portfolio/summary")
async def portfolio_summary(
    currency: str | None = Query(None, description="結算幣種 HKD|MOP|USD|CNY"),
    user=Depends(require_auth),
):
    target = _parse_currency(currency)
    return get_portfolio_settlement_service().get_summary(user.id, target)


@router.get("/api/portfolio/trend")
async def portfolio_trend(
    currency: str | None = Query(None),
    days: int = Query(90, ge=7, le=365),
    user=Depends(require_auth),
):
    target = _parse_currency(currency)
    return get_portfolio_settlement_service().get_trend(
        user.id, days=days, currency=target
    )


@router.get("/api/user/preferred-currency")
async def get_preferred_currency(user=Depends(require_auth)):
    return {
        "success": True,
        "preferred_currency": get_user_preferred_currency(user.id),
        "supported": sorted(SUPPORTED_CURRENCIES),
    }


@router.put("/api/user/preferred-currency")
async def put_preferred_currency(body: dict, user=Depends(require_auth)):
    raw = (body.get("preferred_currency") or body.get("currency") or "").strip().upper()
    if not _CURRENCY_RE.match(raw):
        raise HTTPException(400, "preferred_currency 必須為 HKD、MOP、USD 或 CNY")
    saved = set_user_preferred_currency(user.id, raw)
    try:
        import json
        from src.core.db import get_conn

        with get_conn() as conn:
            row = conn.execute(
                "SELECT settings FROM users WHERE id = ?", (user.id,)
            ).fetchone()
            st = {}
            if row and row[0]:
                try:
                    st = json.loads(row[0])
                except (json.JSONDecodeError, TypeError):
                    st = {}
            st["preferred_currency"] = saved
            conn.execute(
                "UPDATE users SET settings = ? WHERE id = ?",
                (json.dumps(st, ensure_ascii=False), user.id),
            )
    except Exception:
        pass
    return {"success": True, "preferred_currency": saved}
