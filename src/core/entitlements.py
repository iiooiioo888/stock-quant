"""
用戶訂閱權益 — 方案解析、功能開關、每日配額。
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any, Optional

from fastapi import Depends, HTTPException

from src.core.auth import get_current_user, require_admin, require_auth
from src.core.billing_plans import FEATURE_LABELS, plan_definition
from src.core.db import get_conn
from src.models.user import User
from src.utils.logger import logger

DEFAULT_BILLING = {
    "plan_id": "free",
    "status": "active",
    "expires_at": None,
    "provider": None,
    "updated_at": None,
}


def _parse_billing(settings: dict | None) -> dict[str, Any]:
    raw = (settings or {}).get("billing")
    if not isinstance(raw, dict):
        return dict(DEFAULT_BILLING)
    out = {**DEFAULT_BILLING, **raw}
    out["plan_id"] = str(out.get("plan_id") or "free").lower()
    if out["plan_id"] not in ("free", "pro", "institutional"):
        out["plan_id"] = "free"
    return out


def get_user_billing(user: User | None) -> dict[str, Any]:
    if not user:
        return dict(DEFAULT_BILLING)
    if user.role == "admin":
        b = _parse_billing(user.settings)
        b["plan_id"] = "institutional"
        b["status"] = "active"
        return b
    return _parse_billing(user.settings)


def effective_plan_id(user: User | None) -> str:
    b = get_user_billing(user)
    if b.get("status") not in ("active", "trialing", None, ""):
        return "free"
    exp = b.get("expires_at")
    if exp:
        try:
            if datetime.fromisoformat(str(exp).replace("Z", "")) < datetime.now():
                return "free"
        except ValueError:
            pass
    return b.get("plan_id") or "free"


def user_has_feature(user: User | None, feature: str) -> bool:
    if not user:
        return feature in plan_definition("free").features
    pid = effective_plan_id(user)
    return feature in plan_definition(pid).features


def billing_summary(user: User | None) -> dict[str, Any]:
    pid = effective_plan_id(user)
    plan = plan_definition(pid)
    billing = get_user_billing(user)
    usage = usage_snapshot(user.id if user else 0)
    return {
        "plan_id": pid,
        "plan_name": plan.name,
        "status": billing.get("status") or "active",
        "expires_at": billing.get("expires_at"),
        "limits": {
            "daily_backtests": plan.limits.daily_backtests,
            "daily_portfolio_runs": plan.limits.daily_portfolio_runs,
            "daily_optimize_runs": plan.limits.daily_optimize_runs,
            "max_watchlist": plan.limits.max_watchlist,
            "max_allocation_positions": plan.limits.max_allocation_positions,
            "concurrent_tasks": plan.limits.concurrent_tasks,
        },
        "features": sorted(plan.features),
        "feature_labels": {k: FEATURE_LABELS.get(k, k) for k in plan.features},
        "usage": usage,
    }


def _load_user_settings(user_id: int) -> dict:
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT settings FROM users WHERE id = ?", (user_id,)).fetchone()
    if not row or not row["settings"]:
        return {}
    try:
        data = json.loads(row["settings"])
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _save_user_settings(user_id: int, settings: dict) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET settings = ? WHERE id = ?",
            (json.dumps(settings, ensure_ascii=False), user_id),
        )


def usage_snapshot(user_id: int) -> dict[str, int]:
    out = {"backtests_today": 0, "portfolio_runs_today": 0, "optimize_runs_today": 0}
    if not user_id:
        return out
    today = datetime.now().strftime("%Y-%m-%d")
    st = _load_user_settings(user_id)
    usage = (st.get("billing") or {}).get("usage") or {}
    day = usage.get(today) if isinstance(usage, dict) else {}
    if isinstance(day, dict):
        out["backtests_today"] = int(day.get("backtest") or 0)
        out["portfolio_runs_today"] = int(day.get("portfolio") or 0)
        out["optimize_runs_today"] = int(day.get("optimize") or 0)
    return out


def record_usage(user: User, metric: str) -> None:
    """記錄當日用量（提交任務前調用）。"""
    if not user or not user.id:
        return
    today = datetime.now().strftime("%Y-%m-%d")
    st = _load_user_settings(user.id)
    billing = st.get("billing") if isinstance(st.get("billing"), dict) else {}
    usage = billing.get("usage") if isinstance(billing.get("usage"), dict) else {}
    day = usage.get(today) if isinstance(usage.get(today), dict) else {}
    day[metric] = int(day.get(metric) or 0) + 1
    usage[today] = day
    billing["usage"] = usage
    st["billing"] = billing
    _save_user_settings(user.id, st)


def _feature_locked(feature: str, message: str, user: User | None = None) -> None:
    raise HTTPException(
        403,
        detail={
            "code": "feature_locked",
            "feature": feature,
            "message": message,
            "current_plan": effective_plan_id(user) if user else "free",
            "upgrade_url": "/app#/pricing",
        },
    )


def gate_backtest_submit(user: User | None, *, advanced: bool = False) -> None:
    """回測提交：登錄用戶計入配額；進階參數需 backtest_advanced。"""
    if advanced:
        if not user:
            raise HTTPException(status_code=401, detail="進階回測需登錄")
        if not user_has_feature(user, "backtest_advanced"):
            _feature_locked("backtest_advanced", "進階風控回測需 Pro 方案", user)
    if user:
        check_quota(user, "backtest")
        record_usage(user, "backtest")


def gate_optimize_submit(user: User) -> None:
    if not user:
        raise HTTPException(status_code=401, detail="參數優化需登錄")
    check_quota(user, "optimize")
    record_usage(user, "optimize")


def gate_compare_submit(user: User | None, codes: list) -> None:
    """多股對比：2 隻以上或非 A 股代碼需 compare_multimarket（登錄）。"""
    normalized = [str(c or "").strip().upper() for c in (codes or []) if str(c or "").strip()]
    needs_pro = len(normalized) >= 2 or any(
        "." in c or c.isalpha() or (c.isdigit() and len(c) != 6)
        for c in normalized
    )
    if not needs_pro:
        return
    if not user:
        raise HTTPException(status_code=401, detail="多市場/多股對比需登錄")
    if not user_has_feature(user, "compare_multimarket"):
        _feature_locked("compare_multimarket", "多市場多股對比需 Pro 方案", user)


def gate_allocation_cloud(user: User) -> None:
    if not user_has_feature(user, "allocation_cloud"):
        _feature_locked("allocation_cloud", "雲端配置同步需 Pro 方案", user)


def gate_ai_assistant(user: User) -> None:
    if not user_has_feature(user, "ai_assistant"):
        _feature_locked("ai_assistant", "AI 投研助手需 Pro 方案", user)


def gate_data_export(user: User) -> None:
    if not user_has_feature(user, "data_export"):
        _feature_locked("data_export", "結果導出需 Pro 方案", user)


def user_assets_pro(user: User | None) -> bool:
    return user_has_feature(user, "assets_pro") if user else False


def check_position_cap(user: User, position_count: int) -> None:
    cap = plan_definition(effective_plan_id(user)).limits.max_allocation_positions
    if position_count > cap:
        raise HTTPException(
            403,
            detail={
                "code": "limit_exceeded",
                "limit": "max_allocation_positions",
                "message": f"持倉數量已達方案上限（{cap} 檔）",
                "used": position_count,
                "cap": cap,
                "upgrade_url": "/app#/pricing",
            },
        )


def check_watchlist_codes_cap(user: User, code_count: int) -> None:
    cap = plan_definition(effective_plan_id(user)).limits.max_watchlist
    if code_count > cap:
        raise HTTPException(
            403,
            detail={
                "code": "limit_exceeded",
                "limit": "max_watchlist",
                "message": f"自選股數量已達方案上限（{cap} 隻）",
                "used": code_count,
                "cap": cap,
                "upgrade_url": "/app#/pricing",
            },
        )


def gate_portfolio_task(user: User, *, advanced: bool = False) -> None:
    """組合任務提交前：功能權益 + 每日配額（通過後由調用方或本函數記錄用量）。"""
    if not user_has_feature(user, "portfolio_basic"):
        raise HTTPException(
            403,
            detail={
                "code": "feature_locked",
                "feature": "portfolio_basic",
                "message": "組合回測需登錄；Free 方案含基礎組合回測",
                "upgrade_url": "/app#/pricing",
            },
        )
    if advanced and not user_has_feature(user, "portfolio_advanced"):
        raise HTTPException(
            403,
            detail={
                "code": "feature_locked",
                "feature": "portfolio_advanced",
                "message": "進階組合（風險平價、MVO 等）需 Pro 方案",
                "current_plan": effective_plan_id(user),
                "upgrade_url": "/app#/pricing",
            },
        )
    check_quota(user, "portfolio")
    record_usage(user, "portfolio")


def check_quota(user: User, metric: str) -> None:
    """配額不足時拋 429（檢查後由調用方 record_usage）。"""
    plan = plan_definition(effective_plan_id(user))
    usage = usage_snapshot(user.id)
    limits = plan.limits
    checks = {
        "backtest": (usage["backtests_today"], limits.daily_backtests, "回測"),
        "portfolio": (usage["portfolio_runs_today"], limits.daily_portfolio_runs, "組合回測"),
        "optimize": (usage["optimize_runs_today"], limits.daily_optimize_runs, "參數優化"),
    }
    key = metric if metric in checks else "backtest"
    used, cap, label = checks[key]
    if cap <= 0:
        raise HTTPException(
            403,
            detail={
                "code": "plan_required",
                "message": f"當前方案不包含{label}功能，請升級 Pro",
                "plan_id": effective_plan_id(user),
                "upgrade_url": "/app#/pricing",
            },
        )
    if used >= cap:
        raise HTTPException(
            429,
            detail={
                "code": "quota_exceeded",
                "message": f"今日{label}次數已達上限（{cap} 次/日）",
                "used": used,
                "limit": cap,
                "upgrade_url": "/app#/pricing",
            },
        )


def require_feature(feature: str):
    async def _dep(user: User = Depends(require_auth)) -> User:
        if not user_has_feature(user, feature):
            pid = effective_plan_id(user)
            need = "pro" if feature != "team_seats" else "institutional"
            raise HTTPException(
                403,
                detail={
                    "code": "feature_locked",
                    "feature": feature,
                    "message": f"此功能需要 {plan_definition(need).name} 方案",
                    "current_plan": pid,
                    "upgrade_url": "/app#/pricing",
                },
            )
        return user

    return _dep


def set_user_plan(user_id: int, plan_id: str, *, status: str = "active", expires_at: str | None = None) -> None:
    plan_id = (plan_id or "free").lower()
    if plan_id not in ("free", "pro", "institutional"):
        raise ValueError("無效方案")
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT settings FROM users WHERE id = ?", (user_id,)).fetchone()
        if not row:
            raise ValueError("用戶不存在")
        try:
            st = json.loads(row["settings"] or "{}")
        except (json.JSONDecodeError, TypeError):
            st = {}
        if not isinstance(st, dict):
            st = {}
        st["billing"] = {
            "plan_id": plan_id,
            "status": status,
            "expires_at": expires_at,
            "provider": "manual",
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }
        conn.execute(
            "UPDATE users SET settings = ? WHERE id = ?",
            (json.dumps(st, ensure_ascii=False), user_id),
        )
