"""
加密貨幣業務服務層 — REST 共用入口。
"""
from typing import Optional

from src.config import settings
from src.core.crypto.client import (
    download_crypto_kline,
    get_crypto_multi_realtime,
    get_crypto_realtime,
    get_crypto_symbols,
)
from src.utils.logger import logger

_service_instance: Optional["CryptoService"] = None


class CryptoDisabledError(RuntimeError):
    """功能關閉時拋出。"""


class CryptoService:
    """加密貨幣只讀數據服務。"""

    def _ensure_enabled(self) -> None:
        if not settings.crypto_enabled:
            raise CryptoDisabledError("加密貨幣功能已關閉（SQ_CRYPTO_ENABLED=false）")

    def list_symbols(self) -> dict:
        self._ensure_enabled()
        return get_crypto_symbols()

    def get_watchlist(self) -> list[str]:
        self._ensure_enabled()
        return list(settings.crypto_watchlist)

    def get_realtime(self, symbols: list[str] = None) -> list[dict]:
        self._ensure_enabled()
        sym_list = symbols or list(settings.crypto_watchlist)
        return get_crypto_multi_realtime(sym_list)

    def get_realtime_one(self, symbol: str) -> dict:
        self._ensure_enabled()
        return get_crypto_realtime(symbol)

    def get_kline(
        self,
        symbol: str = "BTCUSDT",
        days: int = 30,
        interval: str = "1d",
    ) -> dict:
        self._ensure_enabled()
        from datetime import datetime, timedelta

        start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        try:
            df = download_crypto_kline(symbol=symbol, interval=interval, start_date=start)
            if df.empty:
                return {"symbol": symbol, "klines": [], "message": "無數據", "total": 0}
            klines = df.to_dict(orient="records")
            return {"symbol": symbol, "klines": klines, "total": len(klines)}
        except Exception as e:
            logger.error(f"加密 K 線失敗 {symbol}: {e}")
            raise


def get_crypto_service() -> CryptoService:
    global _service_instance
    if _service_instance is None:
        _service_instance = CryptoService()
    return _service_instance
