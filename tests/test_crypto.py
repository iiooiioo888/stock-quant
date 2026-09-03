"""加密貨幣子系統單元測試（不打外網）。"""

from unittest.mock import patch

import pandas as pd
import pytest

from src.core.crypto.client import get_crypto_symbols
from src.core.crypto.service import CryptoDisabledError, CryptoService


def test_crypto_symbols_contains_majors():
    symbols = get_crypto_symbols()
    assert isinstance(symbols, dict)
    assert "BTCUSDT" in symbols
    assert "ETHUSDT" in symbols


def test_crypto_service_disabled_raises():
    with patch("src.config.settings.crypto_enabled", False):
        with pytest.raises(CryptoDisabledError):
            CryptoService().get_realtime()


def test_crypto_service_realtime_mock():
    ticker = {
        "symbol": "BTCUSDT",
        "name": "比特幣",
        "price": 65000.0,
        "change_pct": 1.2,
        "market": "crypto",
    }
    with patch(
        "src.core.crypto.service.get_crypto_realtime", return_value=ticker
    ), patch(
        "src.core.crypto.service.get_crypto_symbols",
        return_value={"BTCUSDT": "比特幣"},
    ):
        data = CryptoService().get_realtime(["BTCUSDT"])
    assert data[0]["symbol"] == "BTCUSDT"


def test_crypto_kline_columns_passthrough():
    df = pd.DataFrame(
        [
            {
                "date": "2026-01-01",
                "open": 1,
                "high": 2,
                "low": 0.5,
                "close": 1.5,
                "volume": 10,
            }
        ]
    )
    svc = CryptoService()
    with patch.object(CryptoService, "_ensure_ws_components", lambda self: None), patch(
        "src.core.crypto.service.download_crypto_kline", return_value=df
    ):
        out = svc.get_kline("BTCUSDT", days=7, interval="1d")
    assert out["total"] == 1
    assert out["symbol"] == "BTCUSDT"
