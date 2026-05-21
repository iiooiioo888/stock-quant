"""
依股票代碼/名稱搜尋 Polymarket 相關預測市場。
"""
from __future__ import annotations

import re
from typing import Optional

from src.api.constants import STOCK_NAMES


def resolve_stock_name(code: str, name: Optional[str] = None) -> str:
    code = str(code or "").strip()
    name = (name or "").strip() or STOCK_NAMES.get(code, "") or code
    return name


def build_polymarket_search_queries(code: str, name: Optional[str] = None) -> list[str]:
    """產生去重後的搜尋關鍵字列表（繁中名、代碼、簡稱）。"""
    code = str(code or "").strip()
    name = resolve_stock_name(code, name)
    queries: list[str] = []

    def add(q: str) -> None:
        q = re.sub(r"\s+", " ", (q or "").strip())
        if len(q) < 2:
            return
        if q not in queries:
            queries.append(q)

    if name and name.upper() != code.upper():
        add(name)
    if code:
        add(code)

    for suffix in ("股份有限公司", "有限公司", "控股", "集团", "集團", "股份"):
        if name.endswith(suffix) and len(name) > len(suffix) + 1:
            add(name[: -len(suffix)])

    # A 股常見簡稱（前兩字）
    if re.fullmatch(r"\d{6}", code) and len(name) >= 4 and name not in queries:
        add(name[:2])

    return queries[:6]


def search_polymarket_for_stock(
    code: str,
    name: Optional[str] = None,
    limit_per_query: int = 8,
    max_results: int = 20,
) -> dict:
    """
    對多個關鍵字搜尋 Polymarket，合併去重市場列表。
    返回 { queries, markets, disabled, error }
    """
    from src.core.polymarket.service import PolymarketDisabledError, get_polymarket_service

    queries = build_polymarket_search_queries(code, name)
    if not queries:
        return {"queries": [], "markets": [], "disabled": False, "error": None}

    try:
        svc = get_polymarket_service()
    except PolymarketDisabledError as e:
        return {"queries": queries, "markets": [], "disabled": True, "error": str(e)}

    seen: set[str] = set()
    markets: list[dict] = []
    for q in queries:
        try:
            payload = svc.search(q, limit=limit_per_query)
            for hit in payload.get("results") or []:
                if hit.get("result_type") == "event":
                    continue
                key = hit.get("slug") or hit.get("market_id") or hit.get("question")
                if not key or key in seen:
                    continue
                seen.add(key)
                markets.append(hit)
                if len(markets) >= max_results:
                    break
        except Exception:
            continue
        if len(markets) >= max_results:
            break

    return {"queries": queries, "markets": markets, "disabled": False, "error": None}
