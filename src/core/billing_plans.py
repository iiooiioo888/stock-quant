"""
訂閱方案定義 — Free / Pro / Pro+AI / Institutional

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
    daily_ai_queries: int = 0
    daily_walkforward: int = 0
    daily_monte_carlo: int = 0
    daily_signal_ranking: int = 0
    daily_full_report: int = 0
    max_watchlist: int = 20
    max_custom_strategies: int = 0
    max_paper_sessions: int = 1
    max_allocation_positions: int = 10
    concurrent_tasks: int = 2
    realtime_ws_symbols: int = 0
    export_row_limit: int = 0


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
    # === 基礎 ===
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
    # === AI 進階 ===
    "ai_strategy_recommend": "AI 策略智能推薦",
    "ai_report_interpret": "AI 回測報告深度解讀",
    "ai_code_generate": "AI 策略代碼生成",
    "ai_param_suggest": "AI 參數調優建議",
    "ai_market_report": "AI 市場晨報/日報",
    # === 高級分析 ===
    "walkforward": "Walk-Forward 分析",
    "monte_carlo": "蒙特卡羅模擬",
    "efficient_frontier": "有效前沿分析",
    "degradation_detect": "策略衰退檢測",
    "signal_backtest": "信號回測驗證",
    "signal_heatmap": "信號熱力圖",
    "signal_ranking": "信號排名",
    "full_report": "全面回測報告",
    # === 風控 ===
    "risk_position_calc": "進階倉位計算（ATR/Kelly/波動率/回撤）",
    "risk_budget_check": "風險預算檢查",
    "risk_drawdown_protect": "回撤保護分析",
    "risk_pipeline": "風控管道（信號→倉位→交易）",
    "correlation_monitor": "策略相關性監控",
    "signal_arbitration": "多策略信號仲裁",
    # === 數據 & 策略 ===
    "minute_kline": "分鐘 K 線",
    "data_quality_repair": "數據質量修復",
    "custom_strategies": "自定義策略",
    "sandbox_backtest": "沙箱回測",
    "strategy_leaderboard": "策略排行榜參與",
    "paper_trading": "模擬交易",
    "realtime_ws_symbols": "實時信號推送",
    "rest_api_access": "REST API 訪問",
    "signal_history": "歷史信號查詢",
    "strategy_browse": "瀏覽策略庫",
    "position_calc_basic": "基礎倉位計算",
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
            daily_ai_queries=0,
            daily_walkforward=0,
            daily_monte_carlo=0,
            daily_signal_ranking=0,
            daily_full_report=0,
            max_watchlist=15,
            max_custom_strategies=0,
            max_paper_sessions=1,
            max_allocation_positions=5,
            concurrent_tasks=1,
            realtime_ws_symbols=0,
            export_row_limit=0,
        ),
        features=frozenset({
            "backtest_basic",
            "portfolio_basic",
            "signal_history",
            "strategy_browse",
            "position_calc_basic",
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
            daily_ai_queries=20,
            daily_walkforward=5,
            daily_monte_carlo=10,
            daily_signal_ranking=10,
            daily_full_report=3,
            max_watchlist=80,
            max_custom_strategies=5,
            max_paper_sessions=5,
            max_allocation_positions=40,
            concurrent_tasks=4,
            realtime_ws_symbols=5,
            export_row_limit=1000,
        ),
        features=frozenset({
            # 基礎
            "backtest_basic",
            "backtest_advanced",
            "compare_multimarket",
            "portfolio_basic",
            "portfolio_advanced",
            "allocation_cloud",
            "assets_pro",
            "task_priority",
            "data_export",
            # AI 基礎
            "ai_assistant",
            "ai_report_interpret",
            # 高級分析
            "walkforward",
            "monte_carlo",
            "efficient_frontier",
            "degradation_detect",
            "signal_backtest",
            "signal_heatmap",
            "signal_ranking",
            "full_report",
            # 風控
            "risk_position_calc",
            "risk_budget_check",
            "risk_drawdown_protect",
            # 數據 & 策略
            "minute_kline",
            "data_quality_repair",
            "custom_strategies",
            "sandbox_backtest",
            "strategy_leaderboard",
            "paper_trading",
            "signal_history",
            "strategy_browse",
            "position_calc_basic",
        }),
        highlight=True,
    ),
    "pro_ai": PlanDefinition(
        id="pro_ai",
        name="Pro + AI",
        tagline="AI 驅動的量化研究",
        price_monthly=44,
        price_yearly=440,
        limits=PlanLimits(
            daily_backtests=80,
            daily_portfolio_runs=30,
            daily_optimize_runs=10,
            daily_ai_queries=100,
            daily_walkforward=10,
            daily_monte_carlo=20,
            daily_signal_ranking=50,
            daily_full_report=10,
            max_watchlist=120,
            max_custom_strategies=10,
            max_paper_sessions=10,
            max_allocation_positions=60,
            concurrent_tasks=6,
            realtime_ws_symbols=20,
            export_row_limit=10000,
        ),
        features=frozenset({
            # 繼承 Pro 全部
            "backtest_basic",
            "backtest_advanced",
            "compare_multimarket",
            "portfolio_basic",
            "portfolio_advanced",
            "allocation_cloud",
            "assets_pro",
            "task_priority",
            "data_export",
            # AI 全部
            "ai_assistant",
            "ai_report_interpret",
            "ai_strategy_recommend",
            "ai_code_generate",
            "ai_param_suggest",
            "ai_market_report",
            # 高級分析
            "walkforward",
            "monte_carlo",
            "efficient_frontier",
            "degradation_detect",
            "signal_backtest",
            "signal_heatmap",
            "signal_ranking",
            "full_report",
            # 風控
            "risk_position_calc",
            "risk_budget_check",
            "risk_drawdown_protect",
            # 數據 & 策略
            "minute_kline",
            "data_quality_repair",
            "custom_strategies",
            "sandbox_backtest",
            "strategy_leaderboard",
            "paper_trading",
            "signal_history",
            "strategy_browse",
            "position_calc_basic",
        }),
    ),
    "institutional": PlanDefinition(
        id="institutional",
        name="Institutional",
        tagline="團隊、合規與定制部署",
        price_monthly=199,
        price_yearly=1990,
        limits=PlanLimits(
            daily_backtests=9999,
            daily_portfolio_runs=9999,
            daily_optimize_runs=9999,
            daily_ai_queries=9999,
            daily_walkforward=9999,
            daily_monte_carlo=9999,
            daily_signal_ranking=9999,
            daily_full_report=9999,
            max_watchlist=500,
            max_custom_strategies=9999,
            max_paper_sessions=999,
            max_allocation_positions=200,
            concurrent_tasks=12,
            realtime_ws_symbols=9999,
            export_row_limit=0,
        ),
        features=frozenset(FEATURE_LABELS.keys()),
        contact_sales=True,
    ),
}

PLAN_ORDER = ["free", "pro", "pro_ai", "institutional"]


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
                "daily_ai_queries": p.limits.daily_ai_queries,
                "daily_walkforward": p.limits.daily_walkforward,
                "daily_monte_carlo": p.limits.daily_monte_carlo,
                "daily_signal_ranking": p.limits.daily_signal_ranking,
                "daily_full_report": p.limits.daily_full_report,
                "max_watchlist": p.limits.max_watchlist,
                "max_custom_strategies": p.limits.max_custom_strategies,
                "max_paper_sessions": p.limits.max_paper_sessions,
                "max_allocation_positions": p.limits.max_allocation_positions,
                "concurrent_tasks": p.limits.concurrent_tasks,
                "realtime_ws_symbols": p.limits.realtime_ws_symbols,
                "export_row_limit": p.limits.export_row_limit,
            },
            "features": [
                {"id": f, "label": FEATURE_LABELS.get(f, f)}
                for f in sorted(p.features)
            ],
        })
    return out