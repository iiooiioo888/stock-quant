"""data_ops 路由（P5 從 app.py 拆分）。"""
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


@router.get("/api/screener/stocks")
async def get_stock_list_api(market: str = "all"):
    """獲取可用股票列表"""
    from src.core.screener import get_stock_list

    try:
        stocks = get_stock_list(market=market)
        return {"stocks": stocks, "total": len(stocks)}
    except Exception as e:
        logger.error(f"獲取股票列表失敗: {e}")
        raise HTTPException(500, str(e))




@router.post("/api/screener/screen")
async def screen_stocks_api(body: dict):
    """股票篩選"""
    from src.core.screener import screen_stocks

    filters = body.get("filters", {})
    codes = body.get("codes")

    try:
        results = screen_stocks(codes=codes, filters=filters)
        return {"success": True, "results": results, "total": len(results)}
    except Exception as e:
        logger.error(f"篩選失敗: {e}")
        raise HTTPException(500, str(e))


# ====== 基準對比 ======



@router.get("/api/benchmark")
async def get_benchmark(start: str = None, end: str = None):
    """獲取滬深300基準數據"""
    from src.core.benchmark import get_benchmark_returns

    try:
        result = get_benchmark_returns(start_date=start, end_date=end)
        return {"success": True, "result": result}
    except Exception as e:
        logger.error(f"基準數據獲取失敗: {e}")
        raise HTTPException(500, str(e))




@router.post("/api/benchmark/compare")
async def compare_benchmark_api(body: dict):
    """回測結果與基準對比"""
    from src.core.benchmark import compare_with_benchmark
    from src.core.backtest import run_backtest

    code = body.get("code")
    strategy = body.get("strategy", "dual_ma")
    params = body.get("params")

    try:
        bt_result = run_backtest(code, strategy_name=strategy, params=params)
        comparison = compare_with_benchmark(bt_result)
        return {"success": True, "comparison": comparison}
    except Exception as e:
        logger.error(f"基準對比失敗: {e}")
        raise HTTPException(500, str(e))


# ====== 實時信號 ======

def _fetch_current_signals():
    from src.core.signals import SignalEngine, compute_and_push_signals

    engine = SignalEngine()
    return compute_and_push_signals(engine, list(settings.watchlist))




@router.get("/api/export/backtest/{result_id}")
async def export_backtest(
    result_id: int,
    format: str = "csv",
    user: User = Depends(require_auth),
):
    """導出回測結果"""
    from src.core.entitlements import gate_data_export
    from src.core.export import export_backtest_csv, export_backtest_json

    gate_data_export(user)

    if format == "json":
        content = export_backtest_json(result_id)
        from fastapi.responses import Response
        return Response(content=content, media_type="application/json")
    else:
        content = export_backtest_csv(result_id)
        from fastapi.responses import Response
        return Response(
            content=content,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=backtest_{result_id}.csv"}
        )




@router.get("/api/export/trades")
async def export_trades(
    code: str,
    strategy: str,
    format: str = "csv",
    user: User = Depends(require_auth),
):
    """導出交易明細"""
    from src.core.entitlements import gate_data_export
    from src.core.export import export_trades_csv, export_trades_json

    gate_data_export(user)

    if format == "json":
        content = export_trades_json(code, strategy)
        from fastapi.responses import Response
        return Response(content=content, media_type="application/json")
    else:
        content = export_trades_csv(code, strategy)
        from fastapi.responses import Response
        return Response(
            content=content,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=trades_{code}_{strategy}.csv"}
        )


# ====== 有效前沿 ======



@router.get("/api/realtime")
async def get_realtime(codes: str = None):
    """獲取實時行情"""
    from src.core.realtime import fetch_realtime

    if codes:
        code_list = codes.split(",")
    else:
        code_list = settings.watchlist

    try:
        df = fetch_realtime(code_list)
        if df.empty:
            return {"quotes": [], "message": "無數據（可能非交易時段）"}
        return {"quotes": df.to_dict(orient="records")}
    except Exception as e:
        logger.error(f"實時行情失敗: {e}")
        raise HTTPException(500, str(e))


# ====== 風險管理 API ======



@router.get("/api/data-quality/check")
async def data_quality_check(code: str = None, severity: str = None):
    """數據質量校驗"""
    from src.core.data_quality import validate_stock_data, validate_all

    try:
        if code:
            issues = validate_stock_data(code)
            return {"success": True, "code": code, "issues": [i.to_dict() for i in issues], "total": len(issues)}
        else:
            report = validate_all(severity_filter=severity)
            return {"success": True, **report}
    except Exception as e:
        logger.error(f"數據質量校驗失敗: {e}")
        raise HTTPException(500, str(e))




@router.post("/api/data-quality/repair")
async def data_quality_repair(code: str, dry_run: bool = True):
    """自動修復數據問題"""
    from src.core.data_quality import repair_data

    try:
        repairs = repair_data(code, dry_run=dry_run)
        return {"success": True, "code": code, "dry_run": dry_run, "repairs": repairs}
    except Exception as e:
        logger.error(f"數據修復失敗: {e}")
        raise HTTPException(500, str(e))




@router.get("/api/data-quality/splits")
async def detect_splits(code: str):
    """檢測除權除息事件"""
    from src.core.data_quality import detect_split_adjustments

    try:
        events = detect_split_adjustments(code)
        return {"success": True, "code": code, "events": events, "total": len(events)}
    except Exception as e:
        logger.error(f"除權檢測失敗: {e}")
        raise HTTPException(500, str(e))


# ====== 模擬交易 API ======



