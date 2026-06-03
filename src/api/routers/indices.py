"""全球主要指數 K 線 API（儀表盤首頁）"""
from concurrent.futures import ThreadPoolExecutor, as_completed

from fastapi import APIRouter, HTTPException, Query

from src.core.market_catalog import (
    GROUP_LABELS,
    GROUP_ORDER,
    MARKET_INSTRUMENTS,
    VALID_SCOPES,
    catalog_summary,
    instruments_by_group,
    instruments_for_charts,
)
from src.core.market_fetch import build_index_chart_item
from src.utils.logger import logger

router = APIRouter(tags=["indices"])

HOME_INDICES = [(i.symbol, i.name) for i in MARKET_INSTRUMENTS]


@router.get("/api/indices/charts")
async def get_indices_charts(
    days: int = Query(90, ge=1, le=365),
    scope: str = Query("all"),
    symbols: str | None = Query(None, description="custom scope symbols, comma-separated"),
):
    """
    全球掛牌：IB → TradingView → Yahoo / 東財 / Twelve Data。
    scope: dashboard | all | tradeable | topbar | stocks | 任一分組 id（asia / hk_stock …）
    dashboard：儀表盤核心掛牌（~80，不含三地個股 bulk）；all/tradeable 為全部可行情標的。
    完整元數據見 /api/indices/catalog。topbar 允許 1–14 日（頂欄輕量）；其餘 scope 至少 30 日。
    """
    if scope not in VALID_SCOPES:
        raise HTTPException(400, detail=f"invalid scope; use one of: {sorted(VALID_SCOPES)}")

    if scope in ("topbar", "custom"):
        days = min(max(days, 1), 14)
    else:
        days = max(days, 30)

    from src.core.api_cache import cached_response

    def _pick_instruments():
        return instruments_for_charts(scope, symbols)

    sym_key = (symbols or "").strip().upper()[:120] if scope == "custom" else ""
    cache_key = f"api:indices:charts:{days}:{scope}:{sym_key}"

    def _build():
        from src.core.data_pipeline import flush_deferred_data_cache_clear

        instruments = _pick_instruments()
        indices = []
        workers = min(12, max(4, len(instruments) // 8 + 4))
        try:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {
                    pool.submit(build_index_chart_item, inst.symbol, inst.name, days): inst
                    for inst in instruments
                }
                for fut in as_completed(futures):
                    inst = futures[fut]
                    try:
                        item = fut.result()
                        if item:
                            item.setdefault("group", inst.group)
                            item.setdefault("topbar", inst.topbar)
                            item.setdefault("asset_class", inst.asset_class)
                            indices.append(item)
                    except Exception as e:
                        logger.debug(f"標的 {inst.symbol} 載入失敗: {e}")
        finally:
            flush_deferred_data_cache_clear()

        order = {i.symbol: n for n, i in enumerate(MARKET_INSTRUMENTS)}
        indices.sort(key=lambda x: order.get(x["symbol"], 999))

        max_kline_pts = 32
        for item in indices:
            kl = item.get("kline")
            if isinstance(kl, list) and len(kl) > max_kline_pts:
                item["kline"] = kl[-max_kline_pts:]

        groups: dict[str, dict] = {}
        for gid in GROUP_ORDER:
            items = [dict(i) for i in indices if i.get("group") == gid]
            if items:
                groups[gid] = {
                    "id": gid,
                    "label": GROUP_LABELS.get(gid, gid),
                    "items": items,
                }

        sources_used = sorted({i.get("source", "") for i in indices if i.get("source")})
        return {
            "indices": indices,
            "groups": groups,
            "group_order": GROUP_ORDER,
            "group_labels": GROUP_LABELS,
            "days": days,
            "count": len(indices),
            "requested": len(instruments),
            "scope": scope,
            "sources": sources_used,
            "providers": _provider_status(indices),
        }

    ttl = 45 if scope == "topbar" else 120
    return cached_response(cache_key, ttl=ttl, builder=_build)


def _provider_status(indices: list) -> dict:
    tv_count = sum(1 for i in indices if "TradingView" in (i.get("source") or ""))
    ib_count = sum(
        1 for i in indices
        if i.get("source") == "IB" or str(i.get("source", "")).startswith("IB")
    )

    tv_probe = {"ok": False}
    ib_st = {"ok": False, "enabled": False}
    try:
        from src.config import settings

        if getattr(settings, "tradingview_enabled", True):
            from src.core.tradingview_data import tv_health_probe

            tv_probe = tv_health_probe()
    except Exception:
        pass

    try:
        from src.core.ib_data import ib_status

        ib_st = ib_status(probe=True)
        ib_st["quotes"] = ib_count
    except Exception:
        ib_st = {"ok": False, "reason": "error"}

    return {
        "tradingview": {
            "ok": tv_probe.get("ok", False) or tv_count > 0,
            "quotes": tv_count,
            "probe": tv_probe,
        },
        "ib": {**ib_st, "quotes": ib_count},
    }


@router.get("/api/indices/providers")
async def get_indices_providers():
    """TradingView / IB 狀態 + 全球目錄摘要。"""
    tv = {"ok": False}
    ib = {"ok": False}
    try:
        from src.core.tradingview_data import tv_health_probe

        tv = tv_health_probe()
    except Exception:
        pass
    try:
        from src.core.ib_data import ib_status

        ib = ib_status(probe=True)
    except Exception:
        pass

    summary = catalog_summary()
    return {
        "catalog_size": summary["total"],
        "topbar_size": summary["topbar"],
        "groups": summary["groups"],
        "asset_classes": summary["asset_classes"],
        "group_order": summary["group_order"],
        "group_labels": summary["group_labels"],
        "tradingview": tv,
        "ib": ib,
    }


@router.get("/api/indices/catalog")
async def get_indices_catalog():
    """完整掛牌目錄（元數據，不含行情）。"""
    return {
        "instruments": [
            {
                "symbol": i.symbol,
                "name": i.name,
                "group": i.group,
                "asset_class": i.asset_class,
                "tv": i.tv,
                "topbar": i.topbar,
            }
            for i in MARKET_INSTRUMENTS
        ],
        **catalog_summary(),
    }
