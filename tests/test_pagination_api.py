"""alerts offset/total 與 stocks 遊標分頁。"""


def test_alerts_pagination_total_and_offset(client):
    r1 = client.get("/api/alerts?limit=2&offset=0")
    assert r1.status_code == 200
    body = r1.json()
    assert "alerts" in body
    assert "total" in body
    assert "offset" in body
    assert "has_more" in body
    assert body["limit"] == 2


def test_stocks_cursor_fields(client):
    r = client.get("/api/stocks?limit=5")
    assert r.status_code == 200
    body = r.json()
    assert "stocks" in body
    assert "total" in body
    assert "has_more" in body
    assert "next_cursor" in body
    if body["has_more"] and body["stocks"]:
        cur = body["next_cursor"]
        r2 = client.get(f"/api/stocks?limit=5&cursor={cur}")
        assert r2.status_code == 200
        b2 = r2.json()
        assert "stocks" in b2
