"""全球資產詳情 — K 線 / 報價 / 財報 / 新聞 / 技術統計（多源）"""

from __future__ import annotations



from typing import Any, Optional



import pandas as pd



from src.core.market_catalog import GROUP_LABELS, lookup_instrument

from src.core.market_fetch import (

    build_index_chart_item,

    df_to_kline_records,

    fetch_history_df,

    fetch_quote,

    symbol_to_a_share_code,

)

from src.core.stock_basics import _infer_market

from src.utils.logger import logger





def _normalize_symbol(symbol: str) -> str:

    return str(symbol).strip().upper()





def _external_links(symbol: str, name: str, tv: str = "", market: str = "") -> list[dict]:

    sym = _normalize_symbol(symbol)

    links = []

    if tv:

        links.append({

            "title": f"TradingView · {name or sym}",

            "url": f"https://www.tradingview.com/chart/?symbol={tv.replace(':', '%3A')}",

            "source": "TradingView",

            "time": "",

        })

    yahoo = sym

    if sym.isdigit() and len(sym) == 6:

        yahoo = f"{sym}.SS" if sym.startswith(("5", "6", "9")) else f"{sym}.SZ"

    links.append({

        "title": f"Yahoo Finance · {name or sym}",

        "url": f"https://finance.yahoo.com/quote/{yahoo}",

        "source": "Yahoo",

        "time": "",

    })

    if sym.endswith(".HK"):

        code = sym.replace(".HK", "").lstrip("0") or "0"

        links.append({

            "title": f"東方財富 · {name or sym}",

            "url": f"https://quote.eastmoney.com/hk/{code}.html",

            "source": "東財",

            "time": "",

        })

        links.append({

            "title": f"AASTOCKS · {name or sym}",

            "url": f"http://www.aastocks.com/tc/stocks/quote/detail-quote.aspx?symbol={code.zfill(4)}",

            "source": "AASTOCKS",

            "time": "",

        })

    elif market == "us_stock" and sym.replace(".US", "").isalpha():

        links.append({

            "title": f"東方財富 · {name or sym}",

            "url": f"https://quote.eastmoney.com/us/{sym.replace('.US', '')}.html",

            "source": "東財",

            "time": "",

        })

    return links





def _fetch_a_share_news(code: str, limit: int = 12) -> list[dict]:

    try:

        import akshare as ak



        df = ak.stock_news_em(symbol=code)

        if df is None or df.empty:

            return []

        items = []

        for _, row in df.head(limit).iterrows():

            title = str(row.get("新闻标题") or row.get("title") or "").strip()

            if not title:

                continue

            items.append({

                "title": title,

                "url": str(row.get("新闻链接") or row.get("url") or "").strip(),

                "source": str(row.get("文章来源") or row.get("source") or "東財").strip(),

                "time": str(row.get("发布时间") or row.get("date") or "").strip(),

            })

        return items

    except Exception as e:

        logger.debug(f"A股新聞 {code} 失敗: {e}")

        return []





def _load_financials(symbol: str) -> dict:

    code = symbol_to_a_share_code(symbol)

    if not code:

        return {}

    try:

        from src.core.data_pipeline import resolve_financials



        return resolve_financials(code, allow_fetch=True, max_age_days=7) or {}

    except Exception as e:

        logger.debug(f"財報 {symbol} 失敗: {e}")

        return {}





def _fetch_em_snapshot(symbol: str) -> dict:

    """東財 push2 快照（港股/美股估值與當日行情）。"""

    try:

        from src.core.global_market import _to_em_secid



        secid = _to_em_secid(symbol)

        if not secid:

            return {}

        from src.core.data_sources import get_session



        http = get_session("asset_detail")

        resp = http.get(

            "https://push2.eastmoney.com/api/qt/stock/get",

            params={

                "secid": secid,

                "fields": "f43,f44,f45,f46,f47,f48,f57,f58,f84,f85,f92,f116,f117,f162,f167,f168,f169,f170",

                "ut": "fa5fd1943c7b386f172d6893dbbd1",

            },

            timeout=10,

        )

        data = resp.json().get("data") or {}

        if not data:

            return {}



        sym = _normalize_symbol(symbol)

        if sym.endswith(".HK"):

            divisor = 1000.0

            mv_div = 1e8

        elif sym.endswith(".US") or sym.replace(".", "").replace("-", "").isalpha():

            divisor = 1000.0

            mv_div = 1e8

        else:

            divisor = 100.0

            mv_div = 1e8



        def _f(key: str, scale: float = 1.0) -> Optional[float]:

            raw = data.get(key)

            if raw is None or raw == "-" or raw == "":

                return None

            try:

                return float(raw) / scale

            except (TypeError, ValueError):

                return None



        pe = _f("f167", 10.0) or _f("f162", 100.0)
        pb = _f("f168", 10.0) or _f("f85", 100.0)
        total_mv = _f("f116", mv_div) or _f("f117", mv_div)



        return {

            "name": str(data.get("f58") or "").strip(),

            "price": _f("f43", divisor),

            "open": _f("f46", divisor),

            "high": _f("f44", divisor),

            "low": _f("f45", divisor),

            "prev_close": _f("f44", divisor),

            "volume": int(data.get("f47") or 0),

            "amount": _f("f48", 1.0),

            "change_pct": _f("f170", 100.0),

            "pe_ttm": pe,

            "pb": pb,

            "total_mv": total_mv,

            "source": "eastmoney",

        }

    except Exception as e:

        logger.debug(f"東財快照 {symbol} 失敗: {e}")

        return {}





