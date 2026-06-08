"""
加密貨幣數據包 — Binance REST + WebSocket 串流 + 技術指標 + 微結構 + 告警。

模塊：
- client.py        — REST 數據拉取（Binance / CoinGecko / CoinCap / Twelve Data）
- ws_client.py     — 幣安 WebSocket Streams 異步客戶端
- stream_manager.py — 串流管理器 + K 線聚合 + 快照緩存
- indicators.py    — 加密貨幣專用技術指標引擎（30+ 指標）
- microstructure.py — 市場微結構分析（買賣壓力/大單/盤口/波動率）
- alerts.py        — 多維度告警引擎（RSI/MACD/BB/大單/漲跌幅）
- service.py       — 統一服務層（WS 優先 + REST 降級）
"""

from src.core.crypto.alerts import AlertEvent, AlertRule, CryptoAlertEngine
from src.core.crypto.client import (
    CRYPTO_SYMBOLS,
    download_crypto_kline,
    get_crypto_multi_realtime,
    get_crypto_realtime,
    get_crypto_symbols,
)
from src.core.crypto.indicators import compute_all_crypto_indicators
from src.core.crypto.microstructure import CryptoMicrostructureAnalyzer
from src.core.crypto.service import (
    CryptoDisabledError,
    CryptoService,
    get_crypto_service,
)
from src.core.crypto.stream_manager import CryptoSnapshot, CryptoStreamManager
from src.core.crypto.ws_client import BinanceStreamClient

__all__ = [
    # 原有
    "CRYPTO_SYMBOLS",
    "CryptoDisabledError",
    "CryptoService",
    "download_crypto_kline",
    "get_crypto_multi_realtime",
    "get_crypto_realtime",
    "get_crypto_symbols",
    "get_crypto_service",
    # WebSocket
    "BinanceStreamClient",
    "CryptoStreamManager",
    "CryptoSnapshot",
    # 分析引擎
    "compute_all_crypto_indicators",
    "CryptoMicrostructureAnalyzer",
    # 告警
    "CryptoAlertEngine",
    "AlertRule",
    "AlertEvent",
]
