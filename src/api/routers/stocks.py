"""股票與市場"""
import json
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends, Query, UploadFile, File, Request
from fastapi.responses import Response
from src.config import settings
from src.core.auth import require_auth, require_admin, get_current_user
from src.core.db import get_conn
from src.utils.logger import logger
from src.api.constants import STOCK_NAMES
from src.api.dispatch import dispatch_async_task

router = APIRouter()


# ====== 股票庫 ======

@router.get("/api/stock-universe/stats")
async def stock_universe_stats():
    """股票庫統計"""
    from src.core.stock_universe import get_universe_stats
    return get_universe_stats()


@router.get("/api/stock-universe")
async def stock_universe_list(
    market: str = Query("all", description="a_share / hk_stock / us_stock / all"),
    keyword: str = Query(None),
    limit: int = Query(50, ge=1, le=20000),
    offset: int = Query(0, ge=0),
    order_by: str = Query("rank_mv"),
):
    """按市值排名查詢股票庫"""
    from src.core.stock_universe import query_stock_universe

    rows, total = query_stock_universe(
        market=market if market != "all" else None,
        keyword=keyword,
        limit=limit,
        offset=offset,
        order_by=order_by,
    )
    return {
        "stocks": rows,
        "total": total,
        "limit": limit,
        "offset": offset,
        "order_by": order_by,
    }


@router.post("/api/stock-universe/sync")
async def stock_universe_sync(
    max_count: int = Query(None, ge=100, le=50000),
    user=Depends(require_auth),
):
    """同步股票庫（異步任務，需登錄）"""
    from src.core.task_manager import create_task
    from src.core.stock_universe import sync_stock_universe

    cap = max_count or settings.stock_universe_max_count
    task_params = {"max_count": cap}
    task = create_task(
        "stock_universe_sync",
        task_params,
        title=f"同步股票庫（前 {cap} 市值）",
    )
    if task.get("is_duplicate"):
        return {
            "success": True,
            "task_id": task["task_id"],
            "is_duplicate": True,
            "message": "相同同步任務執行中",
            "async": True,
        }

    task_id = task["task_id"]
    return dispatch_async_task(
        task_id,
        lambda: sync_stock_universe(max_count=cap, task_id=task_id),
    )


@router.post("/api/stock-universe/enrich-intros")
async def stock_universe_enrich_intros(
    limit: int = Query(None, ge=0, le=20000),
    user=Depends(require_auth),
):
    """補充股票庫簡介（異步任務，需登錄）"""
    from src.core.task_manager import create_task
    from src.core.stock_universe import enrich_universe_intros

    cap = limit if limit is not None else settings.stock_universe_intro_enrich_limit
    task_params = {"limit": cap}
    task = create_task(
        "stock_universe_intro",
        task_params,
        title=f"補充股票簡介（前 {cap} 檔）",
    )
    if task.get("is_duplicate"):
        return {
            "success": True,
            "task_id": task["task_id"],
            "is_duplicate": True,
            "message": "相同簡介補充任務執行中",
            "async": True,
        }

    task_id = task["task_id"]
    return dispatch_async_task(
        task_id,
        lambda: enrich_universe_intros(limit=cap, task_id=task_id),
    )


# ====== 股票 Logo（下載至 data/stock_logos/，API 僅讀本地） ======

def _stock_logo_response(code: str, market: str = "", name: str = "") -> Response:
    from src.core.stock_logo import read_cached_logo, schedule_logo_fetch

    c = str(code).strip()
    if not c:
        raise HTTPException(400, "code required")
    hit = read_cached_logo(c, market)
    if not hit:
        from src.config import settings

        if settings.stock_logo_api_enabled:
            schedule_logo_fetch(c, market, name=name)
            raise HTTPException(
                404,
                "logo not cached yet",
                headers={"Retry-After": "30", "X-Logo-Status": "pending"},
            )
        raise HTTPException(
            404,
            "stock logo fetch disabled",
            headers={"X-Logo-Status": "disabled"},
        )
    body, media_type = hit
    return Response(
        content=body,
        media_type=media_type,
        headers={"Cache-Control": "public, max-age=604800", "X-Logo-Status": "hit"},
    )


