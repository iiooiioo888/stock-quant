"""
加密貨幣行情 API — 獨立子系統路由。
"""
from fastapi import APIRouter, HTTPException, Query

from src.core.crypto.service import CryptoDisabledError, get_crypto_service

router = APIRouter(tags=["crypto"])


def _svc():
    return get_crypto_service()


def _handle_disabled(exc: CryptoDisabledError):
    raise HTTPException(status_code=503, detail=str(exc))


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
    """批量實時行情。"""
    try:
        sym_list = symbols.split(",") if symbols else None
        data = _svc().get_realtime(sym_list)
        return {"market": "crypto", "data": data}
    except CryptoDisabledError as e:
        _handle_disabled(e)


@router.get("/api/crypto/kline")
async def api_crypto_kline(
    symbol: str = "BTCUSDT",
    days: int = Query(30, ge=1, le=365),
):
    """K 線數據。"""
    try:
        return _svc().get_kline(symbol=symbol, days=days)
    except CryptoDisabledError as e:
        _handle_disabled(e)
    except Exception as e:
        raise HTTPException(500, str(e))
