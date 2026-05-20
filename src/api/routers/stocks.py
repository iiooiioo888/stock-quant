"""股票與市場"""
import json
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends, Query, UploadFile, File, Request
from src.config import settings
from src.core.auth import require_auth, require_admin
from src.core.db import get_conn
from src.utils.logger import logger
from src.api.constants import STOCK_NAMES
from src.api.dispatch import dispatch_async_task

router = APIRouter()

# ====== 股票 ======

@router.get("/api/stocks")
async def list_stocks():
    """獲取股票列表"""
    from src.core.api_cache import cached_response
    from src.core.db import load_all_codes

    def _build():
        codes = load_all_codes()
        stocks = []
        for code in codes:
            name = STOCK_NAMES.get(code, "")
            if not name:
                rule = settings.alert_rules.get(code, {})
                name = rule.get("name", code)
            stocks.append({"code": code, "name": name, "data_points": 0})
        return {"stocks": stocks, "total": len(stocks)}

    return cached_response("api:stocks:list", ttl=30, builder=_build)


@router.get("/api/stocks/names")
async def get_stock_names():
    """獲取股票代碼→中文名映射"""
    return {"names": STOCK_NAMES}


def _normalize_compare_code(code: str) -> str:
    """A 股代碼補零（000001）"""
    code = str(code).strip()
    if code.isdigit() and len(code) < 6:
        return code.zfill(6)
    return code


@router.post("/api/stocks/compare")
async def compare_stocks(body: dict):
    """多股收益率對比（本地優先，缺失時首次自動入庫）"""
    codes = body.get("codes", [])
    days = body.get("days", 250)
    start = body.get("start")

    if not codes:
        raise HTTPException(400, "請提供股票代碼列表")

    from src.core.local_kline import ensure_daily_kline

    result = {}
    missing = []
    for raw in codes:
        code = _normalize_compare_code(raw)
        df, _src = ensure_daily_kline(code, start_date=start, min_bars=2)
        if df.empty:
            missing.append(raw)
            continue
        if len(df) > days:
            df = df.tail(days)

        closes = df["close"].tolist()
        dates = df["date"].tolist()
        if not closes or closes[0] == 0:
            continue

        base = closes[0]
        relative = [round((c / base - 1) * 100, 2) for c in closes]
        result[code] = {
            "dates": [str(d) for d in dates],
            "relative_return": relative,
            "close": [round(float(c), 2) for c in closes],
        }

    return {
        "success": True,
        "comparison": result,
        "missing": missing,
        "loaded": len(result),
        "total": len(codes),
    }


@router.get("/api/stocks/{code}/overview")
async def get_stock_overview(code: str, lookback: int = 250):
    """單股基本數據：技術指標、區間統計、基本面摘要"""
    from src.core.api_cache import cached_response
    from src.core.result_cache import get_data_version
    from src.core.stock_basics import build_stock_overview

    code = _normalize_compare_code(code)
    lb = min(max(lookback, 20), 500)
    cache_key = f"api:overview:{code}:{lb}:{get_data_version(code)}"

    def _build():
        return build_stock_overview(code, lookback=lb)

    try:
        overview = cached_response(cache_key, ttl=30, builder=_build)
        return {"success": True, "overview": overview}
    except Exception as e:
        logger.error(f"股票概覽失敗 {code}: {e}")
        raise HTTPException(500, str(e))


@router.get("/api/strategies/params")
async def get_all_strategy_params_api():
    """全部策略默認參數與優化網格"""
    from src.core.api_cache import cached_response
    from src.core.strategy_params_meta import get_all_strategy_params

    return cached_response(
        "api:strategies:params",
        ttl=120,
        builder=lambda: {"strategies": get_all_strategy_params()},
    )


@router.get("/api/stocks/{code}/kline")
async def get_kline(code: str, start: str = None, end: str = None, limit: int = 500):
    """獲取 K 線數據（本地優先，僅首次無數據時爬取入庫）"""
    from src.core.local_kline import ensure_daily_kline, normalize_kline_code

    code = normalize_kline_code(code)
    df, source = ensure_daily_kline(code, start_date=start, end_date=end, min_bars=1)

    if df.empty:
        raise HTTPException(404, f"股票 {code} 無數據（外網拉取亦失敗）")

    if len(df) > limit:
        df = df.tail(limit)

    records = df.to_dict(orient="records")
    return {"code": code, "data": records, "count": len(records), "source": source}


