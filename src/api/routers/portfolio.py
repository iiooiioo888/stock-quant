"""portfolio 路由（P5 從 app.py 拆分）。"""

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


@router.get("/api/portfolio/presets")
async def get_portfolio_presets():
    """獲取預設組合模板"""
    return {"presets": settings.portfolio_presets}


@router.post("/api/portfolio/preset/{preset_name}")
async def run_preset_portfolio(
    preset_name: str,
    cash: float = None,
    user: User = Depends(require_auth),
):
    """用預設模板跑組合回測（異步任務，納入任務面板）"""
    from src.core.portfolio import run_portfolio

    gate_portfolio_task(user, advanced=False)
    preset = settings.portfolio_presets.get(preset_name)
    if not preset:
        raise HTTPException(
            404,
            f"預設組合不存在: {preset_name}，可選: {list(settings.portfolio_presets.keys())}",
        )

    allocations = preset["allocations"]
    rebalance = preset.get("rebalance", "none")
    rebalance_freq_days = preset.get("rebalance_freq_days", 20)
    display = preset.get("name", preset_name)

    def _work():
        result = run_portfolio(
            allocations=allocations,
            rebalance=rebalance,
            rebalance_freq_days=rebalance_freq_days,
            cash=cash,
        )
        if not result or not result.get("portfolio"):
            raise ValueError(
                "所有子策略回測失敗，請先在「數據中心」下載預設股票日線數據（演示模式啟動時會自動下載）",
            )
        return result

    d = dispatch_portfolio_async(
        "preset",
        allocations,
        _work,
        task_extra={
            "preset_name": preset_name,
            "preset_display": display,
            "rebalance": rebalance,
            "rebalance_freq_days": rebalance_freq_days,
            "cash": cash,
        },
        title=f"組合回測 · 預設「{display}」",
    )
    d["preset"] = display
    return d


# ====== 進階組合功能 ======


@router.post("/api/portfolio/dynamic")
async def run_dynamic_portfolio(body: dict, user: User = Depends(require_auth)):
    """動態權重組合回測 — 根據滾動夏普自動調整子策略權重"""
    from src.core.portfolio import dynamic_weight_portfolio

    gate_portfolio_task(user, advanced=True)
    allocations = body.get("allocations", [])
    rolling_window = body.get("rolling_window", 60)
    rebalance_freq_days = body.get("rebalance_freq_days", 20)
    cash = body.get("cash")

    if not allocations:
        raise HTTPException(400, "請提供 allocations")

    def _work():
        return dynamic_weight_portfolio(
            allocations=allocations,
            rolling_window=rolling_window,
            rebalance_freq_days=rebalance_freq_days,
            cash=cash,
        )

    return dispatch_portfolio_async(
        "dynamic",
        allocations,
        _work,
        task_extra={
            "rolling_window": rolling_window,
            "rebalance_freq_days": rebalance_freq_days,
            "cash": cash,
        },
        title="組合回測 · 動態權重",
    )


@router.post("/api/portfolio/kelly")
async def run_kelly_criterion(body: dict, user: User = Depends(require_auth)):
    """Kelly 公式計算最優倉位比例"""
    from src.core.portfolio import kelly_criterion

    gate_portfolio_task(user, advanced=True)
    allocations = body.get("allocations", [])
    cash = body.get("cash")
    fraction_limit = body.get("fraction_limit", 0.5)

    if not allocations:
        raise HTTPException(400, "請提供 allocations")

    def _work():
        return kelly_criterion(
            allocations=allocations,
            cash=cash,
            fraction_limit=fraction_limit,
        )

    return dispatch_portfolio_async(
        "kelly",
        allocations,
        _work,
        task_extra={"cash": cash, "fraction_limit": fraction_limit},
        title="組合回測 · Kelly",
    )


@router.post("/api/portfolio/degradation")
async def run_degradation_detection(body: dict, user: User = Depends(require_auth)):
    """策略衰退檢測 — 檢測子策略是否連續跑輸基準"""
    from src.core.portfolio import detect_degradation

    gate_portfolio_task(user, advanced=True)
    allocations = body.get("allocations", [])
    lookback_days = body.get("lookback_days", 30)
    threshold_days = body.get("threshold_days", 5)
    weight_reduction = body.get("weight_reduction", 0.5)
    cash = body.get("cash")

    if not allocations:
        raise HTTPException(400, "請提供 allocations")

    def _work():
        return detect_degradation(
            allocations=allocations,
            lookback_days=lookback_days,
            threshold_days=threshold_days,
            weight_reduction=weight_reduction,
            cash=cash,
        )

    return dispatch_portfolio_async(
        "degradation",
        allocations,
        _work,
        task_extra={
            "lookback_days": lookback_days,
            "threshold_days": threshold_days,
            "weight_reduction": weight_reduction,
            "cash": cash,
        },
        title="組合回測 · 衰退檢測",
    )