@router.get("/api/iconfont/config")
async def get_iconfont_config():
    """iconfont.cn 前端載入設定（Symbol JS、代碼映射）。"""
    from src.core.iconfont_assets import public_config

    return public_config()


@router.get("/api/stock-logo/{code}")
async def get_stock_logo(
    code: str,
    market: str = Query("", description="a_share / hk_stock / us_stock"),
    name: str = Query("", description="公司名稱，用於 iconfont 名稱映射"),
):
    """回傳已快取 Logo；未命中時背景下載，避免列表大量並發拖垮服務。"""
    return _stock_logo_response(code, market, name)


@router.post("/api/stock-logos/sync")
async def sync_stock_logos(
    _user=Depends(require_admin),
    market: str = Query("all", description="a_share / hk_stock / us_stock / all"),
    limit: int = Query(2000, ge=1, le=20000),
    skip_existing: bool = Query(True),
):
    """批次將股票 Logo 下載至伺服器（管理員）。"""
    from src.core.db import load_all_codes, load_all_codes_by_market
    from src.core.stock_logo import sync_logos_batch
    from src.core.stock_universe import query_stock_universe

    codes: list[str] = []
    code_markets: dict[str, str] = {}
    m = (market or "all").strip().lower()
    if m in ("all", ""):
        try:
            rows, _ = query_stock_universe(limit=limit, offset=0)
            for r in rows:
                c = r.get("code")
                if not c:
                    continue
                codes.append(c)
                code_markets[c] = r.get("market") or ""
        except Exception:
            codes = []
        if not codes:
            codes = load_all_codes()[:limit]
    else:
        codes = load_all_codes_by_market(m)[:limit]
        if not codes:
            try:
                rows, _ = query_stock_universe(market=m, limit=limit, offset=0)
                for r in rows:
                    c = r.get("code")
                    if not c:
                        continue
                    codes.append(c)
                    code_markets[c] = r.get("market") or m
            except Exception:
                codes = []
        else:
            code_markets = {c: m for c in codes}

    return sync_logos_batch(
        codes,
        market=m if m not in ("all", "") else "",
        code_markets=code_markets or None,
        skip_existing=skip_existing,
    )


# ====== 股票 ======

@router.get("/api/stocks")
async def list_stocks(limit: int = Query(500, ge=1, le=20000)):
    """獲取股票列表（默認從 stock_universe 按市值排名，limit 最大 20000）"""
    from src.core.api_cache import cached_response
    from src.core.db import load_all_codes

    cap = min(limit, 20000)

    def _build():
        from src.core.stock_universe import query_stock_universe, get_universe_stats

        stats = get_universe_stats()
        if stats.get("total", 0) > 0:
            rows, total = query_stock_universe(market=None, limit=cap, offset=0)
            stocks = [
                {
                    "code": r["code"],
                    "name": r.get("name") or STOCK_NAMES.get(r["code"], r["code"]),
                    "market": r.get("market", "a_share"),
                    "total_mv": r.get("total_mv"),
                    "rank_mv": r.get("rank_mv"),
                    "price": r.get("price"),
                    "change_pct": r.get("change_pct"),
                    "pe_ttm": r.get("pe_ttm"),
                    "pb": r.get("pb"),
                    "industry": r.get("industry") or "",
                    "intro": r.get("intro") or "",
                    "data_points": 0,
                }
                for r in rows
            ]
            return {
                "stocks": stocks,
                "total": total,
                "limit": cap,
                "source": "stock_universe",
            }

        codes = load_all_codes()
        stocks = []
        for code in codes[:cap]:
            name = STOCK_NAMES.get(code, "")
            if not name:
                rule = settings.alert_rules.get(code, {})
                name = rule.get("name", code)
            stocks.append({"code": code, "name": name, "data_points": 0})
        return {
            "stocks": stocks,
            "total": len(codes),
            "limit": cap,
            "source": "daily_kline",
        }

    return cached_response(f"api:stocks:list:{cap}", ttl=30, builder=_build)


