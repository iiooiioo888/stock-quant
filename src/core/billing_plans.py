"""
訂閱方案定義 — Free / Pro / Institutional

支付通道（Stripe 等）可後接；方案與權益為單一真相來源。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class PlanLimits:
    daily_backtests: int = 5
    daily_portfolio_runs: int = 3
    daily_optimize_runs: int = 1
    max_watchlist: int = 20
    max_allocation_positions: int = 10
    concurrent_tasks: int = 2


@dataclass(frozen=True)
class PlanDefinition:
    id: str
    name: str
    tagline: str
    price_monthly: float  # 展示用 USD；0=免費
    price_yearly: float
    currency: str = "USD"
    limits: PlanLimits = field(default_factory=PlanLimits)
    features: frozenset[str] = field(default_factory=frozenset)
    highlight: bool = False
    contact_sales: bool = False


FEATURE_LABELS: dict[str, str] = {
    "backtest_basic": "基礎回測與 K 線",
    "backtest_advanced": "進階風控參數回測",
    "compare_multimarket": "多市場多股對比",
    "portfolio_basic": "組合回測（等權/基礎）",
    "portfolio_advanced": "風險平價 / MVO / 有效前沿",
    "allocation_cloud": "雲端個人配置同步",
    "assets_pro": "資產庫主題包與詳情",
    "ai_assistant": "AI 投研助手",
    "task_priority": "任務優先隊列",
    "data_export": "結果導出與 API",
    "team_seats": "團隊席位與 SSO",
}

PLANS: dict[str, PlanDefinition] = {
    "free": PlanDefinition(
        id="free",
        name="Free",
        tagline="個人學習與試用",
        price_monthly=0,
        price_yearly=0,
        limits=PlanLimits(
            daily_backtests=8,
            daily_portfolio_runs=2,
            daily_optimize_runs=0,
            max_watchlist=15,
            max_allocation_positions=5,
            concurrent_tasks=1,
        ),
        features=frozenset({
            "backtest_basic",
            "portfolio_basic",
        }),
    ),
    "pro": PlanDefinition(
        id="pro",
        name="Pro",
        tagline="活躍交易者與進階研究",
        price_monthly=29,
        price_yearly=290,
        limits=PlanLimits(
            daily_backtests=80,
            daily_portfolio_runs=30,
            daily_optimize_runs=10,
            max_watchlist=80,
            max_allocation_positions=40,
            concurrent_tasks=4,
        ),
        features=frozenset({
            "backtest_basic",
            "backtest_advanced",
            "compare_multimarket",
            "portfolio_basic",
            "portfolio_advanced",
            "allocation_cloud",
            "assets_pro",
            "ai_assistant",
            "task_priority",
            "data_export",
        }),
        highlight=True,
    ),
    "institutional": PlanDefinition(
        id="institutional",
        name="Institutional",
        tagline="團隊、合規與定制部署",
        price_monthly=0,
        price_yearly=0,
        limits=PlanLimits(
            daily_backtests=9999,
            daily_portfolio_runs=9999,
            daily_optimize_runs=9999,
            max_watchlist=500,
            max_allocation_positions=200,
            concurrent_tasks=12,
        ),
        features=frozenset(FEATURE_LABELS.keys()),
        contact_sales=True,
    ),
}

PLAN_ORDER = ["free", "pro", "institutional"]


def plan_definition(plan_id: str) -> PlanDefinition:
    pid = (plan_id or "free").strip().lower()
    return PLANS.get(pid, PLANS["free"])


def plans_public_payload() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for pid in PLAN_ORDER:
        p = PLANS[pid]
        out.append({
            "id": p.id,
            "name": p.name,
            "tagline": p.tagline,
            "price_monthly": p.price_monthly,
            "price_yearly": p.price_yearly,
            "currency": p.currency,
            "highlight": p.highlight,
            "contact_sales": p.contact_sales,
            "limits": {
                "daily_backtests": p.limits.daily_backtests,
                "daily_portfolio_runs": p.limits.daily_portfolio_runs,
                "daily_optimize_runs": p.limits.daily_optimize_runs,
                "max_watchlist": p.limits.max_watchlist,
                "max_allocation_positions": p.limits.max_allocation_positions,
                "concurrent_tasks": p.limits.concurrent_tasks,
            },
            "features": [
                {"id": f, "label": FEATURE_LABELS.get(f, f)}
                for f in sorted(p.features)
            ],
        })
    return out
