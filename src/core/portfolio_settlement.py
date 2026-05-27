"""
多幣種資產結算 — 模擬持倉 / 用戶自定義持倉，USD 基準換算。
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Optional

from src.config import settings
from src.core.db import get_conn, load_daily_kline
from src.core.exchange import SUPPORTED_CURRENCIES, get_exchange_service
from src.core.result_cache import get_cached_compute, set_cached_compute
from src.utils.logger import logger


@dataclass
class Holding:
    code: str
    quantity: float
    currency: str
    asset_type: str
    price: float = 0.0

    @property
    def market_value(self) -> Decimal:
        return Decimal(str(self.quantity)) * Decimal(str(self.price or 0))


def infer_currency(code: str) -> str:
    c = (code or "").strip().upper()
    if c.endswith(".HK"):
        return "HKD"
    if c.endswith("=X") or c.endswith("=F"):
        return "USD"
    try:
        from src.core.history import detect_market

        market = detect_market(code)
        if market in ("hk_stock",):
            return "HKD"
        if market in ("us_stock", "global", "crypto", "forex", "forex_yahoo", "commodity", "index"):
            return "USD"
        if market in ("forex",):
            return "USD"
    except Exception:
        pass
    if c.isalpha() and len(c) <= 5 and not c.isdigit():
        return "USD"
    return "CNY"


def _normalize_currency(code: str) -> str:
    c = (code or "MOP").upper()
    if c not in SUPPORTED_CURRENCIES:
        return getattr(settings, "default_preferred_currency", "MOP")
    return c


def get_user_preferred_currency(user_id: int) -> str:
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT preferred_currency, settings FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    if not row:
        return _normalize_currency(getattr(settings, "default_preferred_currency", "MOP"))
    pref = (row["preferred_currency"] or "").strip().upper()
    if pref in SUPPORTED_CURRENCIES:
        return pref
    try:
        st = json.loads(row["settings"] or "{}")
        pref = (st.get("preferred_currency") or "").upper()
        if pref in SUPPORTED_CURRENCIES:
            return pref
    except (json.JSONDecodeError, TypeError):
        pass
    return _normalize_currency(getattr(settings, "default_preferred_currency", "MOP"))


def set_user_preferred_currency(user_id: int, currency: str) -> str:
    currency = _normalize_currency(currency)
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET preferred_currency = ? WHERE id = ?",
            (currency, user_id),
        )
    return currency


def _latest_price(code: str) -> float:
    try:
        df = load_daily_kline(code)
        if df is not None and not df.empty:
            col = "close" if "close" in df.columns else df.columns[-1]
            return float(df[col].iloc[-1])
    except Exception as e:
        logger.debug(f"取價失敗 {code}: {e}")
    return 0.0


def _resolve_paper_session_id(user_id: int, user_settings: dict) -> Optional[str]:
    sid = (user_settings or {}).get("paper_session_id")
    if sid:
        return str(sid)
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT id FROM paper_sessions
            WHERE status = 'active'
            ORDER BY started_at DESC
            LIMIT 1
            """
        ).fetchone()
    return row[0] if row else None


