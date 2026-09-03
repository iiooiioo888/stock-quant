"""A 股佣金模型：下限、印花稅、過戶費。"""

from src.core.backtest import AStockCommission


def test_min_commission_applies_on_small_turnover():
    comm = AStockCommission(
        commission=0.00025, min_commission=5.0, stamp_tax=0.0005, transfer_fee=0.00001
    )
    # 買入 100 股 * 10 元 = 1000，費率佣金 0.25 元 → 應抬到 5 元 + 過戶費
    buy = comm._getcommission(100, 10.0, pseudoexec=True)
    assert buy >= 5.0


def test_stamp_tax_only_on_sell():
    comm = AStockCommission(
        commission=0.0, min_commission=0.0, stamp_tax=0.0005, transfer_fee=0.0
    )
    buy = comm._getcommission(1000, 10.0, pseudoexec=True)
    sell = comm._getcommission(-1000, 10.0, pseudoexec=True)
    assert buy == 0.0
    assert abs(sell - 5.0) < 1e-9  # 10000 * 0.0005
