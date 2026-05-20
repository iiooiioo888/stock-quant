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
    batches: list[tuple[str, str, str, Callable]] = [
        ("a_share", "CN", "eastmoney_a", lambda: ak.stock_zh_a_spot_em()),
        ("hk_stock", "HK", "eastmoney_hk", lambda: ak.stock_hk_spot_em()),
        ("us_stock", "US", "eastmoney_us", lambda: ak.stock_us_spot_em()),
    ]

    merged: list[dict] = []
    for market, exchange, source, fetcher in batches:
        df = _fetch_with_retry(fetcher, market)
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

    if task_id:
        update_task(task_id, progress=60)
        update_task_meta(
            task_id,
            message=f"寫入股票庫 {len(top)} / {len(deduped)} 條",
        )

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
                json.dumps({"raw_rank_pool": len(deduped)}, ensure_ascii=False),
            ))

        conn.executemany(
            """INSERT OR REPLACE INTO stock_universe (
                code, market, name, exchange, industry, list_date,
                price, change_pct, total_mv, circulating_mv, pe_ttm, pb,
                volume, amount, turnover, rank_mv, updated_at, source, extra_json
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            records,
        )
        conn.commit()

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
        conditions.append("(code LIKE ? OR name LIKE ?)")
        kw = f"%{keyword.strip()}%"
        params.extend([kw, kw])

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