@router.post("/api/stocks/download")
async def download_stocks(codes: list[str] = None):
    """下載歷史數據（異步任務）"""
    from src.core.task_manager import create_task
    from src.core.download_tasks import run_stocks_download, MARKET_NAMES

    if codes is None:
        codes = settings.watchlist

    task_params = {"codes": codes, "market": "a_share"}
    task = create_task(
        "data_download",
        task_params,
        title=f"下載 {MARKET_NAMES['a_share']}（{len(codes)} 只）",
    )
    if task.get("is_duplicate"):
        return {"success": True, "task_id": task["task_id"], "is_duplicate": True,
                "message": "相同下載任務執行中", "async": True}

    task_id = task["task_id"]
    if task.get("status") == "completed" and task.get("result"):
        return {"success": True, "task_id": task_id, "async": False,
                "from_cache": task.get("from_cache"), "result": task.get("result")}

    return dispatch_async_task(
        task_id,
        lambda: run_stocks_download(codes, task_id=task_id),
        cache_namespace=None,
    )


@router.post("/api/stocks/update")
async def incremental_update(codes: list[str] = None, force: bool = False):
    """增量更新歷史數據（異步任務）"""
    from src.core.task_manager import create_task
    from src.core.download_tasks import run_incremental

    task_params = {"codes": codes or settings.watchlist, "force": force}
    task = create_task(
        "data_incremental",
        task_params,
        title=f"增量更新 A 股（{len(task_params['codes'])} 只）",
    )
    if task.get("is_duplicate"):
        return {"success": True, "task_id": task["task_id"], "is_duplicate": True,
                "message": "相同增量任務執行中", "async": True}

    task_id = task["task_id"]
    return dispatch_async_task(
        task_id,
        lambda: run_incremental(codes=codes, force=force, task_id=task_id),
    )


# ====== 多市場支持 ======

@router.get("/api/markets")
async def list_markets():
    """獲取所有市場及標的數量"""
    from src.core.db import load_all_markets, load_all_codes_by_market
    from src.core.crypto import get_crypto_symbols
    from src.core.forex import get_forex_pairs
    from src.core.global_market import get_market_catalog

    markets = load_all_markets()

    # 基礎市場
    available = {
        "a_share": {"name": "A股", "icon": "🇨🇳", "description": "滬深 A 股"},
        "crypto": {"name": "加密貨幣", "icon": "₿", "description": "Binance 交易對"},
        "forex": {"name": "外匯", "icon": "💱", "description": "主要貨幣對"},
    }

    # 全球市場
    catalog = get_market_catalog()
    for key, cat in catalog.items():
        available[key] = {"name": cat["name"], "icon": cat["icon"], "description": f"{len(cat['symbols'])} 個標的"}

    result = []
    for mkt_key, info in available.items():
        count = next((m["count"] for m in markets if m["market"] == mkt_key), 0)
        result.append({
            "market": mkt_key,
            "name": info.get("name", mkt_key),
            "icon": info.get("icon", ""),
            "description": info.get("description", ""),
            "data_count": count,
        })

    return {"markets": result}


@router.get("/api/markets/{market}/symbols")
async def list_market_symbols(market: str):
    """獲取指定市場的可用標的列表"""
    from src.core.db import load_all_codes_by_market
    from src.core.crypto import get_crypto_symbols
    from src.core.forex import get_forex_pairs
    from src.core.global_market import get_market_catalog

    catalog = get_market_catalog()

    if market == "crypto":
        symbols = get_crypto_symbols()
        existing = set(load_all_codes_by_market("crypto"))
        result = [{"code": k, "name": v, "has_data": k in existing} for k, v in symbols.items()]
        return {"market": market, "symbols": result, "total": len(result)}

    elif market == "forex":
        pairs = get_forex_pairs()
        existing = set(load_all_codes_by_market("forex"))
        result = [{"code": k, "name": v, "has_data": k in existing} for k, v in pairs.items()]
        return {"market": market, "symbols": result, "total": len(result)}

    elif market in catalog:
        cat = catalog[market]
        existing = set(load_all_codes_by_market(market))
        result = [{"code": k, "name": v, "has_data": k in existing} for k, v in cat["symbols"].items()]
        return {"market": market, "symbols": result, "total": len(result)}

    else:
        codes = load_all_codes_by_market("a_share")
        result = [{"code": c, "name": STOCK_NAMES.get(c, c), "has_data": True} for c in codes]
        return {"market": market, "symbols": result, "total": len(result)}


