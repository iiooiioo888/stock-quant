"""
加密貨幣 WebSocket + 技術指標 + 微結構 + 告警測試。

覆蓋：
- BinanceStreamClient 消息解析與驗證
- CryptoStreamManager 快照與 K 線聚合
- 技術指標計算正確性
- 微結構分析
- 告警引擎觸發與冷卻
- API 端點 mock 測試
"""
import json
import time
from unittest.mock import patch, AsyncMock

import numpy as np
import pytest


# ── BinanceStreamClient 測試 ──────────────────────────────────

class TestWSClientParsing:
    """測試消息解析。"""

    def test_parse_trade(self):
        from src.core.crypto.ws_client import BinanceStreamClient
        client = BinanceStreamClient()
        data = {
            "e": "trade",
            "E": int(time.time() * 1000),
            "s": "BTCUSDT",
            "p": "65000.50",
            "q": "0.1",
            "T": int(time.time() * 1000),
            "m": True,
            "t": 12345,
        }
        result = client._parse_trade(data)
        assert result is not None
        assert result["symbol"] == "BTCUSDT"
        assert result["price"] == 65000.50
        assert result["qty"] == 0.1
        assert result["is_buyer_maker"] is True
        assert result["trade_id"] == 12345

    def test_parse_kline(self):
        from src.core.crypto.ws_client import BinanceStreamClient
        client = BinanceStreamClient()
        data = {
            "e": "kline",
            "E": int(time.time() * 1000),
            "s": "BTCUSDT",
            "k": {
                "t": 1000, "T": 2000, "i": "1m",
                "o": "64000", "h": "65500", "l": "63500", "c": "65000",
                "v": "100.5", "q": "6500000", "n": 50, "x": False,
            },
        }
        result = client._parse_kline(data)
        assert result is not None
        assert result["symbol"] == "BTCUSDT"
        assert result["interval"] == "1m"
        assert result["open"] == 64000.0
        assert result["close"] == 65000.0
        assert result["is_closed"] is False

    def test_parse_ticker(self):
        from src.core.crypto.ws_client import BinanceStreamClient
        client = BinanceStreamClient()
        data = {
            "e": "24hrTicker",
            "E": int(time.time() * 1000),
            "s": "BTCUSDT",
            "c": "65000", "o": "64000", "h": "66000", "l": "63000",
            "v": "1000", "q": "65000000",
            "p": "1000", "P": "1.56", "w": "64500", "n": 5000,
        }
        result = client._parse_ticker(data)
        assert result is not None
        assert result["price"] == 65000.0
        assert result["change_pct"] == 1.56

    def test_parse_depth(self):
        from src.core.crypto.ws_client import BinanceStreamClient
        client = BinanceStreamClient()
        data = {
            "e": "depthUpdate",
            "E": int(time.time() * 1000),
            "s": "BTCUSDT",
            "b": [["64900", "1.5"], ["64800", "2.0"]],
            "a": [["65100", "1.2"], ["65200", "0.8"]],
        }
        result = client._parse_depth(data)
        assert result is not None
        assert result["best_bid"] == 64900.0
        assert result["best_ask"] == 65100.0
        assert result["spread"] == 200.0
        assert result["bid_total"] == 3.5
        assert result["ask_total"] == 2.0

    def test_validate_valid_trade(self):
        from src.core.crypto.ws_client import BinanceStreamClient
        client = BinanceStreamClient()
        data = {
            "e": "trade",
            "E": int(time.time() * 1000),
            "s": "BTCUSDT",
            "p": "65000",
            "q": "0.1",
            "T": int(time.time() * 1000),
        }
        assert client._validate_message(data) is True

    def test_validate_invalid_price(self):
        from src.core.crypto.ws_client import BinanceStreamClient
        client = BinanceStreamClient()
        data = {
            "e": "trade",
            "E": int(time.time() * 1000),
            "s": "BTCUSDT",
            "p": "0",
            "q": "0.1",
            "T": int(time.time() * 1000),
        }
        assert client._validate_message(data) is False

    def test_validate_stale_timestamp(self):
        from src.core.crypto.ws_client import BinanceStreamClient
        client = BinanceStreamClient()
        data = {
            "e": "trade",
            "E": int((time.time() - 30) * 1000),  # 30 秒前
            "s": "BTCUSDT",
            "p": "65000",
            "q": "0.1",
            "T": int(time.time() * 1000),
        }
        assert client._validate_message(data) is False

    def test_subscription_management(self):
        from src.core.crypto.ws_client import BinanceStreamClient
        client = BinanceStreamClient()
        new = client.add_subscription("BTCUSDT", stream_types=["trade", "ticker"])
        assert "btcusdt@trade" in new
        assert "btcusdt@ticker" in new
        assert len(client.subscriptions) == 2

        removed = client.remove_subscription("BTCUSDT")
        assert "btcusdt@trade" in removed
        assert len(client.subscriptions) == 0

    def test_kline_subscription(self):
        from src.core.crypto.ws_client import BinanceStreamClient
        client = BinanceStreamClient()
        new = client.add_subscription("BTCUSDT", stream_types=["kline"], kline_intervals=["1m", "5m"])
        assert "btcusdt@kline_1m" in new
        assert "btcusdt@kline_5m" in new

    def test_depth_subscription(self):
        from src.core.crypto.ws_client import BinanceStreamClient
        client = BinanceStreamClient()
        new = client.add_subscription("BTCUSDT", stream_types=["depth"])
        assert "btcusdt@depth@100ms" in new

    def test_get_status(self):
        from src.core.crypto.ws_client import BinanceStreamClient
        client = BinanceStreamClient()
        status = client.get_status()
        assert status["state"] == "idle"
        assert status["is_running"] is False
        assert status["total_messages"] == 0


