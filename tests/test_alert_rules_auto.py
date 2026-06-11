"""自動生成預警規則"""

from unittest.mock import patch

import pytest


@pytest.fixture
def auth_headers(client):
    import uuid

    pw = "alert_auto_pw_2026"
    username = f"alertauto_{uuid.uuid4().hex[:8]}"
    client.post("/api/auth/register", json={"username": username, "password": pw})
    resp = client.post("/api/auth/login", json={"username": username, "password": pw})
    return {"Authorization": f"Bearer {resp.json()['token']}"}


class TestAlertRulesAuto:
    def test_suggest_without_auth(self, client):
        with patch(
            "src.core.alert_rules_auto.fetch_latest_prices",
            return_value={
                "000001": {"price": 10.0, "name": "平安銀行", "source": "test"}
            },
        ):
            resp = client.get("/api/alerts/rules/suggest?code=000001")
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == "000001"
        assert data["rule"]["price_above"] > 10
        assert data["rule"]["price_below"] < 10

    def test_auto_add_requires_auth_in_demo(self, client):
        with patch(
            "src.core.alert_rules_auto.fetch_latest_prices",
            return_value={"000002": {"price": 20.0, "name": "萬科", "source": "test"}},
        ):
            resp = client.post(
                "/api/alerts/rules/auto",
                json={"codes": ["000002"], "skip_existing": False},
            )
        assert resp.status_code == 401

    def test_auto_add_with_auth(self, client, auth_headers):
        from src.config import settings

        settings.alert_rules.pop("000002", None)
        with patch(
            "src.core.alert_rules_auto.fetch_latest_prices",
            return_value={"000002": {"price": 20.0, "name": "萬科A", "source": "test"}},
        ):
            resp = client.post(
                "/api/alerts/rules/auto",
                json={"codes": ["000002"], "skip_existing": False},
                headers=auth_headers,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "000002" in data["added"]
        assert settings.alert_rules["000002"]["price_above"] > 20
