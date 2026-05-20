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


def test_kline_code_to_universe():
    assert su._kline_code_to_universe("0700.HK", "hk_stock") == "00700"
    assert su._kline_code_to_universe("600519.SS", "a_share") == "600519"
    assert su._kline_code_to_universe("AAPL", "us_stock") == "AAPL"


def test_refresh_universe_from_local_kline():
    from src.core.db import get_conn, save_daily_kline, init_db
    import pandas as pd

    init_db()
    su.init_stock_universe_table()

    df = pd.DataFrame([
        {"date": "2026-05-19", "open": 99, "high": 101, "low": 98, "close": 100, "volume": 1000, "amount": 0},
        {"date": "2026-05-20", "open": 100, "high": 106, "low": 99, "close": 105, "volume": 1200, "amount": 0},
    ])
    save_daily_kline(df, "TEST1", market="us_stock")

    result = su.refresh_universe_from_local_kline()
    assert result["inserted"] >= 1 or result["updated"] >= 1

    rows, total = su.query_stock_universe(market="us_stock", keyword="TEST1", limit=5)
    assert total >= 1
    assert rows[0]["price"] == 105
    assert rows[0]["change_pct"] == 5.0

    with get_conn() as conn:
        conn.execute("DELETE FROM stock_universe WHERE code = 'TEST1'")
        conn.execute("DELETE FROM daily_kline WHERE code = 'TEST1'")
        conn.commit()


def test_fetch_intro_a_share(monkeypatch):
    def fake_get(*args, **kwargs):
        class Resp:
            status_code = 200

            @staticmethod
            def raise_for_status():
                return None

            @staticmethod
            def json():
                return {
                    "jbzl": [{
                        "BUSINESS_SCOPE": "茅台酒及系列酒的生产与销售",
                        "ORG_PROFILE": "贵州茅台酒股份有限公司…",
                    }],
                }

        return Resp()

    monkeypatch.setattr(su._HTTP, "get", fake_get)
    intro = su._fetch_intro_a_share("600519")
    assert "茅台酒" in intro


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
