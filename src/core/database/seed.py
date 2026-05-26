"""
常見數據預載 — 日 K、股票庫目錄、板塊快照、基本面、示範回測

用法:
  python scripts/seed_common_data.py
  python scripts/seed_common_data.py --profile standard
  python main.py seed --profile standard
"""
from __future__ import annotations

import random
import time
from datetime import datetime
from typing import Iterable

import pandas as pd

from src.config import settings
from src.utils.logger import logger

# 主要指數（日 K，用於基準/對比）
INDEX_CODES: tuple[str, ...] = (
    "000300",  # 滬深300
    "000016",  # 上證50
    "399001",  # 深證成指
    "399006",  # 創業板指
    "000905",  # 中證500
)

# 常見藍籌 / 權重
CORE_BLUE_CHIPS: tuple[str, ...] = (
    "600519", "601318", "600036", "000858", "000333",
    "002594", "300750", "601166", "600900", "601012",
    "600276", "000725", "002415", "601888", "603259",
    "688981", "600030", "601398", "601857", "601288",
    "000001", "000002", "600028", "601088", "601899",
)

# 常見 ETF
ETF_CODES: tuple[str, ...] = (
    "510300", "510500", "512880", "512480", "512660",
)

DEMO_STRATEGIES: tuple[str, ...] = (
    "dual_ma", "macd", "bollinger", "rsi", "momentum",
)


