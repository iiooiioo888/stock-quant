"""
股票庫 — 按總市值排名收錄多市場標的基本資料（默認前 20000）
"""
from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime
from typing import Callable, Optional

import akshare as ak
import pandas as pd
import requests

from src.config import settings
from src.core.db import get_conn
from src.utils.logger import logger

_HTTP = requests.Session()
_HTTP.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept": "application/json,text/plain,*/*",
})

DDL_STOCK_UNIVERSE = """
CREATE TABLE IF NOT EXISTS stock_universe (
    code            TEXT NOT NULL,
    market          TEXT NOT NULL,
    name            TEXT,
    exchange        TEXT,
    industry        TEXT,
    list_date       TEXT,
    price           REAL,
    change_pct      REAL,
    total_mv        REAL,
    circulating_mv  REAL,
    pe_ttm          REAL,
    pb              REAL,
    volume          REAL,
    amount          REAL,
    turnover        REAL,
    rank_mv         INTEGER,
    updated_at      TEXT NOT NULL,
    source          TEXT,
    intro           TEXT,
    extra_json      TEXT,
    PRIMARY KEY (code, market)
)
"""

# 各數據源列名候選（模糊匹配）
_COL_CANDIDATES = {
    "code": ["代码", "代码", "symbol", "股票代码", "code"],
    "name": ["名称", "名称", "name", "股票名称"],
    "price": ["最新价", "最新", "现价", "price", "close"],
    "change_pct": ["涨跌幅", "涨跌幅", "change_pct", "涨跌幅度"],
    "total_mv": ["总市值", "总市值", "市值", "total_market_cap", "mktcap"],
    "circulating_mv": ["流通市值", "流通市值", "circulating_market_cap"],
    "pe_ttm": ["市盈率-动态", "市盈率", "pe", "pe_ttm"],
    "pb": ["市净率", "市净率", "pb"],
    "volume": ["成交量", "volume"],
    "amount": ["成交额", "amount", "turnover"],
    "turnover": ["换手率", "turnover_rate"],
    "industry": ["所属行业", "行业", "板块", "industry"],
}


def init_stock_universe_table():
    with get_conn() as conn:
        conn.execute(DDL_STOCK_UNIVERSE)
        cols = {
            row[1]
            for row in conn.execute("PRAGMA table_info(stock_universe)").fetchall()
        }
        if "intro" not in cols:
            conn.execute("ALTER TABLE stock_universe ADD COLUMN intro TEXT")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_univ_rank ON stock_universe(rank_mv)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_univ_market ON stock_universe(market)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_univ_mv ON stock_universe(total_mv DESC)"
        )
        conn.commit()
    logger.info("股票庫表 stock_universe 就緒")


def _normalize_intro(text: str | None, max_len: int = 480) -> str:
    if not text:
        return ""
    s = " ".join(str(text).split())
    if len(s) <= max_len:
        return s
    return s[: max_len - 1].rstrip() + "…"


def _infer_intro_from_row(row: dict) -> str:
    industry = (row.get("industry") or "").strip()
    if industry:
        return industry
    name = (row.get("name") or "").strip()
    code = (row.get("code") or "").strip()
    if name and name != code:
        market = row.get("market")
        label = {"a_share": "A股", "hk_stock": "港股", "us_stock": "美股"}.get(market, "")
        return f"{label} {name}".strip() if label else name
    return ""


def _a_share_em_code(code: str) -> str:
    code = str(code).zfill(6)
    prefix = "SH" if code.startswith(("5", "6", "9")) else "SZ"
    return f"{prefix}{code}"


def _fetch_intro_a_share(code: str) -> str:
    try:
        resp = _HTTP.get(
            "https://emweb.securities.eastmoney.com/PC_HSF10/CompanySurvey/PageAjax",
            params={"code": _a_share_em_code(code)},
            timeout=12,
            headers={"Referer": "https://emweb.securities.eastmoney.com/"},
        )
        resp.raise_for_status()
        jb = resp.json().get("jbzl")
        if isinstance(jb, list) and jb:
            jb = jb[0]
        if not isinstance(jb, dict):
            return ""
        scope = (jb.get("BUSINESS_SCOPE") or "").strip()
        if scope:
            return _normalize_intro(scope)
        profile = (jb.get("ORG_PROFILE") or "").strip()
        if profile:
            return _normalize_intro(profile)
        em2016 = (jb.get("EM2016") or jb.get("INDUSTRYCSRC1") or "").strip()
        return _normalize_intro(em2016)
    except Exception as e:
        logger.debug(f"A股簡介 {code} 失敗: {e}")
        return ""


def _fetch_intro_hk(code: str) -> str:
    num = str(code).zfill(5)
    secu = f"{num}.HK"
    try:
        resp = _HTTP.get(
            "https://datacenter.eastmoney.com/securities/api/data/v1/get",
            params={
                "reportName": "RPT_HKF10_INFO_ORGPROFILE",
                "columns": "SECUCODE,ORG_NAME,ORG_PROFILE",
                "filter": f'(SECUCODE="{secu}")',
                "pageNumber": 1,
                "pageSize": 1,
                "source": "SECURITIES",
                "client": "PC",
            },
            timeout=12,
        )
        resp.raise_for_status()
        data = (resp.json().get("result") or {}).get("data") or []
        if not data:
            return ""
        row = data[0]
        profile = (row.get("ORG_PROFILE") or "").strip()
        if profile:
            return _normalize_intro(profile)
        return _normalize_intro(row.get("ORG_NAME"))
    except Exception as e:
        logger.debug(f"港股簡介 {code} 失敗: {e}")
        return ""


def _fetch_intro_us(code: str) -> str:
    sym = str(code).strip().upper()
    for secu in (f"{sym}.O", f"{sym}.N", sym):
        try:
            resp = _HTTP.get(
                "https://datacenter.eastmoney.com/securities/api/data/v1/get",
                params={
                    "reportName": "RPT_USF10_INFO_ORGPROFILE",
                    "columns": "SECUCODE,ORG_NAME,ORG_PROFILE",
                    "filter": f'(SECUCODE="{secu}")',
                    "pageNumber": 1,
                    "pageSize": 1,
                    "source": "SECURITIES",
                    "client": "PC",
                },
                timeout=12,
            )
            resp.raise_for_status()
            body = resp.json()
            if not body.get("success"):
                continue
            data = (body.get("result") or {}).get("data") or []
            if not data:
                continue
            row = data[0]
            profile = (row.get("ORG_PROFILE") or "").strip()
            if profile:
                return _normalize_intro(profile)
            return _normalize_intro(row.get("ORG_NAME"))
        except Exception:
            continue
    return ""


def _fetch_intro(code: str, market: str) -> str:
    if market == "a_share":
        return _fetch_intro_a_share(code)
    if market == "hk_stock":
        return _fetch_intro_hk(code)
    if market == "us_stock":
        return _fetch_intro_us(code)
    return ""


def enrich_universe_intros(
    limit: int | None = None,
    task_id: str | None = None,
    *,
    replace_short: bool = True,
) -> dict:
    """為股票庫補充簡介（按 rank_mv 優先，東財 F10）。"""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from src.core.task_manager import update_task, update_task_meta, is_task_cancelled

    cap = limit if limit is not None else settings.stock_universe_intro_enrich_limit
    if cap <= 0:
        return {"enriched": 0, "skipped": True, "attempted": 0, "failed": 0}

    init_stock_universe_table()
    intro_filter = (
        "intro IS NULL OR intro = ''"
        + (" OR (length(intro) < 36 AND intro NOT LIKE '%。%' AND intro NOT LIKE '%；%')" if replace_short else "")
    )
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"""
            SELECT code, market, name, industry, intro, rank_mv
            FROM stock_universe
            WHERE {intro_filter}
            ORDER BY rank_mv ASC
            LIMIT ?
            """,
            (cap,),
        ).fetchall()

    total = len(rows)
    if total == 0:
        result = {"enriched": 0, "failed": 0, "attempted": 0, "note": "所有標的已有簡介"}
        if task_id:
            update_task(task_id, status="completed", progress=100, result=result)
            update_task_meta(task_id, message="無需補充（簡介已齊）")
        return result

    if task_id:
        update_task_meta(task_id, message=f"準備補充簡介（{total} 檔）…")
        update_task(task_id, progress=5)

    def _one(row_dict: dict) -> tuple[str, str, str]:
        code = row_dict["code"]
        market = row_dict["market"]
        intro = _fetch_intro(code, market)
        if not intro:
            intro = _infer_intro_from_row(row_dict)
        return code, market, intro

    workers = min(6, max(total, 1))
    pending: list[tuple[str, str, str]] = []
    done = 0

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_one, dict(r)) for r in rows]
        for fut in as_completed(futures):
            if task_id and is_task_cancelled(task_id):
                raise RuntimeError("任務已取消")
            code, market, intro = fut.result()
            if intro:
                pending.append((code, market, intro))
            done += 1
            if task_id and (done == 1 or done % 25 == 0 or done == total):
                pct = 5 + int(done / max(total, 1) * 85)
                update_task(task_id, progress=min(92, pct))
                update_task_meta(
                    task_id,
                    message=f"拉取簡介 {done}/{total}（待寫入 {len(pending)}）",
                )

    enriched = 0
    with get_conn() as conn:
        for code, market, intro in pending:
            conn.execute(
                "UPDATE stock_universe SET intro = ? WHERE code = ? AND market = ?",
                (intro, code, market),
            )
            enriched += 1
        conn.commit()

    failed = total - enriched
    result = {"enriched": enriched, "failed": failed, "attempted": total}
    logger.info(f"股票庫簡介補充: 嘗試 {total}，成功 {enriched}，無資料 {failed}")
    if task_id:
        update_task(task_id, progress=100, result=result)
        update_task_meta(task_id, message=f"簡介補充完成（{enriched}/{total}）")
    return result


def _find_col(df: pd.DataFrame, keys: list[str]) -> Optional[str]:
    cols = list(df.columns)
    for k in keys:
        for c in cols:
            if k in str(c):
                return c
    return None


def _normalize_code(code: str, market: str) -> str:
    code = str(code).strip()
    if market == "a_share" and code.isdigit():
        return code.zfill(6)
    return code


def _to_float(val, default=0.0) -> float:
    try:
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return default
        return float(val)
    except (TypeError, ValueError):
        return default


def _mv_to_yi(raw: float, market: str) -> float:
    """統一為億元量級便於排序（A/HK 原為元；美股原為美元，僅作相對排序）"""
    if raw <= 0:
        return 0.0
    if market == "us_stock":
        # 美元市值 → 粗略按 7 折算人民幣億元
        return raw / 1e8 * 7.0
    return raw / 1e8


def _parse_spot_df(
    df: pd.DataFrame,
    market: str,
    exchange: str,
    source: str,
) -> list[dict]:
    if df is None or df.empty:
        return []

    code_col = _find_col(df, _COL_CANDIDATES["code"])
    name_col = _find_col(df, _COL_CANDIDATES["name"])
    if not code_col:
        return []

    mv_col = _find_col(df, _COL_CANDIDATES["total_mv"])
    rows = []
    for _, row in df.iterrows():
        code = _normalize_code(row.get(code_col, ""), market)
        if not code or code in ("nan", "None"):
            continue
        name = str(row.get(name_col, "")) if name_col else ""
        raw_mv = _to_float(row.get(mv_col)) if mv_col else 0.0
        total_mv_yi = _mv_to_yi(raw_mv, market)

        item = {
            "code": code,
            "market": market,
            "name": name,
            "exchange": exchange,
            "industry": str(row.get(_find_col(df, _COL_CANDIDATES["industry"]), "") or "")
            if _find_col(df, _COL_CANDIDATES["industry"])
            else "",
            "list_date": "",
            "price": _to_float(row.get(_find_col(df, _COL_CANDIDATES["price"]))),
            "change_pct": _to_float(row.get(_find_col(df, _COL_CANDIDATES["change_pct"]))),
            "total_mv": round(total_mv_yi, 4),
            "circulating_mv": round(
                _mv_to_yi(
                    _to_float(row.get(_find_col(df, _COL_CANDIDATES["circulating_mv"]))),
                    market,
                ),
                4,
            ),
            "pe_ttm": _to_float(row.get(_find_col(df, _COL_CANDIDATES["pe_ttm"]))),
            "pb": _to_float(row.get(_find_col(df, _COL_CANDIDATES["pb"]))),
            "volume": _to_float(row.get(_find_col(df, _COL_CANDIDATES["volume"]))),
            "amount": _to_float(row.get(_find_col(df, _COL_CANDIDATES["amount"]))),
            "turnover": _to_float(row.get(_find_col(df, _COL_CANDIDATES["turnover"]))),
            "source": source,
            "intro": _infer_intro_from_row({
                "code": code,
                "market": market,
                "name": name,
                "industry": str(row.get(_find_col(df, _COL_CANDIDATES["industry"]), "") or "")
                if _find_col(df, _COL_CANDIDATES["industry"])
                else "",
            }),
        }
        rows.append(item)
    return rows


def _fetch_with_retry(fetcher: Callable[[], pd.DataFrame], label: str, retries: int = 2) -> pd.DataFrame:
    last_err = None
    for i in range(retries + 1):
        try:
            df = fetcher()
            if df is not None and not df.empty:
                logger.info(f"股票庫 {label}: {len(df)} 條")
                return df
        except Exception as e:
            last_err = e
            logger.warning(f"股票庫 {label} 第 {i + 1} 次失敗: {e}")
            time.sleep(1.5 * (i + 1))
    if last_err:
        logger.error(f"股票庫 {label} 放棄: {last_err}")
    return pd.DataFrame()


def _chunked(items: list[str], size: int = 80):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def _yahoo_chart_quote(symbol: str, timeout: int = 10) -> dict:
    """Yahoo chart 端點備援；通常不需要 crumb，可取價格/成交量。"""
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        resp = _HTTP.get(url, params={"range": "5d", "interval": "1d"}, timeout=timeout)
        if resp.status_code in (401, 403, 404, 429):
            return {}
        resp.raise_for_status()
        result = resp.json().get("chart", {}).get("result", [])
        if not result:
            return {}
        meta = result[0].get("meta", {})
        quote = result[0].get("indicators", {}).get("quote", [{}])[0]
        closes = [x for x in quote.get("close", []) if x is not None]
        volumes = [x for x in quote.get("volume", []) if x is not None]
        if not closes:
            return {}
        price = float(closes[-1])
        prev = float(closes[-2]) if len(closes) > 1 else float(meta.get("previousClose") or price)
        return {
            "symbol": symbol,
            "shortName": symbol,
            "regularMarketPrice": price,
            "regularMarketChangePercent": ((price - prev) / prev * 100) if prev > 0 else 0,
            "regularMarketVolume": int(volumes[-1]) if volumes else 0,
            "currency": meta.get("currency"),
        }
    except Exception:
        return {}


def _yahoo_quote_batch(symbols: list[str], timeout: int = 15) -> dict[str, dict]:
    """Yahoo Finance 批量報價。免費端點，失敗時返回空 dict。"""
    if not symbols:
        return {}
    out: dict[str, dict] = {}
    url = "https://query1.finance.yahoo.com/v7/finance/quote"
    chart_fallback_remaining = 120
    for chunk in _chunked(symbols, 80):
        try:
            resp = _HTTP.get(url, params={"symbols": ",".join(chunk)}, timeout=timeout)
            if resp.status_code in (401, 403):
                # 部分環境會擋 v7 quote；退回 v8 chart，限制數量避免同步過慢。
                for symbol in chunk:
                    if chart_fallback_remaining <= 0:
                        break
                    q = _yahoo_chart_quote(symbol)
                    if q:
                        out[symbol.upper()] = q
                    chart_fallback_remaining -= 1
                    time.sleep(0.05)
                continue
            if resp.status_code == 429:
                logger.warning("Yahoo quote 觸發限流，暫停後繼續")
                time.sleep(2)
                continue
            resp.raise_for_status()
            data = resp.json()
            for q in data.get("quoteResponse", {}).get("result", []):
                sym = str(q.get("symbol") or "").upper()
                if sym:
                    out[sym] = q
        except Exception as e:
            logger.warning(f"Yahoo quote 批次失敗 ({len(chunk)}): {e}")
        time.sleep(0.15)
    return out


def _quote_to_row(
    quote: dict,
    market: str,
    exchange: str,
    source: str,
    fallback_code: str = "",
    fallback_name: str = "",
) -> dict:
    symbol = str(quote.get("symbol") or fallback_code).strip()
    code = fallback_code or symbol
    if market == "hk_stock" and symbol.endswith(".HK"):
        code = symbol[:-3].zfill(5)
    elif market == "a_share" and symbol.endswith((".SS", ".SZ")):
        code = symbol[:-3].zfill(6)
    name = (
        quote.get("shortName")
        or quote.get("longName")
        or fallback_name
        or code
    )
    market_cap = _to_float(quote.get("marketCap"))
    return {
        "code": _normalize_code(code, market),
        "market": market,
        "name": str(name),
        "exchange": exchange,
        "industry": "",
        "list_date": "",
        "price": _to_float(quote.get("regularMarketPrice")),
        "change_pct": _to_float(quote.get("regularMarketChangePercent")),
        "total_mv": round(_mv_to_yi(market_cap, market), 4),
        "circulating_mv": 0,
        "pe_ttm": _to_float(quote.get("trailingPE")),
        "pb": 0,
        "volume": _to_float(quote.get("regularMarketVolume")),
        "amount": 0,
        "turnover": 0,
        "source": source,
    }


def _fetch_us_symbols_nasdaq_trader(limit: int = 12000) -> list[dict]:
    """NASDAQ Trader 免費符號目錄（涵蓋 NASDAQ/NYSE/AMEX）。"""
    urls = [
        ("NASDAQ", "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"),
        ("US", "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"),
    ]
    rows: list[dict] = []
    seen: set[str] = set()
    for exchange, url in urls:
        try:
            resp = _HTTP.get(url, timeout=20)
            resp.raise_for_status()
            lines = [ln for ln in resp.text.splitlines() if ln and not ln.startswith("File Creation Time")]
            if not lines:
                continue
            header = lines[0].split("|")
            for ln in lines[1:]:
                parts = ln.split("|")
                if len(parts) != len(header):
                    continue
                rec = dict(zip(header, parts))
                symbol = (rec.get("Symbol") or rec.get("ACT Symbol") or "").strip()
                if not symbol or symbol in seen:
                    continue
                if rec.get("Test Issue", "N") == "Y":
                    continue
                if rec.get("ETF", "N") == "Y":
                    continue
                name = (rec.get("Security Name") or rec.get("Company Name") or symbol).strip()
                rows.append({
                    "code": symbol,
                    "market": "us_stock",
                    "name": name,
                    "exchange": exchange,
                    "industry": "",
                    "list_date": "",
                    "price": 0,
                    "change_pct": 0,
                    "total_mv": 0,
                    "circulating_mv": 0,
                    "pe_ttm": 0,
                    "pb": 0,
                    "volume": 0,
                    "amount": 0,
                    "turnover": 0,
                    "source": "nasdaq_trader",
                })
                seen.add(symbol)
                if len(rows) >= limit:
                    break
        except Exception as e:
            logger.warning(f"NASDAQ Trader 符號目錄失敗 {exchange}: {e}")
        if len(rows) >= limit:
            break
    logger.info(f"股票庫 NASDAQ Trader: {len(rows)} 條")
    return rows


def _enrich_rows_with_yahoo(rows: list[dict], market: str, max_quotes: int = 2500) -> list[dict]:
    """用 Yahoo quote 為符號目錄補價格/市值。"""
    if not rows:
        return []
    selected = rows[:max_quotes]
    symbols = []
    row_by_symbol = {}
    for row in selected:
        code = row["code"]
        if market == "hk_stock":
            symbol = f"{str(code).zfill(4)}.HK"
        elif market == "a_share":
            suffix = "SS" if str(code).startswith(("5", "6", "9")) else "SZ"
            symbol = f"{str(code).zfill(6)}.{suffix}"
        else:
            symbol = str(code).replace(".", "-")
        symbols.append(symbol)
        row_by_symbol[symbol.upper()] = row

    quotes = _yahoo_quote_batch(symbols)
    enriched: list[dict] = []
    for sym, row in row_by_symbol.items():
        q = quotes.get(sym)
        if q:
            enriched.append(_quote_to_row(
                q,
                market=row["market"],
                exchange=row.get("exchange") or ("US" if market == "us_stock" else "HK"),
                source=f"{row.get('source') or 'symbol_dir'}+yahoo",
                fallback_code=row["code"],
                fallback_name=row.get("name", ""),
            ))
        else:
            enriched.append(row)
    if len(rows) > len(selected):
        enriched.extend(rows[len(selected):])
    return enriched


_HK_YAHOO_SYMBOLS = [
    ("0001", "長和"), ("0002", "中電控股"), ("0003", "香港中華煤氣"), ("0005", "匯豐控股"),
    ("0011", "恒生銀行"), ("0016", "新鴻基地產"), ("0017", "新世界發展"), ("0027", "銀河娛樂"),
    ("0388", "香港交易所"), ("0669", "創科實業"), ("0700", "騰訊控股"), ("0762", "中國聯通"),
    ("0823", "領展房產基金"), ("0857", "中國石油股份"), ("0883", "中國海洋石油"),
    ("0939", "建設銀行"), ("0941", "中國移動"), ("0981", "中芯國際"), ("0992", "聯想集團"),
    ("1024", "快手"), ("1038", "長江基建集團"), ("1088", "中國神華"), ("1093", "石藥集團"),
    ("1099", "國藥控股"), ("1109", "華潤置地"), ("1177", "中國生物製藥"), ("1211", "比亞迪股份"),
    ("1299", "友邦保險"), ("1398", "工商銀行"), ("1810", "小米集團-W"), ("1876", "百威亞太"),
    ("1928", "金沙中國有限公司"), ("2015", "理想汽車-W"), ("2020", "安踏體育"), ("2269", "藥明生物"),
    ("2318", "中國平安"), ("2319", "蒙牛乳業"), ("2331", "李寧"), ("2382", "舜宇光學科技"),
    ("2388", "中銀香港"), ("2628", "中國人壽"), ("2688", "新奧能源"), ("3690", "美團-W"),
    ("3968", "招商銀行"), ("3988", "中國銀行"), ("6098", "碧桂園服務"), ("6618", "京東健康"),
    ("6862", "海底撈"), ("9618", "京東集團-SW"), ("9633", "農夫山泉"), ("9866", "蔚來-SW"),
    ("9888", "百度集團-SW"), ("9988", "阿里巴巴-SW"), ("9999", "網易-S"),
]


_EM_HOSTS = (
    "https://82.push2.eastmoney.com",
    "https://85.push2.eastmoney.com",
    "https://push2.eastmoney.com",
    "https://47.push2.eastmoney.com",
)
_EM_FS = {
    "a_share": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048",
    "hk_stock": "m:116+t:31",
    "us_stock": "m:105+t:55,m:105+t:43",
}
_EM_FIELDS = "f12,f14,f2,f3,f5,f6,f8,f9,f20,f21,f23"


def _em_clist_page(host: str, fs: str, page: int, page_size: int = 100) -> list[dict]:
    url = f"{host}/api/qt/clist/get"
    params = {
        "pn": page,
        "pz": page_size,
        "po": 1,
        "np": 1,
        "fltt": 2,
        "invt": 2,
        "fid": "f20",
        "fs": fs,
        "fields": _EM_FIELDS,
        "ut": "fa5fd1943c7b386f172d6893dbbd1",
    }
    resp = _HTTP.get(url, params=params, timeout=20)
    resp.raise_for_status()
    data = resp.json().get("data") or {}
    return data.get("diff") or []


def _fetch_eastmoney_spot_df(market: str, max_pages: int = 220) -> pd.DataFrame:
    """東財 clist 直連（akshare 失敗時備援，多節點輪詢）。"""
    fs = _EM_FS.get(market)
    if not fs:
        return pd.DataFrame()

    last_err = None
    for host in _EM_HOSTS:
        rows: list[dict] = []
        try:
            for page in range(1, max_pages + 1):
                batch = _em_clist_page(host, fs, page)
                if not batch:
                    break
                for item in batch:
                    code = str(item.get("f12") or "").strip()
                    if not code or code == "-":
                        continue
                    rows.append({
                        "代码": code,
                        "名称": str(item.get("f14") or ""),
                        "最新价": item.get("f2"),
                        "涨跌幅": item.get("f3"),
                        "成交量": item.get("f5"),
                        "成交额": item.get("f6"),
                        "换手率": item.get("f8"),
                        "市盈率-动态": item.get("f9"),
                        "总市值": item.get("f20"),
                        "流通市值": item.get("f21"),
                        "市净率": item.get("f23"),
                    })
                if len(batch) < 100:
                    break
                time.sleep(0.12)
            if rows:
                logger.info(f"股票庫 {market} 東財直連: {len(rows)} 條 ({host})")
                return pd.DataFrame(rows)
        except Exception as e:
            last_err = e
            logger.warning(f"股票庫 {market} 東財 {host} 失敗: {e}")
            time.sleep(0.5)
    if last_err:
        logger.debug(f"股票庫 {market} 東財直連全部失敗: {last_err}")
    return pd.DataFrame()


def _fetch_market_spot_df(market: str) -> pd.DataFrame:
    """拉取單市場全量行情：東財直連 → akshare。"""
    ak_fetchers = {
        "a_share": ak.stock_zh_a_spot_em,
        "hk_stock": ak.stock_hk_spot_em,
        "us_stock": ak.stock_us_spot_em,
    }
    df = _fetch_eastmoney_spot_df(market)
    if not df.empty:
        return df
    fetcher = ak_fetchers.get(market)
    if fetcher:
        return _fetch_with_retry(fetcher, market)
    return pd.DataFrame()


def _kline_code_to_universe(code: str, market: str) -> str:
    """daily_kline 代碼 → stock_universe 代碼。"""
    code = str(code).strip()
    if market == "hk_stock":
        if code.endswith(".HK"):
            return code[:-3].zfill(5)
        return code.zfill(5) if code.isdigit() else code
    if market == "a_share":
        if code.endswith((".SS", ".SZ")):
            return code[:-3].zfill(6)
        return code.zfill(6) if code.isdigit() else code
    return code


def _build_catalog_name_map() -> dict[tuple[str, str], str]:
    from src.core.global_market import MARKET_CATALOG

    out: dict[tuple[str, str], str] = {}
    for mk, cat in MARKET_CATALOG.items():
        if mk not in ("us_stock", "hk_stock"):
            continue
        for sym, name in cat.get("symbols", {}).items():
            ucode = _kline_code_to_universe(sym, mk)
            out[(ucode, mk)] = name
            out[(sym, mk)] = name
    return out


def _apply_catalog_meta(rows: list[dict]) -> None:
    """為目錄內標的補名稱與簡介。"""
    name_map = _build_catalog_name_map()
    for row in rows:
        key = (row.get("code"), row.get("market"))
        cat_name = name_map.get(key)
        if cat_name:
            if not row.get("name") or row.get("name") == row.get("code"):
                row["name"] = cat_name
            if not row.get("intro"):
                row["intro"] = cat_name


def refresh_universe_from_local_kline(task_id: str | None = None) -> dict:
    """
    用本地 daily_kline 更新股票庫（全球/全市場下載完成後調用）。
    已存在則更新價格；不存在則新增。
    """
    from src.core.task_manager import update_task, update_task_meta, is_task_cancelled

    init_stock_universe_table()
    updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    name_map = _build_catalog_name_map()
    exchange_map = {"a_share": "CN", "us_stock": "US", "hk_stock": "HK"}

    if task_id:
        update_task_meta(task_id, message="正在用本地日 K 更新股票庫…")
        update_task(task_id, progress=96)

    inserted = 0
    updated = 0
    skipped = 0

    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT k.code, k.market, k.close, k.volume,
                   (
                       SELECT k2.close FROM daily_kline k2
                       WHERE k2.code = k.code AND k2.market = k.market AND k2.date < k.date
                       ORDER BY k2.date DESC LIMIT 1
                   ) AS prev_close
            FROM daily_kline k
            INNER JOIN (
                SELECT code, market, MAX(date) AS max_date
                FROM daily_kline
                WHERE market IN ('a_share', 'us_stock', 'hk_stock')
                GROUP BY code, market
            ) latest ON k.code = latest.code
                AND k.market = latest.market
                AND k.date = latest.max_date
            WHERE k.market IN ('a_share', 'us_stock', 'hk_stock')
            """
        ).fetchall()

        max_rank = conn.execute(
            "SELECT COALESCE(MAX(rank_mv), 0) FROM stock_universe"
        ).fetchone()[0]

        for kline_code, market, close, volume, prev_close in rows:
            if task_id and is_task_cancelled(task_id):
                raise RuntimeError("任務已取消")

            ucode = _kline_code_to_universe(kline_code, market)
            if not ucode or close is None:
                skipped += 1
                continue

            price = float(close)
            change_pct = 0.0
            if prev_close and float(prev_close) > 0:
                change_pct = (price - float(prev_close)) / float(prev_close) * 100

            name = (
                name_map.get((ucode, market))
                or name_map.get((kline_code, market))
                or ucode
            )
            exchange = exchange_map.get(market, "")

            existing = conn.execute(
                "SELECT code FROM stock_universe WHERE code = ? AND market = ?",
                (ucode, market),
            ).fetchone()

            if existing:
                conn.execute(
                    """
                    UPDATE stock_universe SET
                        name = CASE WHEN name IS NULL OR name = '' THEN ? ELSE name END,
                        price = ?, change_pct = ?, volume = ?,
                        updated_at = ?,
                        source = CASE
                            WHEN source IS NULL OR source = '' THEN 'local_kline'
                            WHEN source LIKE '%local_kline%' THEN source
                            ELSE source || '+local_kline'
                        END
                    WHERE code = ? AND market = ?
                    """,
                    (
                        name,
                        price,
                        round(change_pct, 4),
                        float(volume or 0),
                        updated_at,
                        ucode,
                        market,
                    ),
                )
                updated += 1
            else:
                max_rank += 1
                intro = name if name and name != ucode else ""
                conn.execute(
                    """
                    INSERT INTO stock_universe (
                        code, market, name, exchange, industry, list_date,
                        price, change_pct, total_mv, circulating_mv, pe_ttm, pb,
                        volume, amount, turnover, rank_mv, updated_at, source, intro, extra_json
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        ucode,
                        market,
                        name,
                        exchange,
                        None,
                        None,
                        price,
                        round(change_pct, 4),
                        0,
                        0,
                        0,
                        0,
                        float(volume or 0),
                        0,
                        0,
                        max_rank,
                        updated_at,
                        "local_kline",
                        intro or None,
                        None,
                    ),
                )
                inserted += 1

        conn.commit()

    result = {
        "inserted": inserted,
        "updated": updated,
        "skipped": skipped,
        "updated_at": updated_at,
    }
    logger.info(
        f"股票庫本地更新: 新增 {inserted}，更新 {updated}，跳過 {skipped}"
    )
    if task_id:
        update_task(task_id, progress=99)
        update_task_meta(
            task_id,
            message=f"股票庫已更新（新增 {inserted}，更新 {updated}）",
        )
    return result


def _fallback_hk_yahoo() -> list[dict]:
    rows = [{
        "code": code,
        "market": "hk_stock",
        "name": name,
        "exchange": "HK",
        "industry": "",
        "list_date": "",
        "price": 0,
        "change_pct": 0,
        "total_mv": 0,
        "circulating_mv": 0,
        "pe_ttm": 0,
        "pb": 0,
        "volume": 0,
        "amount": 0,
        "turnover": 0,
        "source": "hk_bluechip_seed",
    } for code, name in _HK_YAHOO_SYMBOLS]
    enriched = _enrich_rows_with_yahoo(rows, "hk_stock", max_quotes=len(rows))
    logger.info(f"股票庫 Yahoo 港股備援: {len(enriched)} 條")
    return enriched


def fetch_all_market_basics() -> list[dict]:
    """從多市場實時行情拉取基本資料並合併。"""
    batches: list[tuple[str, str, str]] = [
        ("a_share", "CN", "eastmoney_a"),
        ("hk_stock", "HK", "eastmoney_hk"),
        ("us_stock", "US", "eastmoney_us"),
    ]

    merged: list[dict] = []
    for market, exchange, source in batches:
        df = _fetch_market_spot_df(market)
        rows = _parse_spot_df(df, market, exchange, source)
        if rows:
            merged.extend(rows)
        elif market == "hk_stock":
            merged.extend(_fallback_hk_yahoo())
        elif market == "us_stock":
            us_rows = _fetch_us_symbols_nasdaq_trader()
            merged.extend(_enrich_rows_with_yahoo(us_rows, "us_stock", max_quotes=2500))
        time.sleep(0.8)

    # 無市值的標的 total_mv=0，排序時靠後
    merged.sort(key=lambda x: x.get("total_mv") or 0, reverse=True)
    return merged


def _fallback_a_share_codes() -> list[dict]:
    """東財全量失敗時：僅代碼+名稱（無市值）。"""
    try:
        df = ak.stock_info_a_code_name()
        if df.empty:
            return []
        out = []
        for _, row in df.iterrows():
            code = _normalize_code(row.get("code", ""), "a_share")
            if not code:
                continue
            out.append({
                "code": code,
                "market": "a_share",
                "name": str(row.get("name", "")),
                "exchange": "CN",
                "industry": "",
                "list_date": "",
                "price": 0,
                "change_pct": 0,
                "total_mv": 0,
                "circulating_mv": 0,
                "pe_ttm": 0,
                "pb": 0,
                "volume": 0,
                "amount": 0,
                "turnover": 0,
                "source": "akshare_code_name",
            })
        logger.info(f"股票庫降級：A 股代碼表 {len(out)} 條（無市值）")
        return out
    except Exception as e:
        logger.error(f"股票庫降級失敗: {e}")
        return []


def sync_stock_universe(
    max_count: int | None = None,
    task_id: str | None = None,
) -> dict:
    """
    同步股票庫：按市值取前 max_count（默認 settings.stock_universe_max_count）。
    """
    from src.core.task_manager import update_task, update_task_meta, is_task_cancelled

    max_count = max_count or settings.stock_universe_max_count
    init_stock_universe_table()
    updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if task_id:
        update_task_meta(task_id, message="正在拉取多市場行情…")
        update_task(task_id, progress=5)

    all_rows = fetch_all_market_basics()
    if not all_rows:
        all_rows = _fallback_a_share_codes()
    elif not any(r.get("market") == "a_share" for r in all_rows):
        all_rows.extend(_fallback_a_share_codes())

    if task_id and is_task_cancelled(task_id):
        raise RuntimeError("任務已取消")

    # 去重 (code, market)
    seen: set[tuple[str, str]] = set()
    deduped = []
    for r in all_rows:
        key = (r["code"], r["market"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(r)

    deduped.sort(key=lambda x: x.get("total_mv") or 0, reverse=True)
    top = deduped[:max_count]
    _apply_catalog_meta(top)

    if task_id:
        update_task(task_id, progress=60)
        update_task_meta(
            task_id,
            message=f"寫入股票庫 {len(top)} / {len(deduped)} 條",
        )

    saved_intros: dict[tuple[str, str], str] = {}
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        for row in conn.execute(
            "SELECT code, market, intro FROM stock_universe WHERE intro IS NOT NULL AND intro != ''"
        ):
            saved_intros[(row["code"], row["market"])] = row["intro"]

    for row in top:
        if not row.get("intro"):
            row["intro"] = saved_intros.get((row["code"], row["market"]), "")
        if not row.get("intro"):
            row["intro"] = _infer_intro_from_row(row)

    with get_conn() as conn:
        conn.execute("DELETE FROM stock_universe")
        records = []
        for rank, row in enumerate(top, start=1):
            records.append((
                row["code"],
                row["market"],
                row.get("name"),
                row.get("exchange"),
                row.get("industry") or None,
                row.get("list_date") or None,
                row.get("price"),
                row.get("change_pct"),
                row.get("total_mv"),
                row.get("circulating_mv"),
                row.get("pe_ttm"),
                row.get("pb"),
                row.get("volume"),
                row.get("amount"),
                row.get("turnover"),
                rank,
                updated_at,
                row.get("source"),
                row.get("intro") or None,
                json.dumps({"raw_rank_pool": len(deduped)}, ensure_ascii=False),
            ))

        conn.executemany(
            """INSERT OR REPLACE INTO stock_universe (
                code, market, name, exchange, industry, list_date,
                price, change_pct, total_mv, circulating_mv, pe_ttm, pb,
                volume, amount, turnover, rank_mv, updated_at, source, intro, extra_json
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            records,
        )
        conn.commit()

    intro_stats = {"enriched": 0, "attempted": 0, "failed": 0}
    if settings.stock_universe_intro_enrich_limit > 0:
        if task_id:
            update_task_meta(task_id, message="正在補充公司簡介…")
        try:
            intro_stats = enrich_universe_intros(task_id=task_id)
        except Exception as e:
            logger.warning(f"股票庫簡介補充失敗: {e}")
            intro_stats = {"error": str(e)}

    by_market: dict[str, int] = {}
    by_source: dict[str, int] = {}
    for r in top:
        by_market[r["market"]] = by_market.get(r["market"], 0) + 1
        src = r.get("source") or "unknown"
        by_source[src] = by_source.get(src, 0) + 1

    result = {
        "success": True,
        "total_pool": len(deduped),
        "saved": len(top),
        "max_count": max_count,
        "updated_at": updated_at,
        "by_market": by_market,
        "by_source": by_source,
        "intro_enrich": intro_stats,
        "note": (
            "已按總市值排序取前 N；若 Yahoo/交易所備援仍無市值，會保留代碼與名稱並排在後段。"
            if len(deduped) < max_count
            else None
        ),
    }
    logger.info(
        f"股票庫同步完成: 入庫 {len(top)} 條（池內 {len(deduped)}，上限 {max_count}）"
    )

    if task_id:
        update_task(task_id, progress=100, result=result)
        update_task_meta(task_id, message="股票庫同步完成")

    return result


def query_stock_universe(
    market: str | None = None,
    keyword: str | None = None,
    limit: int = 100,
    offset: int = 0,
    order_by: str = "rank_mv",
) -> tuple[list[dict], int]:
    """查詢股票庫（分頁）。"""
    init_stock_universe_table()
    allowed_order = {"rank_mv", "total_mv", "change_pct", "code", "name"}
    if order_by not in allowed_order:
        order_by = "rank_mv"

    conditions = ["1=1"]
    params: list = []
    if market and market != "all":
        conditions.append("market = ?")
        params.append(market)
    if keyword:
        conditions.append("(code LIKE ? OR name LIKE ? OR intro LIKE ?)")
        kw = f"%{keyword.strip()}%"
        params.extend([kw, kw, kw])

    where = " AND ".join(conditions)
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        total = conn.execute(
            f"SELECT COUNT(*) AS c FROM stock_universe WHERE {where}",
            params,
        ).fetchone()["c"]
        rows = conn.execute(
            f"""SELECT * FROM stock_universe WHERE {where}
                ORDER BY {order_by} ASC
                LIMIT ? OFFSET ?""",
            params + [limit, offset],
        ).fetchall()
    return [dict(r) for r in rows], int(total)


def get_universe_stats() -> dict:
    init_stock_universe_table()
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        total = conn.execute("SELECT COUNT(*) AS c FROM stock_universe").fetchone()["c"]
        if total == 0:
            return {"total": 0, "markets": {}, "updated_at": None}
        updated = conn.execute(
            "SELECT MAX(updated_at) AS u FROM stock_universe"
        ).fetchone()["u"]
        markets = conn.execute(
            """SELECT market, COUNT(*) AS cnt,
                      SUM(CASE WHEN total_mv > 0 THEN 1 ELSE 0 END) AS with_mv
               FROM stock_universe GROUP BY market"""
        ).fetchall()
    return {
        "total": total,
        "updated_at": updated,
        "markets": {r["market"]: {"count": r["cnt"], "with_mv": r["with_mv"]} for r in markets},
    }


def load_universe_codes(market: str = "a_share", limit: int | None = None) -> list[str]:
    """供下載/篩選使用的代碼列表。"""
    rows, _ = query_stock_universe(market=market, limit=limit or 50000, offset=0)
    return [r["code"] for r in rows if r.get("code")]
