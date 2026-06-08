"""report_backtest 路由（P5 從 app.py 拆分）。"""

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


@router.post("/api/backtest/trade-analysis")
async def backtest_trade_analysis(body: dict):
    """交易深度分析 — 連勝連敗、盈虧比、期望收益等"""
    from src.core.backtest import run_backtest, trade_analysis

    code = body.get("code", "")
    strategy = body.get("strategy", "dual_ma")
    params = body.get("params")

    if not code:
        raise HTTPException(400, "請提供股票代碼")

    try:
        bt_result = run_backtest(code, strategy_name=strategy, params=params)
        analysis = trade_analysis(bt_result.get("trade_details", []))
        return {
            "success": True,
            "code": code,
            "strategy": strategy,
            "trade_analysis": analysis,
        }
    except Exception as e:
        logger.error(f"交易分析失敗: {e}")
        raise HTTPException(500, str(e))


@router.post("/api/backtest/monte-carlo")
async def backtest_monte_carlo(body: dict):
    """蒙特卡羅模擬 — 基於歷史收益率的概率分析"""
    from src.core.backtest import run_backtest, monte_carlo_simulation

    code = body.get("code", "")
    strategy = body.get("strategy", "dual_ma")
    params = body.get("params")
    n_simulations = body.get("n_simulations", 1000)
    days = body.get("days", 252)

    if not code:
        raise HTTPException(400, "請提供股票代碼")

    try:
        bt_result = run_backtest(code, strategy_name=strategy, params=params)
        mc = monte_carlo_simulation(
            bt_result.get("daily_returns", []), n_simulations=n_simulations, days=days
        )
        return {"success": True, "code": code, "strategy": strategy, "monte_carlo": mc}
    except Exception as e:
        logger.error(f"蒙特卡羅模擬失敗: {e}")
        raise HTTPException(500, str(e))


@router.post("/api/backtest/rolling-metrics")
async def backtest_rolling_metrics(body: dict):
    """滾動指標 — 滾動夏普、Sortino、波動率時間序列"""
    from src.core.backtest import run_backtest, rolling_metrics

    code = body.get("code", "")
    strategy = body.get("strategy", "dual_ma")
    params = body.get("params")
    window = body.get("window", 60)

    if not code:
        raise HTTPException(400, "請提供股票代碼")

    try:
        bt_result = run_backtest(code, strategy_name=strategy, params=params)
        rm = rolling_metrics(
            bt_result.get("daily_returns", []),
            bt_result.get("dates", []),
            window=window,
        )
        return {
            "success": True,
            "code": code,
            "strategy": strategy,
            "rolling_metrics": rm,
        }
    except Exception as e:
        logger.error(f"滾動指標失敗: {e}")
        raise HTTPException(500, str(e))


@router.post("/api/report/full")
async def report_full(body: dict):
    """全面回測報告 — 包含所有分析維度"""
    from src.core.report_enhanced import generate_full_report

    code = body.get("code", "")
    strategy = body.get("strategy", "dual_ma")
    params = body.get("params")

    if not code:
        raise HTTPException(400, "請提供股票代碼")

    try:
        report = generate_full_report(code, strategy, params=params)
        return {"success": True, "report": report}
    except Exception as e:
        logger.error(f"全面報告失敗: {e}")
        raise HTTPException(500, str(e))


@router.post("/api/report/comparison")
async def report_comparison(body: dict):
    """多股對比報告 — 同一策略在多隻股票上的表現對比"""
    from src.core.report_enhanced import generate_comparison_report

    codes = body.get("codes", [])
    strategy = body.get("strategy", "dual_ma")

    if not codes:
        raise HTTPException(400, "請提供股票代碼列表")

    try:
        report = generate_comparison_report(codes, strategy)
        return {"success": True, "report": report}
    except Exception as e:
        logger.error(f"對比報告失敗: {e}")
        raise HTTPException(500, str(e))


@router.post("/api/report/strategy")
async def report_strategy(body: dict):
    """策略分析報告 — 一個策略在所有 watchlist 股票上的表現"""
    from src.core.report_enhanced import generate_strategy_report

    strategy = body.get("strategy", "")
    codes = body.get("codes")

    if not strategy:
        raise HTTPException(400, "請提供策略名稱")

    try:
        report = generate_strategy_report(strategy, codes=codes)
        return {"success": True, "report": report}
    except Exception as e:
        logger.error(f"策略報告失敗: {e}")
        raise HTTPException(500, str(e))


# ====== 風控管道 API ======
