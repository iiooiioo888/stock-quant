"""持倉估值與 P&L — 純函數，全程 Decimal。"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP


@dataclass
class HoldingCalc:
    symbol: str
    qty: Decimal
    avg_cost: Decimal
    currency: str
    current_price: Decimal
    fx_to_usd: Decimal
    display_fx: Decimal
    asset_type: str = "equity"
    stale_price: bool = False


class PortfolioCalculator:
    _Q = Decimal("0.01")

    @staticmethod
    def compute(
        holdings: list[HoldingCalc],
        display_currency: str,
        *,
        realized_pnl: Decimal = Decimal("0"),
    ) -> dict:
        total_usd = Decimal("0")
        allocation_usd: dict[str, Decimal] = {}
        unrealized = Decimal("0")

        for h in holdings:
            if h.qty <= 0 or h.current_price <= 0:
                continue
            market_val_usd = h.qty * h.current_price * h.fx_to_usd
            total_usd += market_val_usd
            cat = f"{h.currency}_assets" if h.currency else "other_assets"
            allocation_usd[cat] = allocation_usd.get(cat, Decimal("0")) + market_val_usd
            if not h.stale_price:
                unrealized += (h.current_price - h.avg_cost) * h.qty * h.display_fx

        display_fx = holdings[0].display_fx if holdings else Decimal("1")
        if display_fx <= 0:
            display_fx = Decimal("1")

        total_display = (total_usd / display_fx).quantize(PortfolioCalculator._Q, ROUND_HALF_UP)
        alloc_pct: dict[str, float] = {}
        if total_usd > 0:
            for k, v in allocation_usd.items():
                alloc_pct[k] = round(float(v / total_usd * 100), 2)

        return {
            "total_value": float(total_display),
            "unrealized_pnl": float(unrealized.quantize(PortfolioCalculator._Q, ROUND_HALF_UP)),
            "realized_pnl": float(realized_pnl.quantize(PortfolioCalculator._Q, ROUND_HALF_UP)),
            "allocation": alloc_pct,
        }
