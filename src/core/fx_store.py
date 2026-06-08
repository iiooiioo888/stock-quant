"""
日匯率持久化 — 供歷史趨勢按日換算。
"""

from __future__ import annotations

from datetime import datetime

from src.core.db import get_conn
from src.utils.logger import logger


def persist_daily_rates(rates: dict[str, float], base: str = "USD") -> None:
    if not rates:
        return
    day = datetime.now().strftime("%Y-%m-%d")
    with get_conn() as conn:
        for target, rate in rates.items():
            t = str(target).upper()
            if t == base:
                continue
            try:
                conn.execute(
                    """
                    INSERT INTO fx_rates_daily (base, target, rate, date)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(base, target, date) DO UPDATE SET rate = excluded.rate
                    """,
                    (base, t, float(rate), day),
                )
            except Exception as e:
                logger.debug(f"fx_rates_daily 寫入跳過 {t}: {e}")


def get_historical_rates(
    days: int,
    target: str,
    base: str = "USD",
) -> dict[str, float]:
    """date -> rate (target per 1 USD)，缺失日用最近已知值前向填充。"""
    target = target.upper()
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT date, rate FROM fx_rates_daily
            WHERE base = ? AND target = ?
            ORDER BY date DESC
            LIMIT ?
            """,
            (base, target, max(days, 1) + 5),
        ).fetchall()

    if not rows:
        from src.core.exchange import ExchangeRateService

        latest = ExchangeRateService.FALLBACK.get(target, 1.0)
        today = datetime.now().strftime("%Y-%m-%d")
        return {today: latest}

    by_date = {r[0]: float(r[1]) for r in rows}
    sorted_dates = sorted(by_date.keys())
    last = by_date[sorted_dates[-1]]
    out: dict[str, float] = {}
    for d in sorted_dates:
        last = by_date[d]
        out[d] = last
    return out
