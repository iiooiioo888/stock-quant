"""
Polymarket 響應正規化 — 將 Gamma/CLOB 原始 JSON 映射為穩定內部結構。

內部字段名與 REST/MCP 輸出一致，便於前端與 Agent 消費。
"""
import json
from typing import Any, Optional


def _safe_float(v: Any, default: float = 0.0) -> float:
    """安全轉浮點，無效值返回 default。"""
    if v is None or v == "":
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _parse_json_list(raw: Any) -> list:
    """解析 API 中常見的 JSON 字符串列表（如 outcomes、clobTokenIds）。"""
    if raw is None:
        return []
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []
    return []


def normalize_market(raw: dict) -> dict:
    """
    將 Gamma /markets 單條記錄轉為內部市場摘要。

    返回字段：market_id, slug, question, condition_id, yes_price, no_price,
    volume, liquidity, active, closed, end_date, outcomes, token_ids, image, source
    """
    outcomes = _parse_json_list(raw.get("outcomes"))
    prices = _parse_json_list(raw.get("outcomePrices") or raw.get("outcome_prices"))
    token_ids = _parse_json_list(raw.get("clobTokenIds") or raw.get("clob_token_ids"))

    yes_price = 0.0
    no_price = 0.0
    if len(prices) >= 2:
        yes_price = _safe_float(prices[0])
        no_price = _safe_float(prices[1])
    elif len(prices) == 1:
        yes_price = _safe_float(prices[0])
        no_price = max(0.0, 1.0 - yes_price)

    return {
        "market_id": str(raw.get("id") or raw.get("conditionId") or raw.get("condition_id") or ""),
        "slug": raw.get("slug") or "",
        "question": raw.get("question") or raw.get("title") or "",
        "condition_id": raw.get("conditionId") or raw.get("condition_id") or "",
        "yes_price": round(yes_price, 4),
        "no_price": round(no_price, 4),
        "volume": _safe_float(raw.get("volume") or raw.get("volumeNum")),
        "liquidity": _safe_float(raw.get("liquidity") or raw.get("liquidityNum")),
        "active": bool(raw.get("active", True)),
        "closed": bool(raw.get("closed", False)),
        "end_date": raw.get("endDate") or raw.get("end_date_iso") or "",
        "outcomes": outcomes,
        "token_ids": [str(t) for t in token_ids],
        "image": raw.get("image") or "",
        "source": "gamma",
    }


def normalize_event(raw: dict) -> dict:
    """Gamma 事件摘要。"""
    return {
        "event_id": str(raw.get("id") or ""),
        "slug": raw.get("slug") or "",
        "title": raw.get("title") or "",
        "description": (raw.get("description") or "")[:500],
        "active": bool(raw.get("active", True)),
        "closed": bool(raw.get("closed", False)),
        "start_date": raw.get("startDate") or "",
        "end_date": raw.get("endDate") or "",
        "market_count": len(raw.get("markets") or []),
    }


def normalize_tag(raw: dict) -> dict:
    """Gamma 標籤。"""
    if isinstance(raw, str):
        return {"tag_id": raw, "label": raw, "slug": raw}
    return {
        "tag_id": str(raw.get("id") or raw.get("slug") or ""),
        "label": raw.get("label") or raw.get("name") or "",
        "slug": raw.get("slug") or "",
    }


def normalize_orderbook(raw: dict, token_id: str, depth: int = 10) -> dict:
    """
    CLOB 訂單簿正規化，計算 best bid/ask、價差與中間價。

    CLOB /book 返回 bids/asks，每檔為 {price, size}。
    """
    bids_raw = raw.get("bids") or []
    asks_raw = raw.get("asks") or []

    def _levels(side: list) -> list[dict]:
        out = []
        for row in side[:depth]:
            if isinstance(row, dict):
                p, s = row.get("price"), row.get("size")
            elif isinstance(row, (list, tuple)) and len(row) >= 2:
                p, s = row[0], row[1]
            else:
                continue
            out.append({"price": _safe_float(p), "size": _safe_float(s)})
        return out

    bids = _levels(bids_raw)
    asks = _levels(asks_raw)

    best_bid = bids[0]["price"] if bids else 0.0
    best_ask = asks[0]["price"] if asks else 0.0
    spread = round(best_ask - best_bid, 6) if best_bid and best_ask else 0.0
    mid = round((best_bid + best_ask) / 2, 6) if best_bid and best_ask else 0.0

    return {
        "token_id": token_id,
        "bids": bids,
        "asks": asks,
        "best_bid": best_bid,
        "best_ask": best_ask,
        "spread": spread,
        "mid": mid,
        "depth": depth,
        "source": "clob",
    }


def normalize_price_point(raw: dict) -> Optional[dict]:
    """CLOB 價格歷史單點：ts + price。"""
    ts = raw.get("t") or raw.get("timestamp") or raw.get("time")
    price = raw.get("p") or raw.get("price")
    if ts is None and price is None:
        return None
    return {
        "ts": int(ts) if ts is not None else 0,
        "price": _safe_float(price),
    }


def normalize_search_hit(raw: dict) -> dict:
    """搜尋結果條目（市場或事件）。"""
    kind = "market"
    if raw.get("type"):
        kind = str(raw.get("type")).lower()
    elif raw.get("markets") is not None:
        kind = "event"
    if kind == "event" or raw.get("title") and not raw.get("question"):
        ev = normalize_event(raw)
        ev["result_type"] = "event"
        return ev
    m = normalize_market(raw)
    m["result_type"] = "market"
    return m
