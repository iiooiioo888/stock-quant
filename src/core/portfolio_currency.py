"""持倉幣種推斷 — 供結算與流水遷移共用。"""

from __future__ import annotations


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
        if market in (
            "us_stock",
            "global",
            "crypto",
            "forex",
            "forex_yahoo",
            "commodity",
            "index",
        ):
            return "USD"
        if market in ("forex",):
            return "USD"
    except Exception:
        pass
    if c.isalpha() and len(c) <= 5 and not c.isdigit():
        return "USD"
    return "CNY"