def _resolve_market_codes(market: str, codes: list[str] = None) -> list[str]:
    from src.core.global_market import MARKET_CATALOG

    if codes:
        return codes
    if market == "crypto":
        return list(settings.crypto_watchlist)
    if market == "forex":
        return list(settings.forex_watchlist)
    if market in MARKET_CATALOG:
        return list(MARKET_CATALOG[market]["symbols"].keys())
    return list(settings.watchlist)


@router.post("/api/markets/{market}/download")
async def download_market_data(market: str, body: list | dict | None = None):
    """下載指定市場的歷史數據（異步任務）"""
    from src.core.task_manager import create_task
    from src.core.download_tasks import run_market_download, MARKET_NAMES

    codes = None
    if isinstance(body, list):
        codes = body
    elif isinstance(body, dict):
        codes = body.get("codes")
    codes = _resolve_market_codes(market, codes)
    market_name = MARKET_NAMES.get(market, market)
    task_params = {"market": market, "codes": codes}
    task = create_task(
        "data_download",
        task_params,
        title=f"下載 {market_name}（{len(codes)} 個標的）",
    )
    if task.get("is_duplicate"):
        return {"success": True, "task_id": task["task_id"], "is_duplicate": True,
                "message": "相同下載任務執行中", "async": True}

    task_id = task["task_id"]
    return dispatch_async_task(
        task_id,
        lambda: run_market_download(market, codes, task_id=task_id),
    )


@router.post("/api/download-all")
async def download_all_markets():
    """批量下載所有市場數據（異步任務）"""
    from src.core.task_manager import create_task
    from src.core.download_tasks import run_download_all

    task_params = {"scope": "all_markets"}
    task = create_task("data_download_all", task_params, title="下載全市場數據")
    if task.get("is_duplicate"):
        return {"success": True, "task_id": task["task_id"], "is_duplicate": True,
                "message": "全市場下載任務執行中", "async": True}

    task_id = task["task_id"]
    return dispatch_async_task(
        task_id,
        lambda: run_download_all(task_id=task_id),
    )


@router.get("/api/markets/{market}/realtime")
async def get_market_realtime(market: str, symbols: str = None):
    """獲取指定市場的實時行情"""
    if market == "crypto":
        from src.core.crypto import get_crypto_multi_realtime
        sym_list = symbols.split(",") if symbols else settings.crypto_watchlist
        data = get_crypto_multi_realtime(sym_list)
        return {"market": "crypto", "data": data}

    elif market == "forex":
        from src.core.forex import get_forex_multi_realtime
        sym_list = symbols.split(",") if symbols else settings.forex_watchlist
        data = get_forex_multi_realtime(sym_list)
        return {"market": "forex", "data": data}

    elif market in ("us_stock", "hk_stock", "index", "etf", "commodity"):
        from src.core.global_market import get_global_realtime, MARKET_CATALOG
        if symbols:
            sym_list = symbols.split(",")
        else:
            cat = MARKET_CATALOG.get(market, {})
            sym_list = list(cat.get("symbols", {}).keys())[:20]
        data = get_global_realtime(sym_list)
        return {"market": market, "data": data}

    else:
        raise HTTPException(400, f"不支持的實時市場: {market}")


@router.get("/api/sparkline")
async def get_sparkline(codes: str, days: int = 30):
    """
    獲取多個標的的迷你走勢圖數據（最近 N 天收盤價）。
    多源降級：本地庫 → Yahoo → 東財 → Twelve Data。
    """
    from src.core.market_fetch import build_sparkline_item

    code_list = [c.strip() for c in codes.split(",") if c.strip()]
    result = {code: build_sparkline_item(code, days) for code in code_list}
    return {"sparklines": result}