@router.post("/api/portfolio/arbitrate")
async def run_signal_arbitration(body: dict, user: User = Depends(require_auth)):
    """信號衝突仲裁 — 多策略矛盾信號加權投票"""
    from src.core.portfolio import arbitrate_signals

    gate_portfolio_task(user, advanced=True)
    strategy_signals = body.get("strategy_signals", [])
    allocations = body.get("allocations")
    rolling_window = body.get("rolling_window", 60)
    cash = body.get("cash")

    if not strategy_signals:
        raise HTTPException(400, "請提供 strategy_signals")

    def _work():
        return arbitrate_signals(
            strategy_signals=strategy_signals,
            allocations=allocations,
            rolling_window=rolling_window,
            cash=cash,
        )

    return dispatch_portfolio_async(
        "arbitrate",
        allocations or [],
        _work,
        task_extra={
            "strategy_signals": strategy_signals,
            "rolling_window": rolling_window,
            "cash": cash,
        },
        title="組合回測 · 信號仲裁",
        count_override=len(strategy_signals),
    )


@router.post("/api/portfolio/risk-parity")
async def run_risk_parity(body: dict, user: User = Depends(require_auth)):
    """風險平價組合 — 每個策略對總風險貢獻相等"""
    from src.core.portfolio import risk_parity_portfolio

    gate_portfolio_task(user, advanced=True)
    allocations = body.get("allocations", [])
    cash = body.get("cash")

    if not allocations:
        raise HTTPException(400, "請提供 allocations")

    def _work():
        return risk_parity_portfolio(allocations=allocations, cash=cash)

    return dispatch_portfolio_async(
        "risk-parity",
        allocations,
        _work,
        task_extra={"cash": cash},
        title="組合回測 · 風險平價",
    )


@router.post("/api/portfolio/mvo")
async def run_mean_variance(body: dict, user: User = Depends(require_auth)):
    """均值-方差優化 — Markowitz 最優權重"""
    from src.core.portfolio import mean_variance_optimize

    gate_portfolio_task(user, advanced=True)
    allocations = body.get("allocations", [])
    objective = body.get("objective", "max_sharpe")
    cash = body.get("cash")
    n_simulations = body.get("n_simulations", 5000)

    if not allocations:
        raise HTTPException(400, "請提供 allocations")

    def _work():
        return mean_variance_optimize(
            allocations=allocations,
            objective=objective,
            cash=cash,
            n_simulations=n_simulations,
        )

    return dispatch_portfolio_async(
        "mvo",
        allocations,
        _work,
        task_extra={
            "objective": objective,
            "cash": cash,
            "n_simulations": n_simulations,
        },
        title="組合回測 · 均值方差(MVO)",
    )


@router.post("/api/portfolio/vol-target")
async def run_vol_targeting(body: dict, user: User = Depends(require_auth)):
    """波動率目標組合 — 根據已實現波動率動態調整倉位"""
    from src.core.portfolio import volatility_targeting

    gate_portfolio_task(user, advanced=True)
    allocations = body.get("allocations", [])
    target_vol = body.get("target_vol", 0.15)
    lookback_days = body.get("lookback_days", 20)
    cash = body.get("cash")

    if not allocations:
        raise HTTPException(400, "請提供 allocations")

    def _work():
        return volatility_targeting(
            allocations=allocations,
            target_vol=target_vol,
            lookback_days=lookback_days,
            cash=cash,
        )

    return dispatch_portfolio_async(
        "vol-target",
        allocations,
        _work,
        task_extra={
            "target_vol": target_vol,
            "lookback_days": lookback_days,
            "cash": cash,
        },
        title="組合回測 · 波動目標",
    )


@router.post("/api/portfolio/max-diversification")
async def run_max_diversification(body: dict):
    """最大分散化組合 — 最大化分散化比率"""
    from src.core.portfolio import max_diversification_portfolio

    allocations = body.get("allocations", [])
    cash = body.get("cash")
    n_simulations = body.get("n_simulations", 5000)

    if not allocations:
        raise HTTPException(400, "請提供 allocations")

    def _work():
        return max_diversification_portfolio(
            allocations=allocations,
            cash=cash,
            n_simulations=n_simulations,
        )

    return dispatch_portfolio_async(
        "max-diversification",
        allocations,
        _work,
        task_extra={"cash": cash, "n_simulations": n_simulations},
        title="組合回測 · 最大分散化",
    )