@router.get("/api/stocks/names")
async def get_stock_names():
    """獲取股票代碼→中文名映射"""
    return {"names": STOCK_NAMES}


def _normalize_compare_code(code: str) -> str:
    """多市場代碼正規化（A 股補零；港股/美股等保留 Yahoo/IB 格式）"""
    from src.core.history import detect_market
    from src.core.local_kline import normalize_kline_code

    raw = str(code or "").strip().upper()
    if not raw:
        return raw
    if raw.isdigit() and len(raw) < 6:
        return raw.zfill(6)
    mkt = detect_market(raw)
    if mkt == "a_share" and raw.replace(".", "").isdigit():
        return normalize_kline_code(raw)
    if raw.endswith(".HK"):
        num = raw[:-3].replace(".", "")
        if num.isdigit():
            return f"{num.zfill(4)}.HK"
        return raw
    return raw


def _compare_daily_returns(closes: list) -> list[float]:
    out: list[float] = []
    for i in range(1, len(closes)):
        prev = float(closes[i - 1]) if closes[i - 1] else 0.0
        cur = float(closes[i]) if closes[i] else 0.0
        out.append((cur / prev - 1.0) if prev else 0.0)
    return out


def _compare_max_drawdown_pct(closes: list) -> float:
    if len(closes) < 2:
        return 0.0
    peak = float(closes[0]) or 1.0
    max_dd = 0.0
    for raw in closes:
        v = float(raw)
        if v > peak:
            peak = v
        if peak > 0:
            max_dd = max(max_dd, ((peak - v) / peak) * 100)
    return round(max_dd, 2)


def _compare_series_stats(closes: list) -> dict:
    if len(closes) < 2 or not closes[0]:
        return {}
    base = float(closes[0])
    last = float(closes[-1])
    total_return_pct = round((last / base - 1) * 100, 2)
    daily = _compare_daily_returns(closes)
    vol_pct = 0.0
    if len(daily) >= 2:
        mean = sum(daily) / len(daily)
        var = sum((x - mean) ** 2 for x in daily) / (len(daily) - 1)
        import math

        vol_pct = round(math.sqrt(var) * math.sqrt(252) * 100, 2)
    n = max(len(daily), 1)
    annual_return_pct = round(((last / base) ** (252 / n) - 1) * 100, 2) if base > 0 else 0.0
    return {
        "total_return_pct": total_return_pct,
        "annual_return_pct": annual_return_pct,
        "volatility_pct": vol_pct,
        "max_drawdown_pct": _compare_max_drawdown_pct(closes),
    }


def _compare_align_daily_returns(comparison: dict) -> dict[str, list[float]]:
    codes = [c for c in comparison if comparison[c].get("close")]
    if len(codes) < 2:
        return {}
    date_sets = [set(comparison[c]["dates"]) for c in codes]
    common = sorted(set.intersection(*date_sets))
    if len(common) < 3:
        return {}
    out: dict[str, list[float]] = {}
    for code in codes:
        dc = dict(zip(comparison[code]["dates"], comparison[code]["close"]))
        closes = [float(dc[d]) for d in common]
        out[code] = _compare_daily_returns(closes)
    return out