# ── StreamManager 測試 ────────────────────────────────────────

class TestStreamManager:
    """測試串流管理器。"""

    @pytest.mark.asyncio
    async def test_on_trade_updates_snapshot(self):
        from src.core.crypto.stream_manager import CryptoStreamManager
        mgr = CryptoStreamManager()
        trade = {
            "symbol": "BTCUSDT",
            "price": 65000.0,
            "qty": 0.5,
            "quote_qty": 32500.0,
            "is_buyer_maker": False,
            "trade_time": int(time.time() * 1000),
            "timestamp": time.time(),
        }
        await mgr.on_trade(trade)
        snap = mgr.get_snapshot("BTCUSDT")
        assert snap is not None
        assert snap["price"] == 65000.0
        assert snap["buy_volume"] == 0.5
        assert snap["buy_count"] == 1

    @pytest.mark.asyncio
    async def test_on_ticker_updates_snapshot(self):
        from src.core.crypto.stream_manager import CryptoStreamManager
        mgr = CryptoStreamManager()
        ticker = {
            "symbol": "BTCUSDT",
            "price": 65000.0,
            "open": 64000.0,
            "high": 66000.0,
            "low": 63000.0,
            "volume": 1000.0,
            "quote_volume": 65000000.0,
            "change": 1000.0,
            "change_pct": 1.56,
            "trade_count": 5000,
        }
        await mgr.on_ticker(ticker)
        snap = mgr.get_snapshot("BTCUSDT")
        assert snap is not None
        assert snap["change_pct"] == 1.56
        assert snap["high"] == 66000.0

    @pytest.mark.asyncio
    async def test_trade_stats(self):
        from src.core.crypto.stream_manager import CryptoStreamManager
        mgr = CryptoStreamManager()

        # 模擬買入
        await mgr.on_trade({
            "symbol": "BTCUSDT", "price": 65000.0, "qty": 1.0,
            "is_buyer_maker": False, "timestamp": time.time(),
        })
        # 模擬賣出
        await mgr.on_trade({
            "symbol": "BTCUSDT", "price": 65100.0, "qty": 0.5,
            "is_buyer_maker": True, "timestamp": time.time(),
        })

        stats = mgr.get_trade_stats("BTCUSDT")
        assert stats["buy_volume"] == 1.0
        assert stats["sell_volume"] == 0.5
        assert stats["net_volume"] == 0.5

    def test_snapshot_to_dict(self):
        from src.core.crypto.stream_manager import CryptoSnapshot
        snap = CryptoSnapshot(symbol="BTCUSDT", price=65000.0, change_pct=2.5)
        d = snap.to_dict()
        assert d["symbol"] == "BTCUSDT"
        assert d["price"] == 65000.0
        assert d["market"] == "crypto"
        assert d["source"] == "binance_ws"

    def test_manager_stats(self):
        from src.core.crypto.stream_manager import CryptoStreamManager
        mgr = CryptoStreamManager()
        stats = mgr.get_manager_stats()
        assert stats["symbols_tracked"] == 0
        assert stats["total_trades_processed"] == 0


