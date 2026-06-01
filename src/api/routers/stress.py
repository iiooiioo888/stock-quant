"""
壓力測試 API — 蒙特卡洛模擬、歷史極端行情重放、VaR/CVaR
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from src.core.auth import require_auth
from src.models.user import User
from src.utils.logger import logger

router = APIRouter()


@router.get("/api/stress/scenarios")
async def stress_scenarios():
    """列出所有歷史極端行情場景。"""
    from src.core.stress_test import list_scenarios
    return {"success": True, "scenarios": list_scenarios()}


@router.post("/api/stress/replay")
async def stress_replay(body: dict, user: User = Depends(require_auth)):
    """
    歷史極端行情重放壓力測試。

    body:
        returns: list[float] — 策略歷史日收益率序列
        scenario_id: str — 場景 ID（可選，不填則測試所有場景）
        initial_value: float — 初始價值（默認 100000）
    """
    from src.core.stress_test import replay_extreme_scenario, replay_all_scenarios

    returns = body.get("returns") or []
    if not returns:
        raise HTTPException(400, "請提供策略收益序列 (returns)")

    scenario_id = body.get("scenario_id")
    initial_value = body.get("initial_value", 100000.0)

    if scenario_id:
        try:
            result = replay_extreme_scenario(returns, scenario_id, initial_value)
            return {"success": True, "result": result}
        except ValueError as e:
            raise HTTPException(400, str(e))

    results = replay_all_scenarios(returns, initial_value)
    return {"success": True, "results": results}


@router.post("/api/stress/var")
async def stress_var(body: dict, user: User = Depends(require_auth)):
    """
    VaR/CVaR 壓力測試。

    body:
        returns: list[float] — 日收益率序列
        confidence_levels: list[float] — 置信水平（可選）
        holding_periods: list[int] — 持有期天數（可選）
    """
    from src.core.stress_test import var_stress_test

    returns = body.get("returns") or []
    if not returns:
        raise HTTPException(400, "請提供收益率序列 (returns)")

    confidence_levels = body.get("confidence_levels")
    holding_periods = body.get("holding_periods")

    result = var_stress_test(returns, confidence_levels, holding_periods)
    if "error" in result:
        raise HTTPException(400, result["error"])

    return {"success": True, "result": result}