"""組合帳本 Ledger 純函數單測（P1）。"""
from decimal import Decimal

from src.core.portfolio_ledger import _roll_symbol
from src.core.portfolio_repo import MaterializedHolding


def _row(**fields):
    """模擬 sqlite3.Row 下標存取。"""
    return fields


def test_roll_symbol_buy_then_sell_realized_pnl():
    rows = [
        _row(symbol="AAPL", type="BUY", quantity=10, price=100, currency="USD", fee=1),
        _row(symbol="AAPL", type="SELL", quantity=5, price=120, currency="USD", fee=1),
    ]
    holding, realized = _roll_symbol(rows)
    assert holding is not None
    assert isinstance(holding, MaterializedHolding)
    assert holding.symbol == "AAPL"
    assert holding.total_qty == Decimal("5")
    # 成本 (10*100+1)/10 * 5 ≈ 500.5 賣出 5@120-1 → 實現約 99
    assert realized > Decimal("90")
    assert realized < Decimal("110")


def test_roll_symbol_split_increases_qty():
    rows = [
        _row(symbol="TEST", type="BUY", quantity=100, price=10, currency="MOP", fee=0),
        _row(symbol="TEST", type="SPLIT", quantity=2, price=0, currency="MOP", fee=0),
    ]
    holding, realized = _roll_symbol(rows)
    assert holding is not None
    assert holding.total_qty == Decimal("200")
    assert realized == Decimal("0")


def test_roll_symbol_delist_closes_position():
    rows = [
        _row(symbol="DEL", type="BUY", quantity=50, price=2, currency="HKD", fee=0),
        _row(symbol="DEL", type="DELIST", quantity=0, price=1, currency="HKD", fee=0),
    ]
    holding, realized = _roll_symbol(rows)
    assert holding is None
    assert realized == Decimal("-50")  # (1-2)*50


def test_roll_symbol_dividend_adds_realized():
    rows = [
        _row(symbol="DIV", type="BUY", quantity=10, price=50, currency="USD", fee=0),
        _row(symbol="DIV", type="DIV", quantity=1, price=2, currency="USD", fee=0),
    ]
    holding, realized = _roll_symbol(rows)
    assert holding is not None
    assert realized == Decimal("2")