@router.post("/api/portfolio/anti-correlation")
async def run_anti_correlation(body: dict):
    """反相關組合 — 最小化策略間總相關性"""
    from src.core.portfolio import anti_correlation_portfolio

    allocations = body.get("allocations", [])
    cash = body.get("cash")
    n_simulations = body.get("n_simulations", 5000)

    if not allocations:
        raise HTTPException(400, "請提供 allocations")

    def _work():
        return anti_correlation_portfolio(
            allocations=allocations,
            cash=cash,
            n_simulations=n_simulations,
        )

    return dispatch_portfolio_async(
        "anti-correlation",
        allocations,
        _work,
        task_extra={"cash": cash, "n_simulations": n_simulations},
        title="組合回測 · 低相關",
    )


@router.post("/api/portfolio/regime-switch")
async def run_regime_switch(body: dict):
    """市場狀態切換組合 — 根據趨勢/波動狀態動態調整策略權重"""
    from src.core.portfolio import regime_switch_portfolio

    allocations = body.get("allocations", [])
    regime_method = body.get("regime_method", "volatility")
    lookback_days = body.get("lookback_days", 60)
    cash = body.get("cash")

    if not allocations:
        raise HTTPException(400, "請提供 allocations")

    def _work():
        return regime_switch_portfolio(
            allocations=allocations,
            regime_method=regime_method,
            lookback_days=lookback_days,
            cash=cash,
        )

    return dispatch_portfolio_async(
        "regime-switch",
        allocations,
        _work,
        task_extra={
            "regime_method": regime_method,
            "lookback_days": lookback_days,
            "cash": cash,
        },
        title="組合回測 · 狀態切換",
    )


@router.post("/api/portfolio/black-litterman")
async def run_black_litterman(body: dict):
    """Black-Litterman 模型 — 結合市場均衡收益與投資者觀點"""
    from src.core.portfolio import black_litterman_portfolio

    allocations = body.get("allocations", [])
    views = body.get("views", {})
    confidence = body.get("confidence", {})
    cash = body.get("cash")

    if not allocations:
        raise HTTPException(400, "請提供 allocations")
    if not views:
        raise HTTPException(400, "請提供 views（投資者觀點）")

    def _work():
        return black_litterman_portfolio(
            allocations=allocations,
            views=views,
            confidence=confidence,
            cash=cash,
        )

    return dispatch_portfolio_async(
        "black-litterman",
        allocations,
        _work,
        task_extra={"views": views, "confidence": confidence, "cash": cash},
        title="組合回測 · Black-Litterman",
    )


@router.post("/api/portfolio/hrp")
async def run_hrp(body: dict):
    """層次風險平價 (HRP) — 基於聚類的穩健資產配置"""
    from src.core.portfolio import hierarchical_risk_parity

    allocations = body.get("allocations", [])
    cash = body.get("cash")

    if not allocations:
        raise HTTPException(400, "請提供 allocations")

    def _work():
        return hierarchical_risk_parity(allocations=allocations, cash=cash)

    return dispatch_portfolio_async(
        "hrp",
        allocations,
        _work,
        task_extra={"cash": cash},
        title="組合回測 · HRP",
    )


@router.post("/api/portfolio/cvar-optimize")
async def run_cvar_optimize(body: dict):
    """CVaR 優化 — 最小化條件風險價值"""
    from src.core.portfolio import cvar_optimize

    allocations = body.get("allocations", [])
    alpha = body.get("alpha", 0.05)
    cash = body.get("cash")

    if not allocations:
        raise HTTPException(400, "請提供 allocations")

    def _work():
        return cvar_optimize(allocations=allocations, alpha=alpha, cash=cash)

    return dispatch_portfolio_async(
        "cvar-optimize",
        allocations,
        _work,
        task_extra={"alpha": alpha, "cash": cash},
        title="組合回測 · CVaR",
    )


@router.post("/api/portfolio/multi-timeframe")
async def run_multi_timeframe(body: dict):
    """多時間框架信號確認 — 多窗口投票確認交易信號"""
    from src.core.portfolio import multi_timeframe_signal

    allocations = body.get("allocations", [])
    windows = body.get("windows", [5, 20, 60])
    cash = body.get("cash")

    if not allocations:
        raise HTTPException(400, "請提供 allocations")

    def _work():
        return multi_timeframe_signal(
            allocations=allocations, windows=windows, cash=cash
        )

    return dispatch_portfolio_async(
        "multi-timeframe",
        allocations,
        _work,
        task_extra={"windows": windows, "cash": cash},
        title="組合回測 · 多週期",
    )


