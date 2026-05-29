"""訂閱與方案 API — 定價頁、權益查詢、開發環境升級、Stripe Webhook 占位。"""
from __future__ import annotations

import hmac
import hashlib
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request

from src.config import settings
from src.core.auth import get_current_user, get_user_by_id, require_admin, require_auth
from src.core.billing_plans import FEATURE_LABELS, plans_public_payload
from src.core.entitlements import billing_summary, set_user_plan
from src.models.user import User

router = APIRouter(tags=["billing"])


@router.get("/api/billing/plans")
async def get_billing_plans():
    """公開：方案與功能對照（定價頁）。"""
    return {
        "success": True,
        "plans": plans_public_payload(),
        "feature_labels": FEATURE_LABELS,
        "feature_order": sorted(FEATURE_LABELS.keys()),
        "payment_note": (
            "線上支付（Stripe / 微信 / 支付寶）將於下一階段接入；"
            "目前可註冊後在開發環境申請試用升級，或聯繫銷售開通機構版。"
        ),
        "billing_enabled": bool(getattr(settings, "billing_checkout_enabled", False)),
    }


@router.get("/api/billing/me")
async def get_billing_me(user: User = Depends(require_auth)):
    """當前用戶方案、配額與用量。"""
    return {"success": True, **billing_summary(user)}


@router.post("/api/billing/checkout")
async def billing_checkout(body: dict, user: User = Depends(require_auth)):
    """
    訂閱/checkout。

    - 生產：預留 Stripe（需 SQ_STRIPE_SECRET_KEY）
    - 開發：SQ_BILLING_DEV_UPGRADE=true 時可直接升級試用
    """
    plan_id = str((body or {}).get("plan_id") or "").strip().lower()
    if plan_id not in ("pro", "pro_ai", "institutional"):
        raise HTTPException(400, "僅支持升級至 pro、pro_ai 或 institutional")

    if plan_id == "institutional":
        raise HTTPException(
            400,
            detail={
                "code": "contact_sales",
                "message": "機構版請聯繫銷售定制報價與部署",
            },
        )

    stripe_key = getattr(settings, "stripe_secret_key", None) or ""
    if stripe_key:
        raise HTTPException(
            501,
            detail="Stripe 整合開發中，請稍後或聯繫開通",
        )

    if not getattr(settings, "billing_dev_upgrade", True):
        raise HTTPException(
            503,
            detail="線上支付尚未開通，請聯繫管理員開通方案",
        )

    trial_days = int((body or {}).get("trial_days") or 14)
    expires_at = None
    status = "active"
    if trial_days > 0:
        expires_at = (datetime.now() + timedelta(days=trial_days)).isoformat(timespec="seconds")
        status = "trialing"
    set_user_plan(user.id, plan_id, status=status, expires_at=expires_at)
    fresh_user = get_user_by_id(user.id) or user
    refreshed = billing_summary(fresh_user)
    return {
        "success": True,
        "message": f"已開通試用 {plan_id.upper()}（{trial_days} 天，開發/演示環境）",
        "provider": "dev_manual",
        "trial_days": trial_days,
        "expires_at": expires_at,
        **refreshed,
    }


@router.post("/api/billing/webhook/stripe")
async def stripe_webhook(request: Request):
    """
    Stripe Webhook（占位）。

    生產需設定 SQ_STRIPE_WEBHOOK_SECRET，並依 checkout.session.completed 更新用戶方案。
    """
    secret = getattr(settings, "stripe_webhook_secret", None) or ""
    if not secret:
        raise HTTPException(
            501,
            detail={
                "code": "stripe_not_configured",
                "message": "Stripe Webhook 尚未配置（SQ_STRIPE_WEBHOOK_SECRET）",
            },
        )
    body = await request.body()
    sig = request.headers.get("stripe-signature", "")
    # 簡易校驗占位：生產應使用 stripe.Webhook.construct_event
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    if not sig or expected not in sig:
        raise HTTPException(400, "簽名驗證失敗")
    return {"success": True, "received": True, "note": "事件處理邏輯待接入"}


@router.post("/api/billing/admin/set-plan")
async def admin_set_plan(body: dict, _admin: User = Depends(require_admin)):
    """管理員：為指定用戶設定方案。"""
    user_id = int(body.get("user_id") or 0)
    plan_id = str(body.get("plan_id") or "free").lower()
    if not user_id:
        raise HTTPException(400, "user_id required")
    set_user_plan(user_id, plan_id, status=str(body.get("status") or "active"))
    return {"success": True, "user_id": user_id, "plan_id": plan_id}
