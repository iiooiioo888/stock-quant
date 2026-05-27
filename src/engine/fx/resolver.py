"""匯率解析：即時 vs 歷史（禁止用當前匯率回溯歷史淨值）。"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from src.core.exchange import ExchangeRateService, get_exchange_service
from src.core.fx_store import get_historical_rates


class FXResolver:
    def __init__(self, exchange: ExchangeRateService | None = None):
        self._exchange = exchange or get_exchange_service()

    def spot_rate(self, target: str, base: str = "USD") -> Decimal:
        target = (target or "USD").upper()
        base = (base or "USD").upper()
        rates = self._exchange.get_rates()
        if target == base:
            return Decimal("1")
        if base != "USD":
            raise ValueError("僅支援 USD 基準即時匯率")
        return Decimal(str(rates.get(target, self._exchange.FALLBACK.get(target, 1.0))))

    def resolve(
        self,
        target: str,
        *,
        base: str = "USD",
        on_date: str | date | None = None,
    ) -> Decimal:
        """on_date 為過去日期時走歷史表 + 前向填充。"""
        target = (target or "USD").upper()
        if on_date is None:
            return self.spot_rate(target, base)

        d = on_date.strftime("%Y-%m-%d") if isinstance(on_date, date) else str(on_date)[:10]
        today = datetime.now().strftime("%Y-%m-%d")
        if d >= today:
            return self.spot_rate(target, base)

        hist = get_historical_rates(400, target, base=base)
        if d in hist:
            return Decimal(str(hist[d]))
        last: Decimal | None = None
        for fd in sorted(hist.keys()):
            if fd <= d:
                last = Decimal(str(hist[fd]))
            else:
                break
        if last is not None:
            return last
        return self.spot_rate(target, base)

    def display_fx_to_usd(self, display_currency: str) -> Decimal:
        """1 USD = ? display_currency"""
        return self.spot_rate(display_currency.upper(), "USD")
