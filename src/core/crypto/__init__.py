"""
加密貨幣數據包 — Binance / CoinGecko / Twelve Data 多源降級。

REST 與下載任務均通過 CryptoService 或本模組 re-export 訪問。
"""
from src.core.crypto.client import (
    CRYPTO_SYMBOLS,
    download_crypto_kline,
    get_crypto_multi_realtime,
    get_crypto_realtime,
    get_crypto_symbols,
)
from src.core.crypto.service import CryptoDisabledError, CryptoService, get_crypto_service

__all__ = [
    "CRYPTO_SYMBOLS",
    "CryptoDisabledError",
    "CryptoService",
    "download_crypto_kline",
    "get_crypto_multi_realtime",
    "get_crypto_realtime",
    "get_crypto_symbols",
    "get_crypto_service",
]
