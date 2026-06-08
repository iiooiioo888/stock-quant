"""資產庫持久層 — 交易流水與物化持倉。"""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from src.core.db import get_conn

TX_TYPES = frozenset({"BUY", "SELL", "DIV", "SPLIT", "CASH_IN", "CASH_OUT", "DELIST"})


@dataclass
class MaterializedHolding:
    symbol: str
    total_qty: Decimal
    avg_cost: Decimal
    currency: str
    last_updated: str


class PortfolioRepo:
    def list_transactions(
        self, user_id: int, *, symbol: str | None = None, limit: int = 5000
    ) -> list[sqlite3.Row]:
        with get_conn() as conn:
            conn.row_factory = sqlite3.Row
            if symbol:
                return conn.execute(
                    """
                    SELECT * FROM portfolio_transactions
                    WHERE user_id = ? AND symbol = ?
                    ORDER BY executed_at ASC, rowid ASC
                    LIMIT ?
                    """,
                    (user_id, symbol, limit),
                ).fetchall()
            return conn.execute(
                """
                SELECT * FROM portfolio_transactions
                WHERE user_id = ?
                ORDER BY executed_at ASC, rowid ASC
                LIMIT ?
                """,
                (user_id, limit),
            ).fetchall()

    def insert_transaction(
        self,
        user_id: int,
        *,
        symbol: str,
        tx_type: str,
        quantity: float,
        price: float,
        currency: str,
        fee: float = 0,
        executed_at: str | None = None,
        note: str = "",
    ) -> str:
        t = (tx_type or "").upper()
        if t not in TX_TYPES:
            raise ValueError(f"不支援的交易類型: {tx_type}")
        tx_id = uuid.uuid4().hex
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        executed = executed_at or now
        with get_conn() as conn:
            conn.execute(
                """
                INSERT INTO portfolio_transactions
                (id, user_id, symbol, type, quantity, price, currency, fee, executed_at, note, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tx_id,
                    user_id,
                    symbol.strip().upper(),
                    t,
                    float(quantity),
                    float(price),
                    currency.upper(),
                    float(fee),
                    executed,
                    note or None,
                    now,
                ),
            )
        return tx_id

    def batch_get_holdings(
        self, user_id: int, symbols: list[str] | None = None
    ) -> dict[str, MaterializedHolding]:
        with get_conn() as conn:
            conn.row_factory = sqlite3.Row
            if symbols:
                placeholders = ",".join("?" * len(symbols))
                rows = conn.execute(
                    f"""
                    SELECT symbol, total_qty, avg_cost, currency, last_updated
                    FROM portfolio_holdings
                    WHERE user_id = ? AND symbol IN ({placeholders})
                    """,
                    (user_id, *[s.upper() for s in symbols]),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT symbol, total_qty, avg_cost, currency, last_updated
                    FROM portfolio_holdings
                    WHERE user_id = ? AND total_qty > 0
                    """,
                    (user_id,),
                ).fetchall()
        out: dict[str, MaterializedHolding] = {}
        for r in rows:
            out[r["symbol"]] = MaterializedHolding(
                symbol=r["symbol"],
                total_qty=Decimal(str(r["total_qty"])),
                avg_cost=Decimal(str(r["avg_cost"])),
                currency=r["currency"],
                last_updated=r["last_updated"],
            )
        return out

    def upsert_holdings(
        self, user_id: int, holdings: list[MaterializedHolding]
    ) -> None:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with get_conn() as conn:
            conn.execute("DELETE FROM portfolio_holdings WHERE user_id = ?", (user_id,))
            for h in holdings:
                if h.total_qty <= 0:
                    continue
                conn.execute(
                    """
                    INSERT INTO portfolio_holdings
                    (user_id, symbol, total_qty, avg_cost, currency, last_updated)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user_id,
                        h.symbol,
                        float(h.total_qty),
                        float(h.avg_cost),
                        h.currency,
                        h.last_updated or now,
                    ),
                )

    def save_snapshot(
        self,
        user_id: int,
        snapshot_date: str,
        currency: str,
        *,
        total_net_worth: float,
        daily_pnl: float = 0,
        fx_rate_to_usd: float | None = None,
        allocation: dict | None = None,
    ) -> None:
        with get_conn() as conn:
            conn.execute(
                """
                INSERT INTO portfolio_snapshots
                (user_id, snapshot_date, currency, total_net_worth, daily_pnl, fx_rate_to_usd, allocation_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, snapshot_date, currency) DO UPDATE SET
                    total_net_worth = excluded.total_net_worth,
                    daily_pnl = excluded.daily_pnl,
                    fx_rate_to_usd = excluded.fx_rate_to_usd,
                    allocation_json = excluded.allocation_json
                """,
                (
                    user_id,
                    snapshot_date,
                    currency.upper(),
                    total_net_worth,
                    daily_pnl,
                    fx_rate_to_usd,
                    json.dumps(allocation or {}, ensure_ascii=False),
                ),
            )

    def list_snapshots(
        self, user_id: int, currency: str, *, days: int = 90
    ) -> list[dict[str, Any]]:
        with get_conn() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT snapshot_date, total_net_worth, daily_pnl, allocation_json
                FROM portfolio_snapshots
                WHERE user_id = ? AND currency = ?
                ORDER BY snapshot_date DESC
                LIMIT ?
                """,
                (user_id, currency.upper(), days),
            ).fetchall()
        out = []
        for r in reversed(rows):
            alloc = {}
            try:
                alloc = json.loads(r["allocation_json"] or "{}")
            except (json.JSONDecodeError, TypeError):
                pass
            out.append(
                {
                    "date": r["snapshot_date"],
                    "value": float(r["total_net_worth"]),
                    "daily_pnl": float(r["daily_pnl"] or 0),
                    "allocation": alloc,
                }
            )
        return out

    def has_transactions(self, user_id: int) -> bool:
        with get_conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM portfolio_transactions WHERE user_id = ? LIMIT 1",
                (user_id,),
            ).fetchone()
        return row is not None


_repo: Optional[PortfolioRepo] = None


def get_portfolio_repo() -> PortfolioRepo:
    global _repo
    if _repo is None:
        _repo = PortfolioRepo()
    return _repo