# ── 技術指標測試 ───────────────────────────────────────────────

class TestCryptoIndicators:
    """測試技術指標計算。"""

    def test_compute_ema(self):
        from src.core.crypto.indicators import compute_ema
        close = np.array([100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110], dtype=np.float64)
        ema = compute_ema(close, 5)
        assert not np.isnan(ema[-1])
        assert ema[-1] > 100

    def test_compute_bollinger_bands(self):
        from src.core.crypto.indicators import compute_bollinger_bands
        close = np.arange(100, 130, dtype=np.float64)
        upper, middle, lower = compute_bollinger_bands(close, 20, 2.0)
        assert not np.isnan(middle[-1])
        assert upper[-1] > middle[-1]
        assert lower[-1] < middle[-1]

    def test_compute_obv(self):
        from src.core.crypto.indicators import compute_obv
        close = np.array([10, 11, 10, 12, 11], dtype=np.float64)
        volume = np.array([100, 200, 150, 300, 100], dtype=np.float64)
        obv = compute_obv(close, volume)
        assert obv[-1] != 0

    def test_taker_buy_sell_ratio(self):
        from src.core.crypto.indicators import compute_taker_buy_sell_ratio
        trades = [
            {"qty": 1.0, "is_buyer_maker": False},  # buy
            {"qty": 0.5, "is_buyer_maker": True},    # sell
            {"qty": 2.0, "is_buyer_maker": False},   # buy
        ]
        result = compute_taker_buy_sell_ratio(trades)
        assert result["buy_volume"] == 3.0
        assert result["sell_volume"] == 0.5
        assert result["ratio"] == 6.0

    def test_detect_large_orders(self):
        from src.core.crypto.indicators import detect_large_orders
        trades = [
            {"price": 65000, "qty": 0.1, "quote_qty": 6500, "is_buyer_maker": False, "trade_time": 0},
            {"price": 65000, "qty": 0.1, "quote_qty": 6500, "is_buyer_maker": True, "trade_time": 0},
            {"price": 65000, "qty": 0.1, "quote_qty": 6500, "is_buyer_maker": False, "trade_time": 0},
            {"price": 65000, "qty": 5.0, "quote_qty": 325000, "is_buyer_maker": False, "trade_time": 0},  # 大單
        ]
        # multiplier×平均量：0.1×3 + 5.0 → 平均 1.325，×3 ≈ 3.98，5.0 為大單
        large = detect_large_orders(trades, multiplier=3.0)
        assert len(large) == 1
        assert large[0]["qty"] == 5.0

    def test_compute_all_crypto_indicators(self):
        from src.core.crypto.indicators import compute_all_crypto_indicators
        n = 100
        closes = np.random.uniform(60000, 70000, n)
        highs = closes + np.random.uniform(0, 500, n)
        lows = closes - np.random.uniform(0, 500, n)
        volumes = np.random.uniform(100, 1000, n)

        result = compute_all_crypto_indicators(closes, highs, lows, volumes)
        assert "rsi" in result
        assert "macd_line" in result
        assert "bb_upper" in result
        assert "atr" in result
        assert "obv" in result
        assert "volatility_percentile" in result

    def test_volatility_percentile(self):
        from src.core.crypto.indicators import compute_volatility_percentile
        # 創建收窄波動序列
        closes = np.concatenate([
            np.random.uniform(60000, 70000, 80),  # 高波動
            np.random.uniform(64000, 65000, 20),   # 低波動
        ])
        pct = compute_volatility_percentile(closes)
        assert 0 <= pct <= 100