def _compare_correlation_matrix(comparison: dict) -> dict:
    aligned = _compare_align_daily_returns(comparison)
    codes = list(aligned.keys())
    n = len(codes)
    if n < 2:
        return {"codes": codes, "matrix": [], "sample_days": 0}

    def _pearson(a: list[float], b: list[float]) -> float | None:
        m = len(a)
        if m < 2:
            return None
        ma = sum(a) / m
        mb = sum(b) / m
        num = sum((a[i] - ma) * (b[i] - mb) for i in range(m))
        da = sum((x - ma) ** 2 for x in a) ** 0.5
        db = sum((x - mb) ** 2 for x in b) ** 0.5
        if da == 0 or db == 0:
            return None
        return round(num / (da * db), 4)

    matrix = []
    for i in range(n):
        row = []
        for j in range(n):
            if i == j:
                row.append(1.0)
            else:
                v = _pearson(aligned[codes[i]], aligned[codes[j]])
                row.append(v if v is not None else 0.0)
        matrix.append(row)
    sample_days = len(aligned[codes[0]]) if codes else 0
    return {"codes": codes, "matrix": matrix, "sample_days": sample_days}


COMPARE_INDEXES: dict[str, str] = {
    "000300": "滬深300",
    "399006": "創業板指",
    "000016": "上證50",
    "399001": "深證成指",
    "000905": "中證500",
}


def _compare_beta_alpha(stock_rets: list[float], index_rets: list[float]) -> dict:
    n = min(len(stock_rets), len(index_rets))
    if n < 5:
        return {}
    sr = stock_rets[:n]
    ir = index_rets[:n]
    ms = sum(sr) / n
    mi = sum(ir) / n
    cov = sum((sr[i] - ms) * (ir[i] - mi) for i in range(n)) / (n - 1)
    var_i = sum((x - mi) ** 2 for x in ir) / (n - 1)
    if var_i <= 0:
        return {}
    beta = cov / var_i
    alpha_daily = ms - beta * mi
    return {
        "beta_vs_index": round(beta, 4),
        "alpha_vs_index_pct": round(alpha_daily * 252 * 100, 2),
    }


def _compare_align_to_dates(prices_by_date: dict[str, float], anchor_dates: list[str]) -> tuple[list[str], list[float]]:
    """按 anchor 日期對齊指數/標的收盤價（前向填充）"""
    if not anchor_dates:
        return [], []
    sorted_src = sorted(prices_by_date.keys())
    out_dates: list[str] = []
    out_prices: list[float] = []
    last_price = None
    src_idx = 0
    for d in anchor_dates:
        while src_idx < len(sorted_src) and sorted_src[src_idx] <= d:
            last_price = prices_by_date[sorted_src[src_idx]]
            src_idx += 1
        if last_price is None:
            continue
        out_dates.append(d)
        out_prices.append(float(last_price))
    return out_dates, out_prices


def _load_compare_index_overlay(index_code: str, anchor_dates: list[str], days: int) -> dict | None:
    """載入指數序列並對齊至標的日期軸"""
    index_code = _normalize_compare_code(index_code)
    if index_code not in COMPARE_INDEXES or not anchor_dates:
        return None

    prices_by_date: dict[str, float] = {}

    if index_code == "000300":
        from src.core.benchmark import get_benchmark_returns

        start = anchor_dates[0]
        end = anchor_dates[-1]
        bench = get_benchmark_returns(start_date=start, end_date=end)
        for d, p in zip(bench.get("dates") or [], bench.get("prices") or []):
            prices_by_date[str(d)] = float(p)
    else:
        from src.core.local_kline import ensure_daily_kline

        df, _src = ensure_daily_kline(index_code, min_bars=2)
        if df.empty:
            return None
        if len(df) > days:
            df = df.tail(days)
        for d, c in zip(df["date"].tolist(), df["close"].tolist()):
            prices_by_date[str(d)] = float(c)

    if not prices_by_date:
        return None

    dates, closes = _compare_align_to_dates(prices_by_date, anchor_dates)
    if len(closes) < 2 or closes[0] == 0:
        return None

    base = closes[0]
    relative = [round((c / base - 1) * 100, 2) for c in closes]
    return {
        "code": index_code,
        "name": COMPARE_INDEXES[index_code],
        "dates": dates,
        "relative_return": relative,
        "close": [round(float(c), 2) for c in closes],
        "stats": _compare_series_stats(closes),
    }


