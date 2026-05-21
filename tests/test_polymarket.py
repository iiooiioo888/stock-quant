"""
Polymarket 模塊測試 — mock HTTP，不依賴外網。
"""
import json
import pytest
from unittest.mock import MagicMock, patch

from src.core.polymarket.normalize import (
    normalize_market,
    normalize_orderbook,
    normalize_price_point,
)
from src.core.polymarket.service import (
    PolymarketService,
    PolymarketDisabledError,
    _market_is_displayable,
)


SAMPLE_MARKET = {
    "id": "12345",
    "slug": "will-btc-hit-100k",
    "question": "Will BTC hit 100k?",
    "conditionId": "0xabc",
    "outcomes": '["Yes", "No"]',
    "outcomePrices": '["0.65", "0.35"]',
    "clobTokenIds": '["token_yes", "token_no"]',
    "volume": "1000000",
    "liquidity": "50000",
    "active": True,
    "closed": False,
    "endDate": "2026-12-31",
}


class TestNormalize:
    def test_normalize_market_prices(self):
        m = normalize_market(SAMPLE_MARKET)
        assert m["market_id"] == "12345"
        assert m["slug"] == "will-btc-hit-100k"
        assert abs(m["yes_price"] - 0.65) < 0.01
        assert abs(m["no_price"] - 0.35) < 0.01
        assert m["price_source"] == "outcome_prices"
        assert m["token_ids"] == ["token_yes", "token_no"]

    def test_normalize_market_orderbook_fallback(self):
        raw = {
            "id": "99",
            "question": "Test?",
            "bestBid": "0.48",
            "bestAsk": "0.52",
            "lastTradePrice": 0,
            "volume24hr": 1000,
        }
        m = normalize_market(raw)
        assert m["price_source"] == "orderbook"
        assert abs(m["yes_price"] - 0.5) < 0.01

    def test_normalize_stale_crypto_slot(self):
        raw = {
            "id": "1",
            "question": "ETH Up or Down - December 19",
            "bestBid": 0,
            "bestAsk": 1,
            "lastTradePrice": 0,
            "volume24hr": 0,
        }
        m = normalize_market(raw)
        assert m["price_source"] == "none"
        assert m["yes_price"] == 0.0

    def test_normalize_orderbook_spread(self):
        raw = {
            "bids": [{"price": "0.64", "size": "100"}],
            "asks": [{"price": "0.66", "size": "80"}],
        }
        ob = normalize_orderbook(raw, "token_yes", depth=5)
        assert ob["best_bid"] == 0.64
        assert ob["best_ask"] == 0.66
        assert abs(ob["spread"] - 0.02) < 0.001
        assert abs(ob["mid"] - 0.65) < 0.001

    def test_normalize_price_point(self):
        p = normalize_price_point({"t": 1700000000, "p": "0.55"})
        assert p["ts"] == 1700000000
        assert p["price"] == 0.55


class TestPolymarketService:
    def test_list_markets_mock(self):
        svc = PolymarketService()
        with patch.object(svc._gamma, "list_markets", return_value=[SAMPLE_MARKET]):
            with patch("src.core.polymarket.service.api_cache.cached_response", side_effect=lambda k, t, b: b()):
                out = svc.list_markets(limit=10, use_cache=False)
        assert out["total"] == 1
        assert out["markets"][0]["question"] == "Will BTC hit 100k?"

    def test_market_is_displayable_filters_stale(self):
        stale = normalize_market({
            "id": "1",
            "question": "ETH Up or Down",
            "bestBid": 0,
            "bestAsk": 1,
            "volume24hr": 0,
        })
        assert not _market_is_displayable(stale)
        assert _market_is_displayable(normalize_market(SAMPLE_MARKET))

    def test_disabled_raises(self, monkeypatch):
        from src.config import settings
        monkeypatch.setattr(settings, "polymarket_enabled", False)
        svc = PolymarketService()
        with pytest.raises(PolymarketDisabledError):
            svc.list_markets(use_cache=False)


class TestPolymarketAPI:
    def test_markets_endpoint_mock(self, client, monkeypatch):
        from src.config import settings
        monkeypatch.setattr(settings, "polymarket_enabled", True)
        fake = {
            "markets": [normalize_market(SAMPLE_MARKET)],
            "total": 1,
            "limit": 50,
            "offset": 0,
            "source": "gamma",
        }
        with patch(
            "src.api.routers.polymarket.get_polymarket_service",
        ) as mock_get:
            mock_get.return_value.list_markets.return_value = fake
            resp = client.get("/api/polymarket/markets?limit=5")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert "yes_price" in data["markets"][0]

    def test_orderbook_endpoint_mock(self, client, monkeypatch):
        from src.config import settings
        monkeypatch.setattr(settings, "polymarket_enabled", True)
        ob = normalize_orderbook(
            {"bids": [{"price": "0.5", "size": "10"}], "asks": [{"price": "0.52", "size": "10"}]},
            "tok1",
        )
        with patch("src.api.routers.polymarket.get_polymarket_service") as mock_get:
            mock_get.return_value.get_orderbook.return_value = ob
            resp = client.get("/api/polymarket/orderbook?token_id=tok1")
        assert resp.status_code == 200
        assert resp.json()["token_id"] == "tok1"

    def test_disabled_returns_503(self, client, monkeypatch):
        from src.config import settings
        monkeypatch.setattr(settings, "polymarket_enabled", False)
        resp = client.get("/api/polymarket/markets")
        assert resp.status_code == 503

    def test_search_requires_query(self, client, monkeypatch):
        from src.config import settings
        monkeypatch.setattr(settings, "polymarket_enabled", True)
        resp = client.get("/api/polymarket/search")
        assert resp.status_code == 422