def fetch_holdings(user_id: int) -> list[Holding]:
    holdings: list[Holding] = []
    user_settings: dict = {}
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        urow = conn.execute(
            "SELECT settings FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if urow and urow["settings"]:
            try:
                user_settings = json.loads(urow["settings"])
            except (json.JSONDecodeError, TypeError):
                user_settings = {}

        for item in user_settings.get("holdings") or []:
            if not isinstance(item, dict):
                continue
            code = str(item.get("code") or "").strip()
            if not code:
                continue
            qty = float(item.get("quantity") or 0)
            if qty <= 0:
                continue
            curr = _normalize_currency(item.get("currency") or infer_currency(code))
            holdings.append(
                Holding(
                    code=code,
                    quantity=qty,
                    currency=curr,
                    asset_type=str(item.get("asset_type") or "equity"),
                    price=float(item.get("price") or 0) or _latest_price(code),
                )
            )

        session_id = _resolve_paper_session_id(user_id, user_settings)
        if session_id:
            rows = conn.execute(
                """
                SELECT code, shares, current_price, value
                FROM paper_positions
                WHERE session_id = ? AND shares > 0
                """,
                (session_id,),
            ).fetchall()
            existing = {h.code for h in holdings}
            for r in rows:
                code = r["code"]
                if code in existing:
                    continue
                price = float(r["current_price"] or 0) or _latest_price(code)
                holdings.append(
                    Holding(
                        code=code,
                        quantity=float(r["shares"]),
                        currency=infer_currency(code),
                        asset_type="paper",
                        price=price,
                    )
                )

    if not holdings:
        codes = list(settings.watchlist or [])[:8]
        for code in codes:
            price = _latest_price(code)
            if price <= 0:
                continue
            holdings.append(
                Holding(
                    code=code,
                    quantity=100.0,
                    currency=infer_currency(code),
                    asset_type="watchlist_demo",
                    price=price,
                )
            )
    return holdings


class PortfolioSettlementService:
    def __init__(self):
        self.exchange = get_exchange_service()

    def convert_value(
        self,
        amount: float | Decimal,
        from_curr: str,
        to_curr: str,
        rates: Optional[dict] = None,
    ) -> Decimal:
        return self.exchange.convert(amount, from_curr, to_curr, rates=rates)

    def get_summary(
        self,
        user_id: int,
        currency: Optional[str] = None,
        *,
        use_cache: bool = True,
    ) -> dict[str, Any]:
        target = _normalize_currency(currency or get_user_preferred_currency(user_id))
        cache_key = f"port:sum:{user_id}:{target}"
        if use_cache:
            cached = get_cached_compute("portfolio_summary", {"user_id": user_id, "currency": target})
            if cached:
                return cached

        rates = self.exchange.get_rates()
        holdings = fetch_holdings(user_id)
        total = Decimal("0")
        allocation: dict[str, Decimal] = {}
        positions_out = []

        for h in holdings:
            raw_val = h.market_value
            if raw_val <= 0:
                continue
            conv_val = self.convert_value(raw_val, h.currency, target, rates=rates)
            total += conv_val
            allocation[h.asset_type] = allocation.get(h.asset_type, Decimal("0")) + conv_val
            positions_out.append(
                {
                    "code": h.code,
                    "quantity": h.quantity,
                    "currency": h.currency,
                    "asset_type": h.asset_type,
                    "price": h.price,
                    "value_native": float(raw_val.quantize(Decimal("0.01"))),
                    "value": float(conv_val),
                }
            )

        alloc_pct = {}
        if total > 0:
            for k, v in allocation.items():
                alloc_pct[k] = round(float(v / total * 100), 2)

        daily_pnl = self._calc_daily_pnl(user_id, target, rates)

        result = {
            "success": True,
            "total_value": float(total.quantize(Decimal("0.01"))),
            "currency": target,
            "daily_pnl": float(daily_pnl),
            "allocation": alloc_pct,
            "positions": positions_out,
            "rates": {k: rates[k] for k in SUPPORTED_CURRENCIES if k in rates},
            "fx_updated": self.exchange.fx_updated_iso(),
            "disclaimer": "即時匯率僅供參考，結算以券商為準",
        }
        set_cached_compute(
            "portfolio_summary",
            {"user_id": user_id, "currency": target},
            result,
            ttl=300,
        )
        return result

    def _calc_daily_pnl(
        self, user_id: int, target: str, rates: dict[str, float]
    ) -> Decimal:
        user_settings: dict = {}
        with get_conn() as conn:
            urow = conn.execute(
                "SELECT settings FROM users WHERE id = ?", (user_id,)
            ).fetchone()
            if urow and urow[0]:
                try:
                    user_settings = json.loads(urow[0])
                except (json.JSONDecodeError, TypeError):
                    pass
            session_id = _resolve_paper_session_id(user_id, user_settings)
            if not session_id:
                return Decimal("0")
            rows = conn.execute(
                """
                SELECT nav, recorded_at FROM paper_nav_history
                WHERE session_id = ?
                ORDER BY recorded_at DESC
                LIMIT 2
                """,
                (session_id,),
            ).fetchall()
        if len(rows) < 2:
            return Decimal("0")
        nav_today = Decimal(str(rows[0][0]))
        nav_prev = Decimal(str(rows[1][0]))
        pnl_cny = nav_today - nav_prev
        return self.convert_value(pnl_cny, "CNY", target, rates=rates)

    def get_trend(
        self,
        user_id: int,
        days: int = 90,
        currency: Optional[str] = None,
    ) -> dict[str, Any]:
        target = _normalize_currency(currency or get_user_preferred_currency(user_id))
        days = max(7, min(int(days), 365))
        user_settings: dict = {}
        with get_conn() as conn:
            urow = conn.execute(
                "SELECT settings FROM users WHERE id = ?", (user_id,)
            ).fetchone()
            if urow and urow[0]:
                try:
                    user_settings = json.loads(urow[0])
                except (json.JSONDecodeError, TypeError):
                    pass
            session_id = _resolve_paper_session_id(user_id, user_settings)

        series = []
        if session_id:
            with get_conn() as conn:
                rows = conn.execute(
                    """
                    SELECT substr(recorded_at, 1, 10) AS d, MAX(nav) AS nav
                    FROM paper_nav_history
                    WHERE session_id = ?
                    GROUP BY d
                    ORDER BY d DESC
                    LIMIT ?
                    """,
                    (session_id, days),
                ).fetchall()
            rows = list(reversed(rows))

            from src.core.fx_store import get_historical_rates

            fx_by_date = get_historical_rates(days, target)
            fx_dates = sorted(fx_by_date.keys())
            last_fx = fx_by_date[fx_dates[-1]] if fx_dates else self.exchange.FALLBACK.get(target, 1.0)

            for d, nav in rows:
                fx = fx_by_date.get(d)
                if fx is None:
                    for fd in reversed(fx_dates):
                        if fd <= d:
                            fx = fx_by_date[fd]
                            break
                    else:
                        fx = last_fx
                last_fx = fx
                nav_dec = Decimal(str(nav))
                usd_nav = nav_dec / Decimal(str(self.exchange.FALLBACK.get("CNY", 7.248)))
                val = (usd_nav * Decimal(str(fx))).quantize(Decimal("0.01"))
                series.append({"date": d, "value": float(val)})

        if not series:
            summary = self.get_summary(user_id, target, use_cache=True)
            today = datetime.now().strftime("%Y-%m-%d")
            series = [{"date": today, "value": summary.get("total_value", 0)}]

        return {
            "success": True,
            "currency": target,
            "days": days,
            "series": series,
            "fx_updated": self.exchange.fx_updated_iso(),
            "disclaimer": "歷史趨勢按日匯率折算，非交易日沿用上一個有效匯率",
        }


_service: Optional[PortfolioSettlementService] = None


def get_portfolio_settlement_service() -> PortfolioSettlementService:
    global _service
    if _service is None:
        _service = PortfolioSettlementService()
    return _service