def _merge_financials(symbol: str, market: str, base: dict, em: dict, profile: dict) -> dict:

    """合併 A 股財報、東財快照與 stock_universe 欄位。"""

    out = dict(base) if base else {}

    for src in (em, profile):

        for k, v in (src or {}).items():

            if v is None or v == "":

                continue

            if out.get(k) is None:

                out[k] = v



    if em.get("pe_ttm") is not None:

        out["pe_ttm"] = em["pe_ttm"]

    if em.get("pb") is not None:

        out["pb"] = em["pb"]

    if em.get("total_mv") is not None:

        out["total_mv"] = em["total_mv"]



    if out.get("pe_ttm") is not None or out.get("pb") is not None or out.get("total_mv") is not None:

        out["has_data"] = True

        out.setdefault("source", em.get("source") or profile.get("source") or market)

    elif base.get("has_data"):

        out["has_data"] = True

    return out





def _load_profile_enhanced(symbol: str, inst_name: str = "") -> dict:

    """簡介 / 行業 / 市值等（含港股東財 F10）。"""

    sym = _normalize_symbol(symbol)

    market = _infer_market(sym)

    try:

        from src.core.stock_basics import load_stock_profile



        profile = load_stock_profile(sym) or {}

    except Exception as e:

        logger.debug(f"profile {sym}: {e}")

        profile = {"code": sym, "market": market}



    if inst_name and not profile.get("name"):

        profile["name"] = inst_name



    intro = (profile.get("intro") or "").strip()

    if not intro and market == "hk_stock" and sym.endswith(".HK"):

        try:

            from src.core.stock_universe import _fetch_intro_hk



            hk_num = sym.replace(".HK", "").lstrip("0") or "0"

            intro = _fetch_intro_hk(hk_num)

            if intro:

                profile["intro"] = intro

        except Exception as e:

            logger.debug(f"港股簡介 {sym}: {e}")

    elif not intro and market == "us_stock":

        try:

            from src.core.stock_universe import _fetch_intro_us



            code = sym.replace(".US", "")

            intro = _fetch_intro_us(code)

            if intro:

                profile["intro"] = intro

        except Exception as e:

            logger.debug(f"美股簡介 {sym}: {e}")



    profile.setdefault("market", market)

    profile.setdefault("market_label", profile.get("market_label") or GROUP_LABELS.get(market, market))

    return profile





def _stats_from_kline(kline: list[dict], quote: dict, days: int) -> dict:

    """從 K 線計算區間統計與簡單技術指標。"""

    if not kline or len(kline) < 2:

        return {}



    df = pd.DataFrame(kline)

    if "close" not in df.columns:

        return {}



    df["close"] = pd.to_numeric(df["close"], errors="coerce")

    df = df.dropna(subset=["close"])

    if len(df) < 2:

        return {}



    closes = df["close"].astype(float)

    latest = float(closes.iloc[-1])

    n = len(closes)



    def _ret(period: int) -> Optional[float]:

        if n <= period:

            return None

        base = float(closes.iloc[-1 - period])

        if not base:

            return None

        return round((latest / base - 1) * 100, 2)



    high_col = pd.to_numeric(df.get("high", closes), errors="coerce")

    low_col = pd.to_numeric(df.get("low", closes), errors="coerce")

    vol_col = pd.to_numeric(df.get("volume", 0), errors="coerce").fillna(0)



    ma20 = float(closes.tail(20).mean()) if n >= 20 else None

    ma60 = float(closes.tail(60).mean()) if n >= 60 else None



    stats: dict[str, Any] = {

        "bars": n,

        "period_days": days,

        "period_high": round(float(high_col.max()), 4),

        "period_low": round(float(low_col.min()), 4),

        "return_1w": _ret(5),

        "return_1m": _ret(21),

        "return_3m": _ret(63),

        "return_6m": _ret(126),

        "avg_volume_20": int(vol_col.tail(20).mean()) if n >= 5 else int(vol_col.mean()),

        "latest_volume": int(vol_col.iloc[-1]) if len(vol_col) else 0,

    }

    if ma20:

        stats["ma20"] = round(ma20, 4)

        stats["dist_ma20_pct"] = round((latest / ma20 - 1) * 100, 2)

    if ma60:

        stats["ma60"] = round(ma60, 4)

        stats["dist_ma60_pct"] = round((latest / ma60 - 1) * 100, 2)



    last = df.iloc[-1]
    prev_row = df.iloc[-2] if n >= 2 else last
    stats["open"] = round(float(last.get("open", latest)), 4)
    stats["high"] = round(float(last.get("high", latest)), 4)
    stats["low"] = round(float(last.get("low", latest)), 4)
    stats["prev_close"] = round(float(prev_row.get("close", latest)), 4)

    q = quote or {}
    for k in ("volume", "amount", "currency"):
        if q.get(k) is not None:
            stats[k] = q[k]
    if stats.get("latest_volume") and not stats.get("volume"):
        stats["volume"] = stats["latest_volume"]

    return stats





