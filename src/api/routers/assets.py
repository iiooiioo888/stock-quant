"""全球資產庫 API — 目錄 + 詳情"""

from urllib.parse import unquote

import time

from fastapi import APIRouter, HTTPException, Query, Depends
from starlette.concurrency import run_in_threadpool

from src.core.market_catalog import (
    GROUP_LABELS,
    GROUP_ORDER,
    MARKET_INSTRUMENTS,
    catalog_summary,
    derive_l2,
    derive_l3,
    map_price_sources,
)
from src.utils.logger import logger
from src.core.auth import get_current_user, require_admin
from src.core.entitlements import user_assets_pro

router = APIRouter(tags=["assets"])

_INSTRUMENT_BY_SYMBOL: dict | None = None


def _instrument_index() -> dict:
    """符號 → 掛牌元數據（模組級快取）。"""
    global _INSTRUMENT_BY_SYMBOL
    if _INSTRUMENT_BY_SYMBOL is not None:
        return _INSTRUMENT_BY_SYMBOL
    idx: dict = {}
    for inst in MARKET_INSTRUMENTS:
        key = (inst.symbol or "").upper()
        if not key:
            continue
        idx[key] = inst
        if key.isdigit() and len(key) <= 6:
            idx[key.zfill(6)] = inst
    _INSTRUMENT_BY_SYMBOL = idx
    return idx


def _a_share_catalog_symbol(code: str) -> str:
    """六位 A 股代碼 → 目錄符號（600519 → 600519.SS）。"""
    c = str(code or "").strip()
    if len(c) < 6 and c.isdigit():
        c = c.zfill(6)
    if not (len(c) == 6 and c.isdigit()):
        return ""
    if c.startswith(("60", "68", "51", "52", "56", "58")):
        return f"{c}.SS"
    return f"{c}.SZ"


def _lookup_inst(symbol: str):
    sym = (symbol or "").strip()
    if not sym:
        return None
    u = sym.upper()
    candidates = [u]
    if u.isdigit() and len(u) <= 6:
        candidates.append(_a_share_catalog_symbol(u))
    idx = _instrument_index()
    for key in candidates:
        if key and key in idx:
            return idx[key]
    return None


def _fetch_exchange_price(inst) -> dict | None:
    """同步抓交易所報價（在 threadpool 中執行）。"""
    if inst.symbol.endswith((".SS", ".SZ")):
        from src.core.realtime import fetch_one_realtime

        code = inst.symbol.split(".")[0]
        q = fetch_one_realtime(code)
        if q and q.get("price", 0) > 0:
            return {
                "success": True,
                "symbol": inst.symbol,
                "name": inst.name or q.get("name") or inst.symbol,
                "market": inst.market,
                "asset_class": inst.asset_class,
                "last_price": float(q.get("price")),
                "ts": time.time(),
                "source": q.get("source") or "realtime",
                "kind": "price",
                "currency": inst.currency or "CNY",
                "pricing_note": map_price_sources(inst)[1],
            }
        return None

    from src.core.global_market import get_global_realtime

    data = get_global_realtime([inst.symbol]) or []
    q = data[0] if data else {}
    price = float(q.get("price") or 0)
    if price <= 0:
        return None
    return {
        "success": True,
        "symbol": inst.symbol,
        "name": inst.name or q.get("name") or inst.symbol,
        "market": inst.market,
        "asset_class": inst.asset_class,
        "last_price": price,
        "ts": time.time(),
        "source": q.get("source") or "global_market",
        "kind": "price",
        "currency": q.get("currency") or inst.currency,
        "pricing_note": map_price_sources(inst)[1],
    }


@router.get("/api/assets/price")
async def get_asset_price(symbol: str = Query(..., min_length=1, max_length=64)):
    """
    資產即時價/估值（P0/P1/P2 統一入口）

    - P0: 交易所可公開行情 → 走現有行情源
    - P1/P2: 銀行間/OTC → 先讀本地導入估值（合規）
    """
    from src.core.pricing_store import get_price

    sym = unquote(symbol).strip()
    inst = _lookup_inst(sym)
    if not inst:
        raise HTTPException(404, f"unknown asset: {sym}")

    # P1/P2: prefer imported valuation/price
    imported = get_price(inst.symbol)
    if imported and imported.price > 0 and imported.ts > 0:
        return {
            "success": True,
            "symbol": inst.symbol,
            "name": inst.name,
            "market": inst.market,
            "asset_class": inst.asset_class,
            "last_price": imported.price,
            "ts": imported.ts,
            "source": imported.source,
            "kind": imported.kind,
            "currency": imported.currency or inst.currency,
            "note": imported.note,
            "pricing_note": map_price_sources(inst)[1],
        }

    # P0: exchange public quotes（外網 I/O 放到執行緒，避免卡住 UI 輪詢）
    if (inst.market or "") == "exchange":
        try:
            p0 = await run_in_threadpool(_fetch_exchange_price, inst)
            if p0:
                return p0
        except Exception as e:
            logger.debug(f"asset price P0 failed {inst.symbol}: {e}")

    # No live price; return sources + hint
    sources, note = map_price_sources(inst)
    return {
        "success": False,
        "symbol": inst.symbol,
        "name": inst.name,
        "market": inst.market,
        "asset_class": inst.asset_class,
        "last_price": None,
        "ts": None,
        "source": None,
        "kind": None,
        "currency": inst.currency,
        "price_sources": sources,
        "pricing_note": note,
        "message": "暫無可用報價（可透過估值/報價導入補齊）",
    }