@router.post("/api/portfolio/dynamic-rebalance")
async def run_dynamic_rebalance(body: dict):
    """動態再平衡觸發 — 波動率和權重偏移驅動的再平衡"""
    from src.core.portfolio import dynamic_rebalance_trigger

    allocations = body.get("allocations", [])
    threshold_pct = body.get("threshold_pct", 5.0)
    vol_window = body.get("vol_window", 20)
    cash = body.get("cash")

    if not allocations:
        raise HTTPException(400, "請提供 allocations")

    def _work():
        return dynamic_rebalance_trigger(
            allocations=allocations,
            threshold_pct=threshold_pct,
            vol_window=vol_window,
            cash=cash,
        )

    return dispatch_portfolio_async(
        "dynamic-rebalance",
        allocations,
        _work,
        task_extra={
            "threshold_pct": threshold_pct,
            "vol_window": vol_window,
            "cash": cash,
        },
        title="組合回測 · 動態再平衡",
    )


@router.post("/api/portfolio/sector-limit")
async def run_sector_limit(body: dict):
    """板塊敞口限制 — 控制單板塊最大配置比例"""
    from src.core.portfolio import sector_exposure_limit

    allocations = body.get("allocations", [])
    max_sector_pct = body.get("max_sector_pct", 40.0)
    cash = body.get("cash")

    if not allocations:
        raise HTTPException(400, "請提供 allocations")

    def _work():
        return sector_exposure_limit(
            allocations=allocations,
            max_sector_pct=max_sector_pct,
            cash=cash,
        )

    return dispatch_portfolio_async(
        "sector-limit",
        allocations,
        _work,
        task_extra={"max_sector_pct": max_sector_pct, "cash": cash},
        title="組合回測 · 板塊限制",
    )


@router.post("/api/portfolio/voting")
async def run_voting_portfolio(body: dict):
    """投票式組合 — 多策略投票，>= min_votes 個同意才執行"""
    from src.core.portfolio import strategy_voting_portfolio

    allocations = body.get("allocations", [])
    min_votes = body.get("min_votes", 2)
    cash = body.get("cash")

    if not allocations:
        raise HTTPException(400, "請提供 allocations")

    def _work():
        return strategy_voting_portfolio(
            allocations=allocations,
            min_votes=min_votes,
            cash=cash,
        )

    return dispatch_portfolio_async(
        "voting",
        allocations,
        _work,
        task_extra={"min_votes": min_votes, "cash": cash},
        title="組合回測 · 投票式",
    )


@router.post("/api/portfolio/momentum-of-momentum")
async def run_momentum_of_momentum(body: dict):
    """動量的動量組合 — 二階動量加權，策略改善趨勢越好權重越高"""
    from src.core.portfolio import momentum_of_momentum

    allocations = body.get("allocations", [])
    lookback = body.get("lookback", 60)
    cash = body.get("cash")

    if not allocations:
        raise HTTPException(400, "請提供 allocations")

    def _work():
        return momentum_of_momentum(
            allocations=allocations,
            lookback=lookback,
            cash=cash,
        )

    return dispatch_portfolio_async(
        "momentum-of-momentum",
        allocations,
        _work,
        task_extra={"lookback": lookback, "cash": cash},
        title="組合回測 · 動量動量",
    )


@router.post("/api/portfolio/adaptive-regime")
async def run_adaptive_regime(body: dict):
    """自適應市場狀態組合 — 低波動加趨勢策略，高波動加均值回歸策略"""
    from src.core.portfolio import adaptive_regime_portfolio

    allocations = body.get("allocations", [])
    cash = body.get("cash")

    if not allocations:
        raise HTTPException(400, "請提供 allocations")

    def _work():
        return adaptive_regime_portfolio(
            allocations=allocations,
            cash=cash,
        )

    return dispatch_portfolio_async(
        "adaptive-regime",
        allocations,
        _work,
        task_extra={"cash": cash},
        title="組合回測 · 自適應狀態",
    )


# ====== 熱力圖 ======


@router.post("/api/portfolio/frontier")
async def run_portfolio_frontier(body: dict):
    """有效前沿分析"""
    from src.core.portfolio import efficient_frontier

    allocations = body.get("allocations", [])
    n_points = body.get("n_points", 20)

    if len(allocations) < 2:
        raise HTTPException(400, "至少需要 2 個子策略")

    def _work():
        return efficient_frontier(allocations=allocations, n_points=n_points)

    return dispatch_portfolio_async(
        "frontier",
        allocations,
        _work,
        task_extra={"n_points": n_points},
        title="組合回測 · 有效前沿",
    )


# ====== 策略開發框架 ======