def _dedupe_codes(codes: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for c in codes:
        c = str(c).strip()
        if not c or c in seen:
            continue
        seen.add(c)
        out.append(c)
    return out


def codes_for_profile(profile: str) -> list[str]:
    """依預載檔位返回待下載代碼列表。"""
    profile = (profile or "standard").lower()
    base = list(settings.watchlist)

    if profile == "quick":
        return _dedupe_codes(base + list(INDEX_CODES[:2]))
    if profile == "full":
        from src.api.constants import STOCK_NAMES

        return _dedupe_codes(list(STOCK_NAMES.keys()) + list(INDEX_CODES))
    # standard（默認）
    return _dedupe_codes(base + list(INDEX_CODES) + list(CORE_BLUE_CHIPS) + list(ETF_CODES))


def _kline_already_seeded(codes: list[str], min_codes: int = 2) -> bool:
    from src.core.db import load_daily_kline

    ok = 0
    for code in codes[: max(min_codes, len(codes))]:
        if not load_daily_kline(code).empty:
            ok += 1
    return ok >= min(min_codes, len(codes))


def seed_universe_catalog() -> int:
    """將 STOCK_NAMES 寫入股票庫（無需外網，僅元數據）。"""
    from src.api.constants import STOCK_NAMES
    from src.core.db import get_conn

    updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    records = []
    for rank, (code, name) in enumerate(STOCK_NAMES.items(), start=1):
        records.append((
            code,
            "a_share",
            name,
            "CN",
            None,  # industry
            None,  # list_date
            None,  # price
            None,  # change_pct
            None,  # total_mv
            None,  # circulating_mv
            None,  # pe_ttm
            None,  # pb
            None,  # volume
            None,  # amount
            None,  # turnover
            rank,
            updated_at,
            "catalog_seed",
            None,  # intro
            None,  # extra_json
        ))

    with get_conn() as conn:
        before = conn.execute("SELECT COUNT(*) FROM stock_universe").fetchone()[0]
        conn.executemany(
            """
            INSERT OR IGNORE INTO stock_universe (
                code, market, name, exchange, industry, list_date,
                price, change_pct, total_mv, circulating_mv, pe_ttm, pb,
                volume, amount, turnover, rank_mv, updated_at, source, intro, extra_json
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            records,
        )
        after = conn.execute("SELECT COUNT(*) FROM stock_universe").fetchone()[0]

    added = max(0, int(after) - int(before))
    logger.info(f"股票庫目錄：新增 {added} 條（共 {after} 條）")
    return added


def _seed_realtime_from_kline(codes: list[str]) -> int:
    from src.api.constants import STOCK_NAMES
    from src.core.db import load_daily_kline, save_realtime_snapshot

    rows: list[dict] = []
    for code in codes:
        df = load_daily_kline(code)
        if df.empty or "close" not in df.columns:
            continue
        last = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else last
        close = float(last["close"])
        prev_close = float(prev.get("close", close) or close)
        chg = (close - prev_close) / prev_close * 100 if prev_close else 0.0
        rows.append({
            "code": code,
            "name": STOCK_NAMES.get(code, code),
            "price": close,
            "change_pct": round(chg, 4),
            "volume": float(last.get("volume", 0) or 0),
            "amount": float(last.get("amount", 0) or 0),
            "high": float(last.get("high", close) or close),
            "low": float(last.get("low", close) or close),
            "open": float(last.get("open", close) or close),
            "prev_close": prev_close,
        })

    if not rows:
        return 0
    save_realtime_snapshot(pd.DataFrame(rows))
    return len(rows)


def _download_codes(codes: list[str], start_date: str | None = None) -> dict:
    from src.core.history import download_one

    total = 0
    ok = 0
    failed: list[str] = []
    start_date = start_date or settings.history_start_date

    for i, code in enumerate(codes, 1):
        count = 0
        for attempt in range(3):
            try:
                count = download_one(code, start_date=start_date)
                if count >= 0:
                    break
            except Exception as e:
                logger.debug(f"下載 {code} 第{attempt + 1}次失敗: {e}")
                if attempt < 2:
                    time.sleep(2)
        if count > 0:
            total += count
            ok += 1
            logger.info(f"[{i}/{len(codes)}] {code}: {count} 條")
        else:
            failed.append(code)
        if i < len(codes):
            time.sleep(max(0.3, settings.download_throttle_sec) * random.uniform(0.7, 1.3))

    return {"total_records": total, "ok": ok, "failed": failed}


def _seed_fundamentals(codes: list[str], limit: int) -> int:
    from src.core.fundamental import get_fundamentals

    n = 0
    for code in codes[:limit]:
        try:
            data = get_fundamentals(code)
            if data:
                n += 1
        except Exception as e:
            logger.debug(f"基本面 {code} 跳過: {e}")
        time.sleep(0.3)
    return n


def _seed_sector_snapshots() -> dict:
    from src.core.sector import save_sector_snapshot

    out: dict[str, int] = {}
    for st in ("industry", "concept"):
        try:
            out[st] = save_sector_snapshot(st)
        except Exception as e:
            logger.warning(f"板塊快照 {st} 失敗: {e}")
            out[st] = 0
    return out


def _seed_sample_backtests(codes: list[str], strategies: tuple[str, ...]) -> int:
    from src.core.backtest import run_backtest

    n = 0
    for code in codes:
        for strat in strategies:
            try:
                run_backtest(code, strategy_name=strat)
                n += 1
            except Exception as e:
                logger.debug(f"示範回測 {code}/{strat} 跳過: {e}")
    return n


def seed_common_data(
    profile: str = "standard",
    *,
    force: bool = False,
    download: bool = True,
    catalog: bool = True,
    sector: bool | None = None,
    fundamentals: bool | None = None,
    backtest_samples: bool | None = None,
    sync_universe: bool = False,
    universe_max: int = 500,
) -> dict:
    """
    預載常見數據。

    profile:
      - quick: 自選股 + 滬深300，約 7 檔
      - standard: 藍籌 + 指數 + ETF，約 35 檔（默認）
      - full: STOCK_NAMES 全集 + 指數（耗時較長）
    """
    from src.core.database.bootstrap import init_database

    profile = (profile or "standard").lower()
    init_database()

    codes = codes_for_profile(profile)
    result: dict = {
        "profile": profile,
        "codes_planned": len(codes),
        "skipped": False,
    }

    if catalog:
        result["catalog_rows"] = seed_universe_catalog()

    if sector is None:
        sector = profile != "quick"
    if fundamentals is None:
        fundamentals = profile == "standard"
    if backtest_samples is None:
        backtest_samples = profile == "quick"

    if download:
        if not force and _kline_already_seeded(codes):
            logger.info("日 K 已存在，跳過下載（使用 --force 強制）")
            result["download"] = {"skipped": True, "ok": 0, "total_records": 0}
        else:
            logger.info(f"開始下載 {len(codes)} 檔日 K（{profile}）…")
            result["download"] = _download_codes(codes)
            from src.core.db import clear_data_cache

            clear_data_cache()

        try:
            from src.core.stock_universe import refresh_universe_from_local_kline

            result["universe_refresh"] = refresh_universe_from_local_kline()
        except Exception as e:
            logger.warning(f"股票庫由日 K 刷新失敗: {e}")
            result["universe_refresh"] = {"error": str(e)}

        result["realtime_rows"] = _seed_realtime_from_kline(codes)

    if sync_universe and profile in ("standard", "full"):
        try:
            from src.core.stock_universe import sync_stock_universe

            cap = universe_max if profile == "standard" else settings.stock_universe_max_count
            result["universe_sync"] = sync_stock_universe(max_count=cap)
        except Exception as e:
            logger.warning(f"股票庫全量同步失敗: {e}")
            result["universe_sync"] = {"error": str(e)}

    if sector:
        result["sector"] = _seed_sector_snapshots()

    if fundamentals:
        limit = 5 if profile == "quick" else (15 if profile == "standard" else 30)
        fund_codes = list(settings.watchlist) + list(CORE_BLUE_CHIPS[:10])
        result["fundamentals"] = _seed_fundamentals(_dedupe_codes(fund_codes), limit=limit)

    if backtest_samples:
        bt_codes = list(settings.watchlist)
        result["backtests"] = _seed_sample_backtests(bt_codes, DEMO_STRATEGIES)

    logger.info(f"常見數據預載完成（{profile}）")
    return result
