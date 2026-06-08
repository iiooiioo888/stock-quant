"""由交易流水滾動計算物化持倉與已實現損益。"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from src.core.db import get_conn
from src.core.portfolio_currency import infer_currency
from src.core.portfolio_repo import (
    MaterializedHolding,
    PortfolioRepo,
    get_portfolio_repo,
)
from src.utils.logger import logger

_Q = Decimal("0.000001")


@dataclass
class LedgerState:
    holdings: list[MaterializedHolding]
    realized_pnl: Decimal


def _roll_symbol(rows: list[sqlite3.Row]) -> tuple[MaterializedHolding | None, Decimal]:
    qty = Decimal("0")
    avg = Decimal("0")
    currency = "MOP"
    realized = Decimal("0")

    for r in rows:
        t = (r["type"] or "").upper()
        q = Decimal(str(r["quantity"] or 0))
        price = Decimal(str(r["price"] or 0))
        currency = (r["currency"] or currency).upper()
        fee = Decimal(str(r["fee"] or 0))

        if t == "BUY":
            if q <= 0:
                continue
            cost = q * price + fee
            if qty <= 0:
                qty = q
                avg = cost / q if q else Decimal("0")
            else:
                avg = (avg * qty + cost) / (qty + q)
                qty += q
        elif t == "SELL":
            if q <= 0 or qty <= 0:
                continue
            sell_q = min(q, qty)
            realized += (price - avg) * sell_q - fee
            qty -= sell_q
            if qty <= _Q:
                qty = Decimal("0")
                avg = Decimal("0")
        elif t == "DIV":
            realized += q * price
        elif t == "SPLIT" and q > 0:
            qty *= q
        elif t == "DELIST":
            if qty > 0 and price > 0:
                realized += (price - avg) * qty
            qty = Decimal("0")
            avg = Decimal("0")
        elif t in ("CASH_IN", "CASH_OUT"):
            pass

    if qty <= _Q:
        return None, realized
    sym = rows[0]["symbol"] if rows else ""
    return (
        MaterializedHolding(
            symbol=sym,
            total_qty=qty,
            avg_cost=avg.quantize(Decimal("0.000001")),
            currency=currency,
            last_updated=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ),
        realized,
    )


def recompute_holdings(user_id: int, repo: PortfolioRepo | None = None) -> LedgerState:
    repo = repo or get_portfolio_repo()
    rows = repo.list_transactions(user_id)
    by_sym: dict[str, list[sqlite3.Row]] = {}
    for r in rows:
        by_sym.setdefault(r["symbol"], []).append(r)

    holdings: list[MaterializedHolding] = []
    realized_total = Decimal("0")
    for sym_rows in by_sym.values():
        h, realized = _roll_symbol(sym_rows)
        realized_total += realized
        if h:
            holdings.append(h)

    repo.upsert_holdings(user_id, holdings)
    return LedgerState(holdings=holdings, realized_pnl=realized_total)


def import_settings_holdings_as_buys(
    user_id: int, repo: PortfolioRepo | None = None
) -> int:
    """將 users.settings.holdings 遷移為 BUY 流水（僅在無流水時）。"""
    repo = repo or get_portfolio_repo()
    if repo.has_transactions(user_id):
        return 0

    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT settings FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    if not row or not row["settings"]:
        return 0
    try:
        st = json.loads(row["settings"])
    except (json.JSONDecodeError, TypeError):
        return 0

    count = 0
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for item in st.get("holdings") or []:
        if not isinstance(item, dict):
            continue
        code = str(item.get("code") or "").strip().upper()
        qty = float(item.get("quantity") or 0)
        if not code or qty <= 0:
            continue
        price = float(item.get("price") or item.get("avg_cost") or 0)
        curr = (item.get("currency") or infer_currency(code)).upper()
        repo.insert_transaction(
            user_id,
            symbol=code,
            tx_type="BUY",
            quantity=qty,
            price=price if price > 0 else 0.01,
            currency=curr,
            executed_at=now,
            note="migrated_from_settings",
        )
        count += 1

    if count:
        recompute_holdings(user_id, repo)
        logger.info(f"用戶 {user_id} 已從 settings 遷移 {count} 筆 BUY 流水")
    return count
