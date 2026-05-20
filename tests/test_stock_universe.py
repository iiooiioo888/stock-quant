"""股票庫"""
import pandas as pd

from src.core import stock_universe as su


def test_parse_a_share_spot():
    df = pd.DataFrame([
        {
            "代码": "000001",
            "名称": "平安银行",
            "最新价": 10.5,
            "涨跌幅": 1.2,
            "总市值": 2_000_000_000_000,
            "流通市值": 1_800_000_000_000,
            "市盈率-动态": 8.5,
            "市净率": 0.9,
        },
        {
            "代码": "600519",
            "名称": "贵州茅台",
            "最新价": 1600,
            "涨跌幅": -0.5,
            "总市值": 2_500_000_000_000,
            "流通市值": 2_500_000_000_000,
            "市盈率-动态": 25,
            "市净率": 8,
        },
    ])
    rows = su._parse_spot_df(df, "a_share", "CN", "test")
    assert len(rows) == 2
    assert rows[0]["code"] == "000001"
    assert rows[1]["total_mv"] > rows[0]["total_mv"]


def test_sync_stock_universe_mock(monkeypatch):
    su.init_stock_universe_table()

    def fake_fetch():
        return [
            {"code": "000001", "market": "a_share", "name": "A", "exchange": "CN",
             "industry": "", "list_date": "", "price": 1, "change_pct": 0,
             "total_mv": 100, "circulating_mv": 90, "pe_ttm": 1, "pb": 1,
             "volume": 0, "amount": 0, "turnover": 0, "source": "test"},
            {"code": "600519", "market": "a_share", "name": "B", "exchange": "CN",
             "industry": "", "list_date": "", "price": 2, "change_pct": 0,
             "total_mv": 200, "circulating_mv": 180, "pe_ttm": 2, "pb": 2,
             "volume": 0, "amount": 0, "turnover": 0, "source": "test"},
        ]

    monkeypatch.setattr(su, "fetch_all_market_basics", fake_fetch)
    result = su.sync_stock_universe(max_count=10)
    assert result["saved"] == 2

    rows, total = su.query_stock_universe(limit=10)
    assert total == 2
    assert rows[0]["rank_mv"] == 1
    assert rows[0]["code"] == "600519"


def test_stock_universe_api(client, monkeypatch):
    df = pd.DataFrame([{
        "代码": "000001", "名称": "測試", "总市值": 1e11,
    }])
    monkeypatch.setattr(
        su,
        "fetch_all_market_basics",
        lambda: su._parse_spot_df(df, "a_share", "CN", "t"),
    )
    su.sync_stock_universe(max_count=5)

    r = client.get("/api/stock-universe/stats")
    assert r.status_code == 200
    assert r.json()["total"] >= 1

    r2 = client.get("/api/stock-universe?limit=5")
    assert r2.status_code == 200
    assert len(r2.json()["stocks"]) >= 1
