"""
加密貨幣 API 測試 — mock 外部行情，覆蓋新路徑與相容路由。
"""
import pytest
from unittest.mock import patch

from src.core.crypto.service import CryptoDisabledError, CryptoService


SAMPLE_TICKER = {
    "symbol": "BTCUSDT",
    "name": "比特幣",
    "price": 65000.0,
    "change_pct": 2.5,
    "high": 66000.0,
    "low": 64000.0,
    "volume": 1000.0,
    "quote_volume": 65000000.0,
    "market": "crypto",
}


class TestCryptoService:
    def test_get_realtime_mock(self):
        with patch("src.core.crypto.service.get_crypto_realtime", return_value=SAMPLE_TICKER), \
             patch("src.core.crypto.service.get_crypto_symbols", return_value={"BTCUSDT": "比特幣"}):
            data = CryptoService().get_realtime(["BTCUSDT"])
        assert len(data) == 1
        assert data[0]["symbol"] == "BTCUSDT"

    def test_disabled_raises(self):
        with patch("src.config.settings.crypto_enabled", False):
            with pytest.raises(CryptoDisabledError):
                CryptoService().get_realtime()


class TestCryptoAPI:
    def test_crypto_realtime(self, client):
        with patch(
            "src.core.crypto.service.CryptoService.get_realtime",
            return_value=[SAMPLE_TICKER],
        ):
            resp = client.get("/api/crypto/realtime?symbols=BTCUSDT")
        assert resp.status_code == 200
        body = resp.json()
        assert body["market"] == "crypto"
        assert len(body["data"]) == 1

    def test_crypto_symbols(self, client):
        resp = client.get("/api/crypto/symbols")
        assert resp.status_code == 200
        assert "BTCUSDT" in resp.json().get("symbols", {})

    def test_crypto_kline_mock(self, client):
        import pandas as pd

        df = pd.DataFrame([
            {"date": "2026-05-01", "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "volume": 10.0, "amount": 0.0},
        ])
        with patch("src.core.crypto.service.download_crypto_kline", return_value=df):
            resp = client.get("/api/crypto/kline?symbol=BTCUSDT&days=7")
        assert resp.status_code == 200
        assert resp.json()["total"] == 1

    def test_markets_crypto_realtime_compat(self, client):
        with patch(
            "src.core.crypto.service.CryptoService.get_realtime",
            return_value=[SAMPLE_TICKER],
        ):
            resp = client.get("/api/markets/crypto/realtime")
        assert resp.status_code == 200
        assert resp.json()["market"] == "crypto"

    def test_markets_crypto_kline_compat(self, client):
        import pandas as pd

        df = pd.DataFrame([
            {"date": "2026-05-01", "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "volume": 10.0, "amount": 0.0},
        ])
        with patch("src.core.crypto.service.download_crypto_kline", return_value=df):
            resp = client.get("/api/markets/crypto/kline?symbol=ETHUSDT&days=30")
        assert resp.status_code == 200
        assert resp.json()["symbol"] == "ETHUSDT"