# ── 微結構分析測試 ─────────────────────────────────────────────

class TestMicrostructure:
    """測試微結構分析。"""

    def test_analyze_trades(self):
        from src.core.crypto.microstructure import CryptoMicrostructureAnalyzer
        analyzer = CryptoMicrostructureAnalyzer()
        trades = [
            {"price": 65000, "qty": 0.1, "is_buyer_maker": False, "quote_qty": 6500, "timestamp": time.time()},
            {"price": 65100, "qty": 0.2, "is_buyer_maker": True, "quote_qty": 13020, "timestamp": time.time()},
            {"price": 65200, "qty": 0.3, "is_buyer_maker": False, "quote_qty": 19560, "timestamp": time.time()},
        ]
        result = analyzer.analyze_trades(trades)
        assert result["trade_count"] == 3
        assert result["buy_sell_pressure"]["buy_volume"] == 0.4
        assert result["buy_sell_pressure"]["sell_volume"] == 0.2

    def test_empty_trades(self):
        from src.core.crypto.microstructure import CryptoMicrostructureAnalyzer
        analyzer = CryptoMicrostructureAnalyzer()
        result = analyzer.analyze_trades([])
        assert result["trade_count"] == 0

    def test_analyze_depth(self):
        from src.core.crypto.microstructure import CryptoMicrostructureAnalyzer
        analyzer = CryptoMicrostructureAnalyzer()
        depth = {
            "bids": [[64900, 1.5], [64800, 2.0], [64700, 3.0]],
            "asks": [[65100, 1.0], [65200, 1.5], [65300, 2.0]],
        }
        result = analyzer.analyze_depth(depth)
        assert result["best_bid"] == 64900.0
        assert result["best_ask"] == 65100.0
        assert result["spread"] == 200.0
        assert "depth_imbalance" in result
        assert "support_levels" in result


# ── 告警引擎測試 ───────────────────────────────────────────────

class TestAlertEngine:
    """測試告警引擎。"""

    def test_create_default_rules(self):
        from src.core.crypto.alerts import CryptoAlertEngine
        engine = CryptoAlertEngine()
        rules = engine.create_default_rules("BTCUSDT")
        assert len(rules) == 8  # 8 條默認規則
        assert engine.get_rule_count() == 8

    def test_rsi_overbought_alert(self):
        from src.core.crypto.alerts import CryptoAlertEngine
        engine = CryptoAlertEngine(rsi_overbought=70.0)
        engine.create_default_rules("BTCUSDT")

        triggered = engine.evaluate(
            "BTCUSDT",
            indicators={"rsi": 75.0},
            snapshot={"price": 65000},
        )
        assert len(triggered) == 1
        assert "RSI 超買" in triggered[0].message

    def test_rsi_oversold_alert(self):
        from src.core.crypto.alerts import CryptoAlertEngine
        engine = CryptoAlertEngine(rsi_oversold=30.0)
        engine.create_default_rules("BTCUSDT")

        triggered = engine.evaluate(
            "BTCUSDT",
            indicators={"rsi": 25.0},
            snapshot={"price": 65000},
        )
        assert len(triggered) == 1
        assert "RSI 超賣" in triggered[0].message

    def test_cooldown_prevents_duplicate(self):
        from src.core.crypto.alerts import CryptoAlertEngine
        engine = CryptoAlertEngine(rsi_overbought=70.0, default_cooldown_sec=300)
        engine.create_default_rules("BTCUSDT")

        # 第一次觸發
        triggered1 = engine.evaluate("BTCUSDT", indicators={"rsi": 75.0}, snapshot={"price": 65000})
        assert len(triggered1) == 1

        # 冷卻期內不重複觸發
        triggered2 = engine.evaluate("BTCUSDT", indicators={"rsi": 80.0}, snapshot={"price": 66000})
        assert len(triggered2) == 0

    def test_price_change_alert(self):
        from src.core.crypto.alerts import CryptoAlertEngine
        engine = CryptoAlertEngine(price_change_pct=5.0)
        engine.create_default_rules("BTCUSDT")

        triggered = engine.evaluate("BTCUSDT", snapshot={"price": 65000, "change_pct": 8.0})
        assert any("漲幅" in e.message for e in triggered)

    def test_alert_history(self):
        from src.core.crypto.alerts import CryptoAlertEngine
        engine = CryptoAlertEngine()
        engine.create_default_rules("BTCUSDT")
        engine.evaluate("BTCUSDT", indicators={"rsi": 75.0}, snapshot={"price": 65000})

        history = engine.get_alert_history("BTCUSDT")
        assert len(history) >= 1

    def test_enable_disable_rule(self):
        from src.core.crypto.alerts import CryptoAlertEngine
        engine = CryptoAlertEngine()
        rules = engine.create_default_rules("BTCUSDT")

        engine.disable_rule(rules[0])
        assert engine.get_rules("BTCUSDT")[0]["enabled"] is False

        engine.enable_rule(rules[0])
        assert engine.get_rules("BTCUSDT")[0]["enabled"] is True

    def test_update_config(self):
        from src.core.crypto.alerts import CryptoAlertEngine
        engine = CryptoAlertEngine()
        engine.update_config({"rsi_overbought": 80.0, "rsi_oversold": 20.0})
        config = engine.get_config()
        assert config["rsi_overbought"] == 80.0
        assert config["rsi_oversold"] == 20.0

    def test_stats(self):
        from src.core.crypto.alerts import CryptoAlertEngine
        engine = CryptoAlertEngine()
        engine.create_default_rules("BTCUSDT")
        stats = engine.get_stats()
        assert stats["total_rules"] == 8
        assert stats["symbols_with_rules"] == 1