def _compare_enrich_stats_vs_index(comparison: dict, index_overlay: dict) -> None:
    """為每檔股票補充相對指數的 beta / alpha"""
    idx_dates = index_overlay.get("dates") or []
    idx_close = index_overlay.get("close") or []
    if len(idx_dates) < 5:
        return
    idx_map = dict(zip(idx_dates, idx_close))
    idx_rets = _compare_daily_returns(idx_close)
    for code, item in comparison.items():
        dc = dict(zip(item.get("dates") or [], item.get("close") or []))
        aligned_stock: list[float] = []
        aligned_index: list[float] = []
        prev_s = prev_i = None
        for d in idx_dates:
            if d not in dc or d not in idx_map:
                continue
            cs = float(dc[d])
            ci = float(idx_map[d])
            if prev_s and prev_i:
                if prev_s > 0 and prev_i > 0:
                    aligned_stock.append(cs / prev_s - 1)
                    aligned_index.append(ci / prev_i - 1)
            prev_s, prev_i = cs, ci
        if len(aligned_stock) >= 5:
            extra = _compare_beta_alpha(aligned_stock, aligned_index)
            if extra and item.get("stats"):
                item["stats"].update(extra)


def _compare_excess_series(comparison: dict, benchmark: str) -> dict:
    """各股相對基準的超額累計收益序列（%）"""
    bench = comparison.get(benchmark)
    if not bench:
        return {}
    b_rel = bench.get("relative_return") or []
    b_dates = bench.get("dates") or []
    b_map = dict(zip(b_dates, b_rel))
    excess = {}
    for code, item in comparison.items():
        if code == benchmark:
            excess[code] = [0.0] * len(item.get("relative_return") or [])
            continue
        rel = item.get("relative_return") or []
        dates = item.get("dates") or []
        excess[code] = [
            round(float(rel[i]) - float(b_map.get(dates[i], 0)), 2)
            for i in range(len(rel))
        ]
    return excess


@router.get("/api/stocks/compare/indexes")
async def list_compare_indexes():
    """多股對比可疊加的 A 股指數"""
    return {
        "indexes": [{"code": k, "name": v} for k, v in COMPARE_INDEXES.items()],
    }


