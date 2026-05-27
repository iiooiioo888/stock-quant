"""交易驅動持倉滾動與計算引擎。"""
from decimal import Decimal

import pytest


def test_portfolio_calculator_basic():
    from src.engine.portfolio.calculator import HoldingCalc, PortfolioCalculator

    holdings = [
        HoldingCalc(
            symbol="600519",
            qty=Decimal("10"),
            avg_cost=Decimal("100"),
            currency="CNY",
            current_price=Decimal("110"),
            fx_to_usd=Decimal("0.138"),
            display_fx=Decimal("7.248"),
            asset_type="equity",
        )
    ]
    out = PortfolioCalculator.compute(holdings, "USD", realized_pnl=Decimal("50"))
    assert out["total_value"] > 0
    assert out["realized_pnl"] == 50.0
    assert "CNY_assets" in out["allocation"]


def test_ledger_buy_sell_roll(isolated_db):
    import sqlite3

    from src.config import settings
    from src.core.portfolio_ledger import recompute_holdings
    from src.core.portfolio_repo import get_portfolio_repo
    from src.core.database.connection import get_conn, reset_thread_connection

    assert settings.db_path == isolated_db
    reset_thread_connection()

    uid = 9001
    with get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO users (id, username, password_hash, created_at) VALUES (?, ?, ?, ?)",
            (uid, "ledger_test", "x", "2026-01-01 00:00:00"),
        )
    repo = get_portfolio_repo()
    repo.insert_transaction(uid, symbol="AAPL", tx_type="BUY", quantity=10, price=100, currency="USD")
    repo.insert_transaction(uid, symbol="AAPL", tx_type="SELL", quantity=4, price=120, currency="USD")

    with sqlite3.connect(isolated_db) as raw:
        rows = raw.execute(
            "SELECT type, quantity FROM portfolio_transactions WHERE user_id = ? ORDER BY executed_at",
            (uid,),
        ).fetchall()
    assert rows == [("BUY", 10.0), ("SELL", 4.0)]

    state = recompute_holdings(uid)
    assert len(state.holdings) == 1
    h = state.holdings[0]
    assert float(h.total_qty) == pytest.approx(6.0)
    assert float(state.realized_pnl) == pytest.approx(80.0)


@pytest.fixture
def isolated_db(monkeypatch):
    import os
    import tempfile

    path = os.path.join(tempfile.gettempdir(), f"test_ledger_{os.getpid()}.db")
    if os.path.exists(path):
        os.remove(path)
    monkeypatch.setenv("SQ_DB_PATH", path)
    from src.config import settings
    from src.core.database import init_database
    from src.core.database.connection import reset_thread_connection

    settings.db_path = path
    reset_thread_connection()
    init_database()
    import src.core.portfolio_repo as portfolio_repo_mod

    portfolio_repo_mod._repo = None
    yield path
    reset_thread_connection()
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass
