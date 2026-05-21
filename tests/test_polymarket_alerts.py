"""Polymarket 概率預警與策略信號。"""
import json
from unittest.mock import patch

import pytest


@pytest.fixture
def pm_alert_db(client):
    from src.core.polymarket.store import init_polymarket_tables
    init_polymarket_tables()
    yield


class TestPolymarketAlertRules:
    def test_upsert_and_list_rule(self, pm_alert_db):
        from src.core.polymarket.alert_store import upsert_alert_rule, list_alert_rules

        rule = upsert_alert_rule({
            "market_key": "test-market-slug",
            "name": "測試市場",
            "yes_above": 0.8,
            "prob_change_pct": 10,
        })
        assert rule["market_key"] == "test-market-slug"
        assert rule["yes_above"] == 0.8
        rules = list_alert_rules()
        assert any(r["id"] == rule["id"] for r in rules)


class TestPolymarketAlertEngine:
    def test_yes_above_triggers(self, pm_alert_db):
        from src.core.polymarket.alerts import PolymarketAlertEngine
        from src.core.polymarket.alert_store import upsert_alert_rule

        upsert_alert_rule({
            "market_key": "fed-rate",
            "yes_above": 0.7,
            "enabled": True,
        })
        engine = PolymarketAlertEngine()
        market = {
            "market_id": "1",
            "slug": "fed-rate",
            "question": "Fed cut?",
            "yes_price": 0.82,
            "no_price": 0.18,
        }
        with patch.object(engine, "dispatch") as mock_dispatch:
            msgs = engine.evaluate_rule(
                {"market_key": "fed-rate", "yes_above": 0.7, "enabled": True},
                market,
            )
            assert len(msgs) == 1
            mock_dispatch.assert_not_called()
        engine.dispatch(msgs)
        assert engine.total_alerts == 1


class TestPolymarketStrategySignals:
    def test_classify_bullish(self):
        from src.core.polymarket.strategy_signals import classify_market

        sig = classify_market({
            "slug": "x",
            "question": "Q?",
            "yes_price": 0.85,
            "no_price": 0.15,
        })
        assert sig["signal"] == "bullish"
        assert sig["action_hint"] == "long_yes"


class TestPolymarketAlertAPI:
    def test_strategy_signals_route(self, client, monkeypatch):
        from src.config import settings
        monkeypatch.setattr(settings, "polymarket_enabled", True)

        fake = {
            "signals": [{"market_key": "a", "signal": "neutral"}],
            "total": 1,
            "thresholds": {},
            "source": "polymarket_probability",
        }
        with patch(
            "src.core.polymarket.strategy_signals.compute_strategy_signals",
            return_value=fake,
        ):
            resp = client.get("/api/polymarket/strategy-signals?limit=5")
        assert resp.status_code == 200
        assert resp.json()["total"] == 1

    def test_alert_rules_list(self, client, monkeypatch, pm_alert_db):
        from src.config import settings
        monkeypatch.setattr(settings, "polymarket_enabled", True)
        resp = client.get("/api/polymarket/alerts/rules")
        assert resp.status_code == 200
        assert "rules" in resp.json()
