"""
匯率服務 — USD 基準、L1/L2 緩存、離線兜底。
"""

from __future__ import annotations

import time
from decimal import Decimal
from typing import Dict, Optional

import requests

from src.core.cache import get_cache
from src.utils.logger import logger

SUPPORTED_CURRENCIES = frozenset({"HKD", "MOP", "USD", "CNY"})
FRANKFURTER_LATEST = "https://api.frankfurter.dev/v1/latest"


class ExchangeRateService:
    """取得各幣種相對 1 USD 的匯率（target 數量 / 1 USD）。"""

    BASE = "USD"
    SUPPORTED = SUPPORTED_CURRENCIES
    L1_TTL = 900
    L2_TTL = 3600
    CACHE_KEY = "fx:rates:latest:v1"
    FALLBACK: Dict[str, float] = {
        "USD": 1.0,
        "HKD": 7.825,
        "MOP": 8.052,
        "CNY": 7.248,
    }
    # 官方掛鈎近似：1 HKD ≈ 1.03 MOP
    MOP_PER_HKD = 1.03

    def __init__(self):
        self._mem: Optional[dict] = None
        self._mem_ts: float = 0.0

    def get_rates(self) -> dict[str, float]:
        now = time.time()
        if self._mem and (now - self._mem_ts) < self.L1_TTL:
            return dict(self._mem)

        cache = get_cache()
        cached = cache.get(self.CACHE_KEY)
        if isinstance(cached, dict) and cached:
            self._mem = dict(cached)
            self._mem_ts = now
            return dict(self._mem)

        rates = self._fetch_rates()
        self._mem = rates
        self._mem_ts = now
        cache.set(self.CACHE_KEY, rates, ttl=self.L2_TTL)
        try:
            from src.core.fx_store import persist_daily_rates

            persist_daily_rates(rates)
        except Exception as e:
            logger.debug(f"匯率日線持久化跳過: {e}")
        return dict(rates)

    def _fetch_rates(self) -> dict[str, float]:
        rates = dict(self.FALLBACK)
        try:
            resp = requests.get(
                FRANKFURTER_LATEST,
                params={"from": self.BASE, "to": "CNY,HKD"},
                timeout=8,
            )
            resp.raise_for_status()
            data = resp.json()
            fetched = data.get("rates") or {}
            for key, val in fetched.items():
                c = str(key).upper()
                if c in self.SUPPORTED:
                    rates[c] = float(val)
            rates["USD"] = 1.0
            if "HKD" in rates:
                rates["MOP"] = round(rates["HKD"] * self.MOP_PER_HKD, 6)
            logger.info(
                f"匯率已更新 (Frankfurter): USD/HKD={rates.get('HKD')} USD/CNY={rates.get('CNY')} USD/MOP={rates.get('MOP')}"
            )
            return rates
        except Exception as e:
            logger.warning(f"匯率 API 失敗，使用兜底: {e}")
            return dict(self.FALLBACK)

    def convert(
        self,
        amount: float | Decimal,
        from_curr: str,
        to_curr: str,
        rates: Optional[dict[str, float]] = None,
    ) -> Decimal:
        """from → USD → to，全程 Decimal。"""
        from_curr = (from_curr or "CNY").upper()
        to_curr = (to_curr or "MOP").upper()
        if from_curr not in self.SUPPORTED or to_curr not in self.SUPPORTED:
            raise ValueError(f"不支援的幣種: {from_curr} → {to_curr}")
        amt = amount if isinstance(amount, Decimal) else Decimal(str(amount))
        if from_curr == to_curr:
            return amt.quantize(Decimal("0.01"))
        r = rates or self.get_rates()
        from_rate = Decimal(str(r.get(from_curr) or self.FALLBACK.get(from_curr, 1)))
        to_rate = Decimal(str(r.get(to_curr) or self.FALLBACK.get(to_curr, 1)))
        if from_rate <= 0 or to_rate <= 0:
            raise ValueError("匯率無效")
        usd_val = amt / from_rate
        return (usd_val * to_rate).quantize(Decimal("0.01"))

    def fx_updated_iso(self) -> str:
        from datetime import datetime, timezone

        return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


_service: Optional[ExchangeRateService] = None


def get_exchange_service() -> ExchangeRateService:
    global _service
    if _service is None:
        _service = ExchangeRateService()
    return _service
