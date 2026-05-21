"""
Polymarket 概率驅動策略信號 —  advisory 層，不接入 Backtrader。

依 yes 機率分檔給出偏多/偏空/觀望建議，可與預警規則聯動配置閾值。
"""
from src.config import settings
from src.core.polymarket.alert_store import load_prob_state
from src.core.polymarket.service import PolymarketDisabledError, get_polymarket_service


def _default_thresholds() -> dict:
    """可經 settings.polymarket_signal_thresholds 覆蓋。"""
    custom = getattr(settings, "polymarket_signal_thresholds", None) or {}
    base = {
        "bullish_strong": 0.75,
        "bearish_strong": 0.25,
        "neutral_low": 0.40,
        "neutral_high": 0.60,
        "momentum_min_change_pct": 5.0,
    }
    base.update(custom if isinstance(custom, dict) else {})
    return base


def classify_market(market: dict, thresholds: dict = None) -> dict:
    """
    單市場信號分類。

    返回：signal, conviction, yes_price, action_hint, rationale
    """
    thresholds = thresholds or _default_thresholds()
    yes = float(market.get("yes_price") or 0)
    key = market.get("slug") or market.get("market_id") or ""
    question = market.get("question") or key

    prev = load_prob_state(key) if key else None
    momentum_pct = None
    if prev and prev.get("yes_price"):
        old = float(prev["yes_price"])
        if old > 0:
            momentum_pct = (yes - old) / old * 100.0

    min_mom = float(thresholds.get("momentum_min_change_pct", 5.0))
    if yes >= float(thresholds["bullish_strong"]):
        signal = "bullish"
        conviction = "high"
        action_hint = "long_yes"
        rationale = f"Yes 機率 {yes*100:.1f}% ≥ 強多頭閾值"
    elif yes <= float(thresholds["bearish_strong"]):
        signal = "bearish"
        conviction = "high"
        action_hint = "long_no"
        rationale = f"Yes 機率 {yes*100:.1f}% ≤ 強空頭閾值"
    elif float(thresholds["neutral_low"]) <= yes <= float(thresholds["neutral_high"]):
        signal = "neutral"
        conviction = "low"
        action_hint = "wait"
        rationale = f"Yes 機率 {yes*100:.1f}% 處於不確定區間"
    elif yes > 0.5:
        signal = "bullish"
        conviction = "medium"
        action_hint = "lean_yes"
        rationale = f"Yes 機率 {yes*100:.1f}% 略偏多"
    else:
        signal = "bearish"
        conviction = "medium"
        action_hint = "lean_no"
        rationale = f"Yes 機率 {yes*100:.1f}% 略偏空"

    if momentum_pct is not None and abs(momentum_pct) >= min_mom:
        direction = "升" if momentum_pct > 0 else "降"
        rationale += f"；近期機率{direction} {abs(momentum_pct):.1f}%"

    return {
        "market_key": key,
        "question": question,
        "yes_price": round(yes, 4),
        "no_price": round(float(market.get("no_price") or 0), 4),
        "signal": signal,
        "conviction": conviction,
        "action_hint": action_hint,
        "momentum_pct": round(momentum_pct, 2) if momentum_pct is not None else None,
        "rationale": rationale,
        "thresholds_used": thresholds,
    }


def compute_strategy_signals(
    market_keys: list[str] = None,
    limit: int = 30,
    tag: str = None,
) -> dict:
    """
    批量計算策略信號。

    market_keys 為空時：規則表 + watchlist + 熱門市場合併去重。
    """
    from src.core.polymarket.alert_store import init_polymarket_alert_tables, list_alert_rules

    svc = get_polymarket_service()
    if not settings.polymarket_enabled:
        raise PolymarketDisabledError("Polymarket 已關閉")

    init_polymarket_alert_tables()
    keys: list[str] = []
    if market_keys:
        keys.extend([k.strip() for k in market_keys if k and str(k).strip()])

    for rule in list_alert_rules(enabled_only=True):
        mk = rule.get("market_key")
        if mk and mk not in keys:
            keys.append(mk)

    for slug in settings.polymarket_watchlist_slugs or []:
        if slug and slug not in keys:
            keys.append(slug)

    markets: list[dict] = []
    seen = set()

    for key in keys[:limit]:
        try:
            m = svc.get_market(key)
            mid = m.get("market_id") or m.get("slug")
            if mid and mid not in seen:
                seen.add(mid)
                markets.append(m)
        except Exception:
            continue

    remaining = max(0, limit - len(markets))
    if remaining > 0 and (tag or not keys):
        payload = svc.list_markets(limit=remaining, tag=tag, active=True)
        for m in payload.get("markets") or []:
            mid = m.get("market_id") or m.get("slug")
            if mid and mid not in seen:
                seen.add(mid)
                markets.append(m)

    thresholds = _default_thresholds()
    signals = [classify_market(m, thresholds) for m in markets]
    signals.sort(
        key=lambda s: (
            0 if s["conviction"] == "high" else 1 if s["conviction"] == "medium" else 2,
            -abs(s.get("momentum_pct") or 0),
        ),
    )

    return {
        "signals": signals,
        "total": len(signals),
        "thresholds": thresholds,
        "source": "polymarket_probability",
    }
