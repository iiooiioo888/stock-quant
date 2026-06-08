"""回測歷史分頁 API"""

import pytest


def test_backtest_history_offset(client):
    r1 = client.get("/api/backtest/history?limit=2&offset=0")
    assert r1.status_code == 200
    d1 = r1.json()
    assert "results" in d1
    assert d1.get("offset") == 0
    assert d1.get("limit") == 2
    assert "total" in d1
    assert isinstance(d1.get("has_more"), bool)

    r2 = client.get("/api/backtest/history?limit=2&offset=2")
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2.get("offset") == 2


def test_backtest_history_page_size_cap(client):
    r = client.get("/api/backtest/history?page_size=500")
    assert r.status_code == 200
    assert r.json().get("limit") == 100
