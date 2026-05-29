"""risk 路由（P5 從 app.py 拆分）。"""
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


@router.post("/api/risk/position-size")
async def risk_position_size(body: dict):
    """計算倉位大小 — 支持多種倉位計算方法"""
    from src.core.risk_manager import PositionSizer, calculate_atr

    capital = body.get("capital", 100000)
    method = body.get("method", "atr")  # atr / fixed / kelly / volatility / drawdown
    max_risk = body.get("max_risk_per_trade", 0.02)

    sizer = PositionSizer(total_capital=capital, max_risk_per_trade=max_risk)

    try:
        if method == "fixed":
            fraction = body.get("fraction", 0.1)
            result_value = sizer.fixed_fraction(fraction)
            return {
                "success": True,
                "method": "固定比例",
                "position_value": round(result_value, 2),
                "fraction": fraction,
            }

        elif method == "atr":
            atr = body.get("atr", 0)
            code = body.get("code")
            # 如果未直接提供 ATR，嘗試從股票數據計算
            if atr <= 0 and code:
                atr = calculate_atr(code)
            if atr <= 0:
                raise HTTPException(400, "請提供 ATR 值或股票代碼")

            risk_multiplier = body.get("risk_multiplier", 1.0)
            shares = sizer.atr_based(atr, risk_multiplier)
            position_value = shares * body.get("price", atr * 30)  # 估算金額
            return {
                "success": True,
                "method": "ATR 倉位",
                "shares": shares,
                "atr": atr,
                "risk_multiplier": risk_multiplier,
                "estimated_value": round(position_value, 2),
            }

        elif method == "kelly":
            win_rate = body.get("win_rate", 0.5)
            avg_win = body.get("avg_win", 1)
            avg_loss = body.get("avg_loss", 1)
            result_value = sizer.kelly_position(win_rate, avg_win, avg_loss)
            return {
                "success": True,
                "method": "Kelly 公式",
                "position_value": round(result_value, 2),
                "win_rate": win_rate,
                "avg_win": avg_win,
                "avg_loss": avg_loss,
            }

        elif method == "volatility":
            target_vol = body.get("target_vol", 0.15)
            current_vol = body.get("current_vol", 0.20)
            current_position = body.get("current_position", capital * 0.5)
            result_value = sizer.volatility_target(target_vol, current_vol, current_position)
            return {
                "success": True,
                "method": "波動率目標",
                "position_value": round(result_value, 2),
                "target_vol": target_vol,
                "current_vol": current_vol,
            }

        elif method == "drawdown":
            current_dd = body.get("current_dd_pct", 0)
            base_size = body.get("base_size", capital * 0.1)
            result_value = sizer.drawdown_adjusted(current_dd, base_size)
            return {
                "success": True,
                "method": "回撤調整",
                "position_value": round(result_value, 2),
                "current_dd_pct": current_dd,
            }

        else:
            raise HTTPException(400, f"未知方法: {method}，可選: atr, fixed, kelly, volatility, drawdown")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"倉位計算失敗: {e}")
        raise HTTPException(500, str(e))




@router.post("/api/risk/budget-check")
async def risk_budget_check(body: dict):
    """風險預算檢查 — 檢查持倉風險是否超限"""
    from src.core.risk_manager import RiskBudget

    max_portfolio_risk = body.get("max_portfolio_risk", 0.15)
    max_single_risk = body.get("max_single_risk", 0.05)
    positions = body.get("positions", [])

    budget = RiskBudget(max_portfolio_risk=max_portfolio_risk, max_single_risk=max_single_risk)

    try:
        # 組合風險預算
        portfolio_result = budget.portfolio_risk_budget(positions)

        # 單個持倉檢查
        total_value = sum(p.get("value", 0) for p in positions)
        position_checks = []
        for p in positions:
            check = budget.check_position(
                position_value=p.get("value", 0),
                total_value=total_value,
                position_vol=p.get("vol", 0),
            )
            check["code"] = p.get("code", "未知")
            position_checks.append(check)

        # 再平衡建議
        rebalance = budget.suggest_rebalance(positions)

        return {
            "success": True,
            "portfolio": portfolio_result,
            "position_checks": position_checks,
            "rebalance_suggestions": rebalance,
        }

    except Exception as e:
        logger.error(f"風險預算檢查失敗: {e}")
        raise HTTPException(500, str(e))




@router.post("/api/risk/drawdown-protect")
async def risk_drawdown_protect(body: dict):
    """回撤保護 — 分析淨值序列的回撤狀態和熔斷點"""
    from src.core.risk_manager import DrawdownProtector, drawdown_circuit_breaker

    mode = body.get("mode", "monitor")  # monitor / circuit_breaker

    try:
        if mode == "monitor":
            # 實時監控模式：傳入一系列淨值
            nav_values = body.get("nav_values", [])
            max_dd = body.get("max_drawdown_pct", 20.0)
            warning_dd = body.get("warning_pct", 10.0)

            protector = DrawdownProtector(max_drawdown_pct=max_dd, warning_pct=warning_dd)
            results = []
            for v in nav_values:
                result = protector.update(v)
                results.append(result)

            return {
                "success": True,
                "mode": "monitor",
                "results": results,
                "final_state": results[-1] if results else None,
            }

        elif mode == "circuit_breaker":
            # 熔斷分析模式：傳入完整淨值和日期序列
            nav = body.get("nav", [])
            dates = body.get("dates", [])
            max_dd = body.get("max_dd", 20.0)

            if not nav or not dates:
                raise HTTPException(400, "請提供 nav 和 dates 序列")

            result = drawdown_circuit_breaker(nav, dates, max_dd)
            return {"success": True, "mode": "circuit_breaker", "result": result}

        else:
            raise HTTPException(400, f"未知模式: {mode}，可選: monitor, circuit_breaker")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"回撤保護分析失敗: {e}")
        raise HTTPException(500, str(e))


# ====== 信號增強 API ======



@router.post("/api/risk-pipeline/run")
async def run_risk_pipeline_api(body: dict = None):
    """運行信號→風控→交易管道"""
    from src.core.risk_pipeline import run_signal_pipeline

    if body is None:
        body = {}

    try:
        result = run_signal_pipeline(
            codes=body.get("codes"),
            total_capital=body.get("total_capital"),
            sizing_method=body.get("sizing_method", "atr"),
        )
        return {"success": True, "result": result}
    except Exception as e:
        logger.error(f"風控管道失敗: {e}")
        raise HTTPException(500, str(e))




@router.get("/api/risk-pipeline/state")
async def get_risk_pipeline_state():
    """獲取風控管道狀態"""
    from src.core.risk_pipeline import RiskPipeline
    pipeline = RiskPipeline()
    return {"success": True, "state": pipeline.get_state()}


# ====== 數據質量 API ======



