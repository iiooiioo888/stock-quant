"""多幣種結算 — 匯率與 Decimal 換算。"""
from decimal import Decimal

import pytest


def test_exchange_convert_same_currency():
    from src.core.exchange import ExchangeRateService

    svc = ExchangeRateService()
    rates = svc.FALLBACK
    assert svc.convert(100, "MOP", "MOP", rates=rates) == Decimal("100.00")


def test_exchange_cross_via_usd():
    from src.core.exchange import ExchangeRateService

    svc = ExchangeRateService()
    rates = svc.FALLBACK
    # 100 HKD -> USD -> MOP
    out = svc.convert(100, "HKD", "MOP", rates=rates)
    usd = Decimal("100") / Decimal(str(rates["HKD"]))
    expected = (usd * Decimal(str(rates["MOP"]))).quantize(Decimal("0.01"))
    assert out == expected


def test_infer_currency():
    from src.core.portfolio_currency import infer_currency

    assert infer_currency("600519") == "CNY"
    assert infer_currency("0700.HK") == "HKD"
    assert infer_currency("AAPL") == "USD"


def test_portfolio_summary_structure():
    from src.core.portfolio_settlement import PortfolioSettlementService

    svc = PortfolioSettlementService()
    data = svc.get_summary(user_id=0, currency="USD", use_cache=False)
    assert data["success"] is True
    assert data["currency"] == "USD"
    assert "total_value" in data
    assert "allocation" in data
    assert data.get("disclaimer")


def test_fx_rates_api(client):
    r = client.get("/api/portfolio/fx-rates")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert "USD" in body["rates"]
    assert "MOP" in body["rates"]


@pytest.fixture
def auth_headers(client):
    import uuid

    pw = "test_fx_pw_2026"
    username = f"fxuser_{uuid.uuid4().hex[:8]}"
    client.post("/api/auth/register", json={"username": username, "password": pw})
    resp = client.post("/api/auth/login", json={"username": username, "password": pw})
    token = resp.json().get("token")
    return {"Authorization": f"Bearer {token}"}


def test_preferred_currency_validation(client, auth_headers):
    r = client.put(
        "/api/user/preferred-currency",
        json={"preferred_currency": "INVALID"},
        headers=auth_headers,
    )
    assert r.status_code == 400


def test_summary_requires_auth(client):
    r = client.get("/api/portfolio/summary?currency=MOP")
    assert r.status_code in (401, 403)
