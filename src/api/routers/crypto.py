"""
加密貨幣行情 API — 獨立子系統路由。

端點：
- GET  /api/crypto/symbols           — 支持的交易對
- GET  /api/crypto/realtime          — 實時行情（WS 優先 + REST 降級）
- GET  /api/crypto/kline             — K 線數據（含 WS 實時聚合）
- GET  /api/crypto/indicators        — 完整技術指標
- GET  /api/crypto/microstructure    — 微結構分析
- GET  /api/crypto/alerts            — 活躍告警
- GET  /api/crypto/alert-history     — 告警歷史
- GET  /api/crypto/alert-rules       — 告警規則
- GET  /api/crypto/ws/status         — WS 連接狀態
- POST /api/crypto/ws/subscribe      — 動態訂閱
- POST /api/crypto/ws/unsubscribe    — 取消訂閱
- POST /api/crypto/alerts/config     — 更新告警配置
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional

from src.core.crypto.service import CryptoDisabledError, get_crypto_service

router = APIRouter(tags=["crypto"])


def _svc():
    return get_crypto_service()


def _handle_disabled(exc: CryptoDisabledError):
    raise HTTPException(status_code=503, detail=str(exc))


# ── 請求模型 ──────────────────────────────────────────────────

class SubscribeRequest(BaseModel):
    symbols: list[str]


class AlertConfigRequest(BaseModel):
    rsi_overbought: Optional[float] = None
    rsi_oversold: Optional[float] = None
    price_change_pct: Optional[float] = None
    volume_surge_multiplier: Optional[float] = None
    large_order_usd: Optional[float] = None
    default_cooldown_sec: Optional[int] = None


# ── 原有端點（向後兼容） ──────────────────────────────────────

@router.get("/api/crypto/symbols")
async def api_crypto_symbols():
    """支持的加密交易對。"""
    try:
        symbols = _svc().list_symbols()
        return {"symbols": symbols, "total": len(symbols)}
    except CryptoDisabledError as e:
        _handle_disabled(e)


@router.get("/api/crypto/realtime")
async def api_crypto_realtime(symbols: str = Query(None, description="逗號分隔，留空用 watchlist")):
    """批量實時行情（WS 快照優先，REST 降級）。"""
    try:
        sym_list = symbols.split(",") if symbols else None
        data = _svc().get_realtime(sym_list)
        return {"market": "crypto", "data": data, "total": len(data)}
    except CryptoDisabledError as e:
        _handle_disabled(e)


@router.get("/api/crypto/kline")
async def api_crypto_kline(
    symbol: str = "BTCUSDT",
    days: int = Query(30, ge=1, le=365),
    interval: str = Query("1d", description="K 線週期：1m/5m/15m/1h/1d"),
):
    """K 線數據（含 WS 實時聚合短週期）。"""
    try:
        return _svc().get_kline(symbol=symbol, days=days, interval=interval)
    except CryptoDisabledError as e:
        _handle_disabled(e)
    except Exception as e:
        raise HTTPException(500, str(e))


# ── 新增端點：技術指標 ────────────────────────────────────────

@router.get("/api/crypto/indicators")
async def api_crypto_indicators(
    symbol: str = "BTCUSDT",
    days: int = Query(90, ge=7, le=365),
):
    """
    計算完整技術指標。
    
    包含：RSI、MACD、EMA(9/21/55/200)、Bollinger Bands、ATR、
    Supertrend、Ichimoku、Stochastic RSI、Williams %R、CCI、
    MFI、OBV、VWAP、Keltner Channel、波動率百分位。
    """
    try:
        return _svc().get_indicators(symbol=symbol, days=days)
    except CryptoDisabledError as e:
        _handle_disabled(e)
    except Exception as e:
        raise HTTPException(500, str(e))


# ── 新增端點：微結構分析 ──────────────────────────────────────

@router.get("/api/crypto/microstructure")
async def api_crypto_microstructure(
    symbol: str = "BTCUSDT",
):
    """
    市場微結構分析（需 WS 數據）。
    
    包含：買賣壓力比、大單偵測、淨流入/流出、成交密度、
    盤口 Spread、深度不平衡、支撐/阻力偵測、實現波動率。
    """
    try:
        return _svc().get_microstructure(symbol=symbol)
    except CryptoDisabledError as e:
        _handle_disabled(e)
    except Exception as e:
        raise HTTPException(500, str(e))


# ── 新增端點：告警 ────────────────────────────────────────────

@router.get("/api/crypto/alerts")
async def api_crypto_alerts():
    """活躍告警列表。"""
    try:
        alerts = _svc().get_alerts()
        return {"alerts": alerts, "total": len(alerts)}
    except CryptoDisabledError as e:
        _handle_disabled(e)


@router.get("/api/crypto/alert-history")
async def api_crypto_alert_history(
    symbol: str = Query(None, description="交易對篩選"),
    limit: int = Query(50, ge=1, le=500),
):
    """告警歷史記錄。"""
    try:
        history = _svc().get_alert_history(symbol=symbol, limit=limit)
        return {"history": history, "total": len(history)}
    except CryptoDisabledError as e:
        _handle_disabled(e)


@router.get("/api/crypto/alert-rules")
async def api_crypto_alert_rules(
    symbol: str = Query(None, description="交易對篩選"),
):
    """告警規則列表。"""
    try:
        rules = _svc().get_alert_rules(symbol=symbol)
        return {"rules": rules, "total": len(rules)}
    except CryptoDisabledError as e:
        _handle_disabled(e)


@router.post("/api/crypto/alerts/config")
async def api_crypto_alert_config(req: AlertConfigRequest):
    """更新告警閾值配置。"""
    try:
        config = {k: v for k, v in req.model_dump().items() if v is not None}
        result = _svc().update_alert_config(config)
        return {"success": True, "config": result}
    except CryptoDisabledError as e:
        _handle_disabled(e)
    except Exception as e:
        raise HTTPException(500, str(e))


# ── 新增端點：WebSocket 管理 ──────────────────────────────────

@router.get("/api/crypto/ws/status")
async def api_crypto_ws_status():
    """WebSocket 連接狀態。"""
    try:
        return _svc().get_ws_status()
    except CryptoDisabledError as e:
        _handle_disabled(e)


@router.post("/api/crypto/ws/subscribe")
async def api_crypto_ws_subscribe(req: SubscribeRequest):
    """動態訂閱新交易對。"""
    try:
        result = await _svc().subscribe(req.symbols)
        return {"success": True, **result}
    except CryptoDisabledError as e:
        _handle_disabled(e)
    except Exception as e:
        raise HTTPException(500, str(e))


@router.post("/api/crypto/ws/unsubscribe")
async def api_crypto_ws_unsubscribe(req: SubscribeRequest):
    """取消訂閱交易對。"""
    try:
        result = await _svc().unsubscribe(req.symbols)
        return {"success": True, **result}
    except CryptoDisabledError as e:
        _handle_disabled(e)
    except Exception as e:
        raise HTTPException(500, str(e))

# ============================================================
# 自定義分析指數端點
# ============================================================

@router.get("/api/crypto/indices")
async def crypto_custom_indices():
    """獲取所有自定義分析指數"""
    from src.core.crypto.custom_indices import get_all_custom_indices
    return get_all_custom_indices()


@router.get("/api/crypto/indices/{index_name}")
async def crypto_custom_index(index_name: str):
    """按名稱獲取單個自定義指數"""
    from src.core.crypto.custom_indices import get_index_by_name
    result = get_index_by_name(index_name)
    if "error" in result:
        raise HTTPException(404, result["error"])
    return result