@router.post("/api/stocks/compare")
async def compare_stocks(body: dict):
    """多股收益率對比（本地優先，缺失時首次自動入庫）"""
    codes = body.get("codes", [])
    days = body.get("days", 250)
    start = body.get("start")
    benchmark = body.get("benchmark")
    index_code = body.get("index")
    with_stats = body.get("with_stats", True)

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
        entry = {
            "dates": [str(d) for d in dates],
            "relative_return": relative,
            "close": [round(float(c), 2) for c in closes],
        }
        if with_stats:
            entry["stats"] = _compare_series_stats(closes)
        result[code] = entry

    bench_code = _normalize_compare_code(benchmark) if benchmark else None
    if bench_code and bench_code not in result and result:
        bench_code = next(iter(result.keys()))
    excess = _compare_excess_series(result, bench_code) if bench_code and len(result) > 1 else {}

    index_overlay = None
    idx_norm = _normalize_compare_code(index_code) if index_code else None
    if idx_norm and idx_norm in COMPARE_INDEXES and result:
        anchor = result[next(iter(result.keys()))]["dates"]
        index_overlay = _load_compare_index_overlay(idx_norm, anchor, days)
        if index_overlay and with_stats:
            _compare_enrich_stats_vs_index(result, index_overlay)

    return {
        "success": True,
        "comparison": result,
        "missing": missing,
        "loaded": len(result),
        "total": len(codes),
        "correlation": _compare_correlation_matrix(result) if len(result) >= 2 else None,
        "benchmark": bench_code,
        "excess_return": excess if excess else None,
        "index_overlay": index_overlay,
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


@router.get("/api/stocks/{code}/analysis-page")
async def get_stock_analysis_page(
    code: str,
    kline_days: int = Query(180, ge=30, le=500),
    sparkline_days: int = Query(90, ge=20, le=365),
):
    """個股分析頁聚合：K 線、走勢指標、基本面。"""
    from src.core.api_cache import cached_response
    from src.core.local_kline import ensure_daily_kline, normalize_kline_code
    from src.core.market_fetch import build_sparkline_item, df_to_kline_records
    from src.core.result_cache import get_data_version
    from src.core.stock_basics import build_stock_overview, load_stock_financials, load_stock_profile

    code = normalize_kline_code(code.strip())
    profile = load_stock_profile(code)
    name = profile.get("name") or ""
    cache_key = f"api:analysis-page:{code}:{kline_days}:{sparkline_days}:{get_data_version(code)}"

    def _build():
        kline: list[dict] = []
        kline_source = ""
        try:
            df, kline_source = ensure_daily_kline(code, min_bars=10)
            if not df.empty:
                if len(df) > kline_days:
                    df = df.tail(kline_days)
                kline = df_to_kline_records(df)
        except Exception as e:
            logger.debug(f"analysis-page kline {code}: {e}")

        spark = build_sparkline_item(code, sparkline_days)

        financials = load_stock_financials(code)

        overview_lb = min(max(kline_days, 60), 250)
        try:
            overview = build_stock_overview(code, lookback=overview_lb)
        except Exception as e:
            logger.debug(f"analysis-page overview {code}: {e}")
            overview = {"code": code, "has_kline": False, "message": str(e)}

        signals_block = {
            "signals": [],
            "strength": None,
            "signals_count": 0,
            "updated_at": None,
        }
        try:
            from src.core.signals import get_current_signals_for_codes, score_signal_strength

            rows = get_current_signals_for_codes([code])
            row = rows[0] if rows else {}
            latest = row.get("signals") or []
            signals_block = {
                "signals": latest[:16],
                "strength": score_signal_strength(latest),
                "signals_count": len(latest),
                "updated_at": row.get("updated_at"),
            }
        except Exception as e:
            logger.debug(f"analysis-page signals {code}: {e}")

        return {
            "success": True,
            "code": code,
            "name": name,
            "market": profile.get("market") or "",
            "profile": profile,
            "financials": financials,
            "overview": overview,
            "signals": signals_block,
            "kline": kline,
            "kline_source": kline_source,
            "sparkline": spark,
        }

    try:
        return cached_response(cache_key, ttl=45, builder=_build)
    except Exception as e:
        logger.error(f"個股分析頁失敗 {code}: {e}")
        raise HTTPException(500, str(e))


@router.get("/api/strategies/params")
async def get_all_strategy_params_api(user=Depends(get_current_user)):
    """全部策略默認參數與優化網格"""
    from src.core.api_cache import cached_response
    from src.core.strategy_params_meta import get_all_strategy_params
    from src.core.admin_controls import is_allowed

    if not is_allowed("strategies", "params", user=user):
        raise HTTPException(403, "策略庫已被管理員關閉（僅管理員可用）")

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
        from src.core.crypto.service import CryptoDisabledError, get_crypto_service
        try:
            sym_list = symbols.split(",") if symbols else None
            data = get_crypto_service().get_realtime(sym_list)
            return {"market": "crypto", "data": data}
        except CryptoDisabledError as e:
            raise HTTPException(503, str(e))

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


@router.get("/api/markets/crypto/kline")
async def get_crypto_kline_compat(symbol: str = "BTCUSDT", days: int = 30):
    """獲取加密貨幣 K 線數據（相容路由，委派 CryptoService）"""
    from src.core.crypto.service import CryptoDisabledError, get_crypto_service
    try:
        return get_crypto_service().get_kline(symbol=symbol, days=days)
    except CryptoDisabledError as e:
        raise HTTPException(503, str(e))
    except Exception as e:
        logger.error(f"加密 K 線失敗 {symbol}: {e}")
        raise HTTPException(500, str(e))


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
