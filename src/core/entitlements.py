"""
用戶訂閱權益 — 方案解析、功能開關、每日配額。
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from typing import Any

from fastapi import Depends, HTTPException

from src.core.auth import require_auth
from src.core.billing_plans import FEATURE_LABELS, plan_definition
from src.core.db import get_conn
from src.models.user import User

# ── 配額操作的 per-user 鎖（防止 read-modify-write 競態） ──────────
_quota_locks_lock = threading.Lock()
_quota_locks: dict[int, threading.Lock] = {}


def _get_user_quota_lock(user_id: int) -> threading.Lock:
    """獲取指定用戶的配額鎖（懶初始化，線程安全）。"""
    with _quota_locks_lock:
        lock = _quota_locks.get(user_id)
        if lock is None:
            lock = threading.Lock()
            _quota_locks[user_id] = lock
        return lock


DEFAULT_BILLING = {
    "plan_id": "free",
    "status": "active",
    "expires_at": None,
    "provider": None,
    "updated_at": None,
}

# 允許的方案 ID 列表（single source of truth）
_VALID_PLAN_IDS = frozenset({"free", "pro", "pro_ai", "institutional"})


def _parse_billing(settings: dict | None) -> dict[str, Any]:
    raw = (settings or {}).get("billing")
    if not isinstance(raw, dict):
        return dict(DEFAULT_BILLING)
    out = {**DEFAULT_BILLING, **raw}
    out["plan_id"] = str(out.get("plan_id") or "free").lower()
    if out["plan_id"] not in _VALID_PLAN_IDS:
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
            "daily_ai_queries": plan.limits.daily_ai_queries,
            "daily_walkforward": plan.limits.daily_walkforward,
            "daily_monte_carlo": plan.limits.daily_monte_carlo,
            "daily_signal_ranking": plan.limits.daily_signal_ranking,
            "daily_full_report": plan.limits.daily_full_report,
            "max_watchlist": plan.limits.max_watchlist,
            "max_custom_strategies": plan.limits.max_custom_strategies,
            "max_paper_sessions": plan.limits.max_paper_sessions,
            "max_allocation_positions": plan.limits.max_allocation_positions,
            "concurrent_tasks": plan.limits.concurrent_tasks,
            "realtime_ws_symbols": plan.limits.realtime_ws_symbols,
            "export_row_limit": plan.limits.export_row_limit,
        },
        "features": sorted(plan.features),
        "feature_labels": {k: FEATURE_LABELS.get(k, k) for k in plan.features},
        "usage": usage,
    }


def _load_user_settings(user_id: int) -> dict:
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT settings FROM users WHERE id = ?", (user_id,)
        ).fetchone()
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
    out = {
        "backtests_today": 0,
        "portfolio_runs_today": 0,
        "optimize_runs_today": 0,
        "ai_queries_today": 0,
        "walkforward_today": 0,
        "monte_carlo_today": 0,
        "signal_ranking_today": 0,
        "full_report_today": 0,
    }
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
        out["ai_queries_today"] = int(day.get("ai_query") or 0)
        out["walkforward_today"] = int(day.get("walkforward") or 0)
        out["monte_carlo_today"] = int(day.get("monte_carlo") or 0)
        out["signal_ranking_today"] = int(day.get("signal_ranking") or 0)
        out["full_report_today"] = int(day.get("full_report") or 0)
    return out


def record_usage(user: User, metric: str) -> None:
    """記錄當日用量（提交任務前調用）。使用 per-user 鎖保證原子性。"""
    if not user or not user.id:
        return
    lock = _get_user_quota_lock(user.id)
    with lock:
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


def check_and_record_usage(user: User, metric: str) -> None:
    """原子性地檢查配額並記錄用量（消除 check_quota + record_usage 的 TOCTOU）。

    Raises HTTPException 429/403 if quota exceeded.
    """
    from src.config import settings as app_settings

    if not user or not user.id:
        return
    lock = _get_user_quota_lock(user.id)
    with lock:
        if not app_settings.billing_quota_enforce:
            # 不 enforce 時仍記錄用量
            _record_usage_inner(user, metric)
            return

        plan = plan_definition(effective_plan_id(user))
        limits = plan.limits
        limit_map = {
            "backtest": (limits.daily_backtests, "回測"),
            "portfolio": (limits.daily_portfolio_runs, "組合回測"),
            "optimize": (limits.daily_optimize_runs, "參數優化"),
            "ai_query": (limits.daily_ai_queries, "AI 問答"),
            "walkforward": (limits.daily_walkforward, "Walk-Forward"),
            "monte_carlo": (limits.daily_monte_carlo, "蒙特卡羅"),
            "signal_ranking": (limits.daily_signal_ranking, "信號排名"),
            "full_report": (limits.daily_full_report, "全面報告"),
        }
        cap, label = limit_map.get(metric, limit_map["backtest"])
        if cap <= 0:
            raise HTTPException(
                403,
                detail={
                    "code": "plan_required",
                    "message": f"當前方案不包含{label}功能，請升級方案",
                    "plan_id": effective_plan_id(user),
                    "upgrade_url": "/app#/pricing",
                },
            )

        # 讀取當前用量（在同一把鎖內，不會被其他線程干擾）
        st = _load_user_settings(user.id)
        billing = st.get("billing") if isinstance(st.get("billing"), dict) else {}
        usage = billing.get("usage") if isinstance(billing.get("usage"), dict) else {}
        today = datetime.now().strftime("%Y-%m-%d")
        day = usage.get(today) if isinstance(usage.get(today), dict) else {}
        current = int(day.get(metric) or 0)

        if current >= cap:
            raise HTTPException(
                429,
                detail={
                    "code": "quota_exceeded",
                    "message": f"今日{label}次數已達上限（{cap} 次/日）",
                    "used": current,
                    "limit": cap,
                    "upgrade_url": "/app#/pricing",
                },
            )

        # 原子性地遞增
        day[metric] = current + 1
        usage[today] = day
        billing["usage"] = usage
        st["billing"] = billing
        _save_user_settings(user.id, st)


def _record_usage_inner(user: User, metric: str) -> None:
    """在已持有 per-user 鎖的情況下記錄用量（不檢查配額）。"""
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
        check_and_record_usage(user, "backtest")


def gate_optimize_submit(user: User) -> None:
    if not user:
        raise HTTPException(status_code=401, detail="參數優化需登錄")
    check_and_record_usage(user, "optimize")


def gate_compare_submit(user: User | None, codes: list) -> None:
    """多股對比：2 隻以上或非 A 股代碼需 compare_multimarket（登錄）。"""
    normalized = [
        str(c or "").strip().upper() for c in (codes or []) if str(c or "").strip()
    ]
    needs_pro = len(normalized) >= 2 or any(
        "." in c or c.isalpha() or (c.isdigit() and len(c) != 6) for c in normalized
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
    if user:
        check_and_record_usage(user, "ai_query")


def gate_ai_strategy_recommend(user: User) -> None:
    """AI 策略智能推薦（Pro+AI 方案）。"""
    if not user:
        raise HTTPException(status_code=401, detail="AI 策略推薦需登錄")
    if not user_has_feature(user, "ai_strategy_recommend"):
        _feature_locked("ai_strategy_recommend", "AI 策略推薦需 Pro+AI 方案", user)
    check_and_record_usage(user, "ai_query")


def gate_ai_report_interpret(user: User) -> None:
    """AI 回測報告解讀（Pro 方案）。"""
    if not user:
        raise HTTPException(status_code=401, detail="AI 報告解讀需登錄")
    if not user_has_feature(user, "ai_report_interpret"):
        _feature_locked("ai_report_interpret", "AI 回測報告解讀需 Pro 方案", user)
    check_and_record_usage(user, "ai_query")


def gate_ai_code_generate(user: User) -> None:
    """AI 策略代碼生成（Pro+AI 方案）。"""
    if not user:
        raise HTTPException(status_code=401, detail="AI 代碼生成需登錄")
    if not user_has_feature(user, "ai_code_generate"):
        _feature_locked("ai_code_generate", "AI 策略代碼生成需 Pro+AI 方案", user)
    check_and_record_usage(user, "ai_query")


def gate_ai_param_suggest(user: User) -> None:
    """AI 參數調優建議（Pro+AI 方案）。"""
    if not user:
        raise HTTPException(status_code=401, detail="AI 參數建議需登錄")
    if not user_has_feature(user, "ai_param_suggest"):
        _feature_locked("ai_param_suggest", "AI 參數調優建議需 Pro+AI 方案", user)
    check_and_record_usage(user, "ai_query")


def gate_ai_market_report(user: User) -> None:
    """AI 市場晨報/日報（Pro+AI 方案）。"""
    if not user:
        raise HTTPException(status_code=401, detail="AI 市場報告需登錄")
    if not user_has_feature(user, "ai_market_report"):
        _feature_locked("ai_market_report", "AI 市場晨報需 Pro+AI 方案", user)


def gate_walkforward(user: User) -> None:
    """Walk-Forward 分析（Pro 方案）。"""
    if not user:
        raise HTTPException(status_code=401, detail="Walk-Forward 分析需登錄")
    if not user_has_feature(user, "walkforward"):
        _feature_locked("walkforward", "Walk-Forward 分析需 Pro 方案", user)
    check_and_record_usage(user, "walkforward")


def gate_monte_carlo(user: User) -> None:
    """蒙特卡羅模擬（Pro 方案）。"""
    if not user:
        raise HTTPException(status_code=401, detail="蒙特卡羅模擬需登錄")
    if not user_has_feature(user, "monte_carlo"):
        _feature_locked("monte_carlo", "蒙特卡羅模擬需 Pro 方案", user)
    check_and_record_usage(user, "monte_carlo")


def gate_full_report(user: User) -> None:
    """全面回測報告（Pro 方案）。"""
    if not user:
        raise HTTPException(status_code=401, detail="全面回測報告需登錄")
    if not user_has_feature(user, "full_report"):
        _feature_locked("full_report", "全面回測報告需 Pro 方案", user)
    check_and_record_usage(user, "full_report")


def gate_signal_ranking(user: User) -> None:
    """信號排名（Pro 方案）。"""
    if not user:
        raise HTTPException(status_code=401, detail="信號排名需登錄")
    if not user_has_feature(user, "signal_ranking"):
        _feature_locked("signal_ranking", "信號排名需 Pro 方案", user)
    check_and_record_usage(user, "signal_ranking")


def gate_risk_pipeline(user: User) -> None:
    """風控管道（Institutional 方案）。"""
    if not user:
        raise HTTPException(status_code=401, detail="風控管道需登錄")
    if not user_has_feature(user, "risk_pipeline"):
        _feature_locked("risk_pipeline", "風控管道需 Institutional 方案", user)


def gate_correlation_monitor(user: User) -> None:
    """策略相關性監控（Institutional 方案）。"""
    if not user:
        raise HTTPException(status_code=401, detail="相關性監控需登錄")
    if not user_has_feature(user, "correlation_monitor"):
        _feature_locked(
            "correlation_monitor", "策略相關性監控需 Institutional 方案", user
        )


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


def gate_concurrent_tasks(user: User) -> None:
    """限制同時進行中的任務數（優先使用 Redis 跨進程計數，降級到本進程記憶體）。"""
    from src.core import task_manager as tm

    cap = plan_definition(effective_plan_id(user)).limits.concurrent_tasks

    # 優先使用 Redis 跨進程計數（多 worker 部署下準確）
    try:
        from src.core import task_store

        if task_store.is_available():
            n = task_store.count_active_by_user(user.id)
            if n >= cap:
                raise HTTPException(
                    429,
                    detail={
                        "code": "quota_exceeded",
                        "message": f"同時進行中的任務已達上限（{cap} 個），請稍後或升級方案",
                        "used": n,
                        "limit": cap,
                        "upgrade_url": "/app#/pricing",
                    },
                )
            return
    except HTTPException:
        raise
    except Exception:
        pass

    # 降級：本進程記憶體計數
    active_status = (tm.STATUS_PENDING, tm.STATUS_RUNNING, tm.STATUS_RETRYING)
    with tm._lock:
        n = sum(
            1
            for t in tm._tasks.values()
            if t.get("user_id") == user.id and t.get("status") in active_status
        )
    if n >= cap:
        raise HTTPException(
            429,
            detail={
                "code": "quota_exceeded",
                "message": f"同時進行中的任務已達上限（{cap} 個），請稍後或升級方案",
                "used": n,
                "limit": cap,
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
    gate_concurrent_tasks(user)
    check_and_record_usage(user, "portfolio")


def check_quota(user: User, metric: str) -> None:
    """配額不足時拋 429（檢查後由調用方 record_usage）。"""
    from src.config import settings

    if not settings.billing_quota_enforce:
        return
    plan = plan_definition(effective_plan_id(user))
    usage = usage_snapshot(user.id)
    limits = plan.limits
    checks = {
        "backtest": (usage["backtests_today"], limits.daily_backtests, "回測"),
        "portfolio": (
            usage["portfolio_runs_today"],
            limits.daily_portfolio_runs,
            "組合回測",
        ),
        "optimize": (
            usage["optimize_runs_today"],
            limits.daily_optimize_runs,
            "參數優化",
        ),
        "ai_query": (usage["ai_queries_today"], limits.daily_ai_queries, "AI 問答"),
        "walkforward": (
            usage["walkforward_today"],
            limits.daily_walkforward,
            "Walk-Forward",
        ),
        "monte_carlo": (
            usage["monte_carlo_today"],
            limits.daily_monte_carlo,
            "蒙特卡羅",
        ),
        "signal_ranking": (
            usage["signal_ranking_today"],
            limits.daily_signal_ranking,
            "信號排名",
        ),
        "full_report": (
            usage["full_report_today"],
            limits.daily_full_report,
            "全面報告",
        ),
    }
    key = metric if metric in checks else "backtest"
    used, cap, label = checks[key]
    if cap <= 0:
        raise HTTPException(
            403,
            detail={
                "code": "plan_required",
                "message": f"當前方案不包含{label}功能，請升級方案",
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
            # 根據 feature 判斷需要哪個方案
            pro_ai_features = {
                "ai_strategy_recommend",
                "ai_code_generate",
                "ai_param_suggest",
                "ai_market_report",
            }
            inst_features = {
                "risk_pipeline",
                "correlation_monitor",
                "signal_arbitration",
                "rest_api_access",
                "team_seats",
            }
            if feature in inst_features:
                need = "institutional"
            elif feature in pro_ai_features:
                need = "pro_ai"
            else:
                need = "pro"
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


def set_user_plan(
    user_id: int, plan_id: str, *, status: str = "active", expires_at: str | None = None
) -> None:
    plan_id = (plan_id or "free").lower()
    if plan_id not in _VALID_PLAN_IDS:
        raise ValueError("無效方案")
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT settings FROM users WHERE id = ?", (user_id,)
        ).fetchone()
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