def _enrich_quote(quote: dict, em: dict, chart: dict) -> dict:

    out = dict(quote or {})

    for src in (em, chart):

        for k in ("price", "change", "change_pct", "open", "high", "low", "volume", "prev_close", "currency", "source"):

            if out.get(k) is None and src.get(k) is not None:

                out[k] = src[k]

    if em.get("name") and not out.get("name"):

        out["name"] = em["name"]

    return out





def build_asset_detail(symbol: str, days: int = 180) -> Optional[dict]:

    """單一資產完整詳情包。"""

    symbol = _normalize_symbol(symbol)

    if not symbol:

        return None



    inst = lookup_instrument(symbol)

    name = inst.name if inst else symbol

    group = inst.group if inst else ""

    asset_class = inst.asset_class if inst else ""

    tv_symbol = inst.tv if inst else ""

    market = _infer_market(symbol)



    chart = build_index_chart_item(symbol, name, days)

    if not chart:

        df, hist_src = fetch_history_df(symbol, days)

        if df.empty:

            return None

        quote_raw, quote_src = fetch_quote(symbol)

        closes = df["close"].astype(float)

        latest = float(closes.iloc[-1])

        prev = float(closes.iloc[-2]) if len(closes) > 1 else latest

        change = latest - prev

        change_pct = (change / prev * 100) if prev else 0.0

        if quote_raw.get("price"):

            latest = float(quote_raw["price"])

        if quote_raw.get("change_pct") is not None:

            change_pct = float(quote_raw["change_pct"])

        chart = {

            "symbol": symbol,

            "name": name,

            "latest": round(latest, 4),

            "change": round(change, 4),

            "change_pct": round(change_pct, 2),

            "source": quote_src or hist_src,

            "kline": df_to_kline_records(df),

            "group": group,

            "asset_class": asset_class,

            "currency": quote_raw.get("currency", ""),

        }



    em_snap = _fetch_em_snapshot(symbol) if market in ("hk_stock", "us_stock") else {}

    if em_snap.get("name"):

        name = em_snap["name"]



    quote = _enrich_quote(

        {

            "price": chart.get("latest"),

            "change": chart.get("change"),

            "change_pct": chart.get("change_pct"),

            "source": chart.get("source"),

            "currency": chart.get("currency", ""),

        },

        em_snap,

        chart,

    )



    kline = chart.get("kline") or []

    stats = _stats_from_kline(kline, quote, days)

    profile = _load_profile_enhanced(symbol, name)



    code = symbol_to_a_share_code(symbol)

    financials = _merge_financials(

        symbol,

        market,

        _load_financials(symbol) if code else {},

        em_snap,

        profile,

    )



    news = _fetch_a_share_news(code) if code else []

    if not news:

        news = _external_links(symbol, name, tv_symbol, market)



    pm = {}

    if code:

        try:

            from src.core.polymarket.stock_link import search_polymarket_for_stock



            pm = search_polymarket_for_stock(code, name, limit_per_query=6, max_results=10)

        except Exception as e:

            logger.debug(f"Polymarket {symbol}: {e}")



    links = _external_links(symbol, chart.get("name") or name, tv_symbol, market)



    return {

        "symbol": symbol,

        "name": chart.get("name") or name,

        "group": group,

        "group_label": GROUP_LABELS.get(group, group),

        "asset_class": asset_class,

        "market": market,

        "market_label": GROUP_LABELS.get(group, profile.get("market_label", market)),

        "tv_symbol": tv_symbol,

        "quote": quote,

        "kline": kline,

        "kline_source": chart.get("source", ""),

        "stats": stats,

        "profile": profile,

        "financials": financials,

        "news": news,

        "polymarket": pm,

        "links": links,

    }


