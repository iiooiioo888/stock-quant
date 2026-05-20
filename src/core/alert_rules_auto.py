"""
根據最新價自動生成預警規則（突破/跌破/漲跌幅閾值）
"""
from __future__ import annotations

from src.api.constants import STOCK_NAMES
from src.config import settings
from src.utils.logger import logger


def round_price(price: float) -> float:
    if price >= 1000:
        return round(price, 1)
    if price >= 100:
        return round(price, 2)
    return round(price, 3)


def build_rule_from_price(
    code: str,
    price: float,
    *,
    name: str = "",
    above_pct: float = 3.0,
    below_pct: float = 3.0,
    change_pct: float = 5.0,
) -> dict:
    if not price or price <= 0:
        raise ValueError(f"股票 {code} 無有效價格")
    display = (
        name
        or settings.alert_rules.get(code, {}).get("name")
        or STOCK_NAMES.get(code)
        or code
    )
    return {
        "name": display,
        "price_above": round_price(price * (1 + above_pct / 100)),
        "price_below": round_price(price * (1 - below_pct / 100)),
        "change_pct": float(change_pct),
    }


def _resolve_name(code: str, quote: dict | None = None) -> str:
    if quote and quote.get("name"):
        return str(quote["name"])
    return (
        settings.alert_rules.get(code, {}).get("name")
        or STOCK_NAMES.get(code)
        or code
    )


def fetch_latest_prices(codes: list[str]) -> dict[str, dict]:
    """返回 {code: {price, name, source}}"""
    codes = [str(c).strip() for c in codes if str(c).strip()]
    if not codes:
        return {}

    out: dict[str, dict] = {}

    try:
        from src.core.realtime import fetch_realtime

        df = fetch_realtime(codes)
        if df is not None and not df.empty:
            for row in df.to_dict(orient="records"):
                code = str(row.get("code", "")).strip()
                price = float(row.get("price") or 0)
                if code and price > 0:
                    out[code] = {
                        "price": price,
                        "name": row.get("name") or _resolve_name(code),
                        "source": "realtime",
                    }
    except Exception as e:
        logger.debug(f"實時行情批量取價失敗: {e}")

    missing = [c for c in codes if c not in out]
    if missing:
        from src.core.market_fetch import build_sparkline_item

        for code in missing:
            try:
                sp = build_sparkline_item(code, days=30)
                latest = float(sp.get("latest") or 0)
                if latest > 0:
                    out[code] = {
                        "price": latest,
                        "name": _resolve_name(code),
                        "source": sp.get("source") or "kline",
                    }
            except Exception as e:
                logger.debug(f"走勢取價失敗 {code}: {e}")

    return out


def resolve_target_codes(
    *,
    codes: list[str] | None = None,
    source: str = "missing",
) -> list[str]:
    if codes:
        return [str(c).strip() for c in codes if str(c).strip()]

    wl = list(settings.watchlist or [])
    existing = set(settings.alert_rules.keys())

    if source == "watchlist":
        return wl
    if source == "config":
        return list(settings.alert_rules.keys())
    # missing: 監控列表中尚未配置規則的代碼；若為空則用整個 watchlist
    missing = [c for c in wl if c not in existing]
    return missing if missing else wl


def auto_add_alert_rules(
    *,
    codes: list[str] | None = None,
    source: str = "missing",
    above_pct: float = 3.0,
    below_pct: float = 3.0,
    change_pct: float = 5.0,
    skip_existing: bool = True,
    overwrite: bool = False,
) -> dict:
    target = resolve_target_codes(codes=codes, source=source)
    if not target:
        return {
            "success": True,
            "added": [],
            "skipped": [],
            "failed": [],
            "rules": settings.alert_rules,
            "message": "沒有可添加的股票代碼",
        }

    prices = fetch_latest_prices(target)
    added: list[str] = []
    skipped: list[str] = []
    failed: list[dict] = []

    for code in target:
        if skip_existing and not overwrite and code in settings.alert_rules:
            skipped.append(code)
            continue

        quote = prices.get(code)
        if not quote:
            failed.append({"code": code, "error": "無法取得最新價"})
            continue

        try:
            rule = build_rule_from_price(
                code,
                quote["price"],
                name=quote.get("name", ""),
                above_pct=above_pct,
                below_pct=below_pct,
                change_pct=change_pct,
            )
            settings.alert_rules[code] = rule
            if code not in settings.watchlist:
                settings.watchlist.append(code)
            added.append(code)
        except ValueError as e:
            failed.append({"code": code, "error": str(e)})

    return {
        "success": True,
        "added": added,
        "skipped": skipped,
        "failed": failed,
        "rules": settings.alert_rules,
        "message": f"已添加 {len(added)} 條規則"
        + (f"，跳過 {len(skipped)} 條" if skipped else "")
        + (f"，失敗 {len(failed)} 條" if failed else ""),
    }


def suggest_alert_rule(
    code: str,
    *,
    above_pct: float = 3.0,
    below_pct: float = 3.0,
    change_pct: float = 5.0,
) -> dict:
    code = str(code).strip()
    if len(code) != 6 or not code.isdigit():
        raise ValueError("股票代碼必須為 6 位數字")

    prices = fetch_latest_prices([code])
    quote = prices.get(code)
    if not quote:
        raise ValueError(f"無法取得 {code} 的最新價")

    rule = build_rule_from_price(
        code,
        quote["price"],
        name=quote.get("name", ""),
        above_pct=above_pct,
        below_pct=below_pct,
        change_pct=change_pct,
    )
    return {
        "code": code,
        "price": quote["price"],
        "source": quote.get("source", ""),
        "rule": rule,
    }