# ── API 端點測試 ───────────────────────────────────────────────

class TestCryptoAPIEndpoints:
    """測試 API 端點（mock 外部依賴）。"""

    def test_crypto_symbols(self, client):
        resp = client.get("/api/crypto/symbols")
        assert resp.status_code == 200
        assert "BTCUSDT" in resp.json().get("symbols", {})

    def test_crypto_realtime_mock(self, client):
        with patch(
            "src.core.crypto.service.get_crypto_realtime",
            return_value={"symbol": "BTCUSDT", "price": 65000.0, "market": "crypto"},
        ):
            resp = client.get("/api/crypto/realtime?symbols=BTCUSDT")
        assert resp.status_code == 200
        body = resp.json()
        assert body["market"] == "crypto"

    def test_crypto_ws_status(self, client):
        resp = client.get("/api/crypto/ws/status")
        assert resp.status_code == 200
        body = resp.json()
        assert "ws_enabled" in body

    def test_crypto_alerts_endpoint(self, client):
        resp = client.get("/api/crypto/alerts")
        assert resp.status_code == 200
        assert "alerts" in resp.json()

    def test_crypto_alert_rules_endpoint(self, client):
        resp = client.get("/api/crypto/alert-rules")
        assert resp.status_code == 200
        assert "rules" in resp.json()

    def test_crypto_indicators_mock(self, client):
        import pandas as pd
        df = pd.DataFrame({
            "date": [f"2026-05-{i:02d}" for i in range(1, 101)],
            "open": np.random.uniform(60000, 70000, 100),
            "high": np.random.uniform(61000, 71000, 100),
            "low": np.random.uniform(59000, 69000, 100),
            "close": np.random.uniform(60000, 70000, 100),
            "volume": np.random.uniform(100, 1000, 100),
            "amount": np.random.uniform(1000, 10000, 100),
        })
        with patch("src.core.crypto.service.download_crypto_kline", return_value=df):
            resp = client.get("/api/crypto/indicators?symbol=BTCUSDT&days=100")
        assert resp.status_code == 200
        body = resp.json()
        assert "indicators" in body
        assert "rsi" in body["indicators"] or "message" in body