@router.post("/api/assets/prices/import")
async def import_asset_prices(
    body: dict,
    _user=Depends(require_admin),
):
    """
    匯入估值/OTC 報價（P1/P2）

    注意：此端點預設不做外部抓取，只接受合規來源的輸入。
    """
    from src.core.pricing_store import PriceRecord, upsert_prices

    items = body.get("records") or []
    if not isinstance(items, list) or not items:
        raise HTTPException(400, "records required")

    recs: list[PriceRecord] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        sym = str(it.get("symbol") or "").strip()
        if not sym:
            continue
        price = float(it.get("price") or 0)
        if price <= 0:
            continue
        ts = float(it.get("ts") or time.time())
        recs.append(
            PriceRecord(
                symbol=sym,
                price=price,
                ts=ts,
                source=str(it.get("source") or "manual"),
                kind=str(it.get("kind") or "valuation"),
                currency=str(it.get("currency") or ""),
                note=str(it.get("note") or ""),
                updated_by=str(it.get("updated_by") or ""),
            )
        )

    if not recs:
        raise HTTPException(400, "no valid records")
    return upsert_prices(recs)


@router.get("/api/assets/catalog")
async def get_assets_catalog(user=Depends(get_current_user)):
    """資產庫目錄（12 分組元數據）。"""
    assets_pro = user_assets_pro(user)

    def _build():
        from src.core.market_catalog import STOCK_GROUPS
        from src.core.stock_sectors import STOCK_SECTOR_LABELS, stock_sector_label
        from src.core.stock_theme_packs import (
            build_symbol_themes_map,
            count_themes_in_catalog,
            theme_packs_payload,
        )

        stock_syms = [
            i.symbol
            for i in MARKET_INSTRUMENTS
            if i.group in STOCK_GROUPS and i.asset_class == "stock"
        ]
        theme_counts = count_themes_in_catalog(stock_syms)
        theme_map = build_symbol_themes_map(stock_syms) if assets_pro else {}

        rows = []
        for i in MARKET_INSTRUMENTS:
            sector = ""
            sector_label = ""
            themes: list[str] = []
            if i.group in STOCK_GROUPS and i.asset_class == "stock":
                sector = (i.sub_class or "other").strip() or "other"
                sector_label = stock_sector_label(sector)
                if assets_pro:
                    themes = theme_map.get((i.symbol or "").upper(), [])
            l2, l2_label = derive_l2(i)
            l3, l3_label = derive_l3(i)
            price_sources, pricing_note = map_price_sources(i)
            rows.append(
                {
                    "symbol": i.symbol,
                    "name": i.name,
                    "group": i.group,
                    "group_label": GROUP_LABELS.get(i.group, i.group),
                    "asset_class": i.asset_class,
                    "sub_class": i.sub_class,
                    "sector": sector,
                    "sector_label": sector_label,
                    "themes": themes if assets_pro else [],
                    "market": i.market,
                    "exchange": i.exchange,
                    "currency": i.currency,
                    "settlement": i.settlement,
                    "regulator": i.regulator,
                    "detail_supported": bool(getattr(i, "detail_supported", True)),
                    "l2": l2,
                    "l2_label": l2_label,
                    "l3": l3,
                    "l3_label": l3_label,
                    "price_sources": price_sources,
                    "pricing_note": pricing_note,
                    "tv": i.tv,
                    "topbar": i.topbar,
                }
            )
        packs = theme_packs_payload()
        for p in packs:
            p["catalog_count"] = theme_counts.get(p["id"], 0)
            if not assets_pro:
                p["locked"] = True

        out = {
            **catalog_summary(),
            "instruments": rows,
            "sector_labels": STOCK_SECTOR_LABELS,
            "theme_packs": packs,
            "theme_pack_order": [p["id"] for p in packs],
        }
        if not assets_pro:
            out["theme_packs_locked"] = True
            out["theme_packs_upgrade_url"] = "/app#/pricing"
        return out

    # v6: 主題包元數據全員可見；instruments.themes 仍為 Pro
    cache_key = (
        "api:assets:catalog:v6:pro" if assets_pro else "api:assets:catalog:v6:base"
    )
    from src.core.api_cache import get_cached, set_cached

    hit = get_cached(cache_key)
    if hit is not None:
        return hit
    value = await run_in_threadpool(_build)
    set_cached(cache_key, value, 300)
    return value


@router.get("/api/assets/detail")
async def get_asset_detail(
    symbol: str = Query(..., min_length=1, max_length=32),
    days: int = Query(180, ge=30, le=500),
    user=Depends(get_current_user),
):
    """單資產詳情：K 線、財報、新聞與外部連結。"""
    from src.core.asset_detail import build_asset_detail

    sym = unquote(symbol).strip()
    if not sym:
        raise HTTPException(400, "symbol required")

    pro = user_assets_pro(user)
    cache_key = f"api:assets:detail:{sym}:{days}:{'pro' if pro else 'base'}"

    def _build():
        detail = build_asset_detail(sym, days, include_thesis=pro)
        if not detail:
            raise HTTPException(404, f"無法載入標的 {sym}")
        return {"success": True, "detail": detail}

    try:
        from src.core.api_cache import get_cached, set_cached

        hit = get_cached(cache_key)
        if hit is not None:
            return hit
        value = await run_in_threadpool(_build)
        set_cached(cache_key, value, 60)
        return value
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"資產詳情 {sym} 失敗: {e}")
        raise HTTPException(500, str(e)) from e
