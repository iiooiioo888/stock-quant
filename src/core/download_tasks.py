"""
市場數據下載任務 — 支持進度回報與任務列表展示
"""

import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.config import settings
from src.utils.logger import logger

_meta_lock = threading.Lock()
_AK_SEM: threading.BoundedSemaphore | None = None
_AK_SEM_N = 0

MARKET_NAMES = {
    "a_share": "A股",
    "crypto": "加密貨幣",
    "forex": "外匯",
    "us_stock": "美股",
    "hk_stock": "港股",
    "index": "全球指數",
    "etf": "ETF",
    "commodity": "商品期貨",
    "global": "全球",
}

# 走 AKShare 的市場：需信號量 + 較嚴格間隔，避免被封
_AKSHARE_MARKETS = frozenset({"a_share"})


def _akshare_semaphore() -> threading.BoundedSemaphore:
    """A 股 AKShare 並發上限（進程內單例，worker 數可變）。"""
    global _AK_SEM, _AK_SEM_N
    n = max(1, int(getattr(settings, "download_akshare_max_concurrent", 2) or 2))
    with _meta_lock:
        if _AK_SEM is None or _AK_SEM_N != n:
            _AK_SEM = threading.BoundedSemaphore(n)
            _AK_SEM_N = n
        return _AK_SEM


def _sleep_after_download(market: str) -> None:
    throttle = float(getattr(settings, "download_throttle_sec", 0) or 0)
    if throttle <= 0:
        return
    if market in _AKSHARE_MARKETS:
        ak_min = float(getattr(settings, "download_akshare_min_interval_sec", 0.5) or 0)
        base = max(throttle, ak_min)
    else:
        base = throttle
    if base <= 0:
        return
    time.sleep(base * random.uniform(0.7, 1.3))


def _history_download_one(code: str, market: str = "a_share") -> int:
    """可被測試 mock 的下載入口（延遲導入，走資料緩衝）。"""
    from src.core.data_fetch_buffer import download_one_buffered

    count, _src = download_one_buffered(code, market=market, force=False)
    return count


def _download_one_guarded(code: str, market: str, mkt: str, task_id: str | None) -> int:
    """下載單標的；A 股走 AKShare 信號量。"""
    _check_cancelled(task_id)
    if market in _AKSHARE_MARKETS:
        with _akshare_semaphore():
            _check_cancelled(task_id)
            count = _history_download_one(code, market=mkt)
            _sleep_after_download(market)
            return count
    count = _history_download_one(code, market=mkt)
    _sleep_after_download(market)
    return count


def _update_download_meta(
    task_id: str,
    *,
    message: str = None,
    market: str = None,
    current_code: str = None,
    index: int = None,
    total: int = None,
    records_total: int = None,
    progress: int = None,
):
    from src.core.task_manager import is_task_cancelled, update_task, update_task_meta

    meta = {}
    if message is not None:
        meta["message"] = message
    dl = {}
    if market is not None:
        dl["market"] = market
        dl["market_name"] = MARKET_NAMES.get(market, market)
    if current_code is not None:
        dl["current_code"] = current_code
    if index is not None:
        dl["index"] = index
    if total is not None:
        dl["total"] = total
    if records_total is not None:
        dl["records_total"] = records_total
    update_task_meta(
        task_id,
        message=message,
        download=dl if dl else None,
    )
    if progress is not None and not is_task_cancelled(task_id):
        update_task(task_id, progress=progress)


def _check_cancelled(task_id: str):
    from src.core.task_manager import is_task_cancelled

    if task_id and is_task_cancelled(task_id):
        raise RuntimeError("任務已取消")


def _market_key_to_mkt(market: str) -> str:
    if market == "a_share":
        return "a_share"
    if market in ("crypto", "forex"):
        return market
    return "global"


def _inner_download_workers(n_codes: int) -> int:
    """單任務內標的並發，不超過任務中心並行上限。"""
    n = max(1, int(n_codes) or 1)
    cap = min(int(getattr(settings, "download_max_workers", 3) or 3), n)
    try:
        from src.core.task_manager import _resolve_max_workers

        cap = min(cap, _resolve_max_workers())
    except Exception:
        pass
    return max(1, cap)


def _download_codes_parallel(
    market: str,
    market_name: str,
    codes: list[str],
    task_id: str = None,
) -> tuple[list[dict], int]:
    """並發下載標的列表，返回 details 與總記錄數。"""
    codes = codes or []
    total = len(codes)
    if total == 0:
        return [], 0

    workers = _inner_download_workers(total)
    mkt = _market_key_to_mkt(market)
    results: list[dict | None] = [None] * total
    grand_total = 0
    completed = 0

    def _one(index: int, code: str) -> tuple[int, str, int]:
        count = _download_one_guarded(code, market, mkt, task_id)
        return index, code, count

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_one, i, code): (i, code) for i, code in enumerate(codes)
        }
        for fut in as_completed(futures):
            _check_cancelled(task_id)
            idx, code, count = fut.result()
            results[idx] = {"code": code, "records": count, "market": market}
            with _meta_lock:
                completed += 1
                grand_total += count
                _update_download_meta(
                    task_id,
                    message=f"{market_name}: {code} ({completed}/{total})",
                    market=market,
                    current_code=code,
                    index=completed,
                    total=total,
                    records_total=grand_total,
                    progress=min(95, int(completed / max(total, 1) * 100)),
                )

    details = [r for r in results if r is not None]
    return details, grand_total


def run_market_download(
    market: str,
    codes: list[str],
    task_id: str = None,
) -> dict:
    """下載單一市場歷史數據"""
    codes = codes or []
    total = len(codes)
    market_name = MARKET_NAMES.get(market, market)

    _update_download_meta(
        task_id,
        message=f"準備下載 {market_name}（{total} 個標的）",
        market=market,
        index=0,
        total=total,
        records_total=0,
        progress=1,
    )

    results, grand_total = _download_codes_parallel(market, market_name, codes, task_id)

    success = sum(1 for r in results if r["records"] > 0)
    result = {
        "market": market,
        "market_name": market_name,
        "total_records": grand_total,
        "total_symbols": total,
        "success_symbols": success,
        "failed_symbols": total - success,
        "details": results,
    }

    if market in ("a_share", "us_stock", "hk_stock", "global"):
        try:
            from src.core.stock_universe import refresh_universe_from_local_kline

            uni = refresh_universe_from_local_kline(task_id=task_id)
            result["universe_refresh"] = uni
        except Exception as e:
            logger.warning(f"市場下載後股票庫更新失敗: {e}")
            result["universe_refresh"] = {"error": str(e)}

    return result


def run_stocks_download(codes: list[str], task_id: str = None) -> dict:
    """下載指定 A 股列表"""
    codes = codes or settings.watchlist
    return run_market_download("a_share", codes, task_id=task_id)


def run_download_all(task_id: str = None) -> dict:
    """下載所有市場數據（A 股走 AKShare 信號量，其餘市場可較高並發）"""
    from src.core.global_market import MARKET_CATALOG

    plan: list[tuple[str, str, list[str]]] = []
    plan.append(("a_share", MARKET_NAMES["a_share"], list(settings.watchlist)))

    for market_key in ["us_stock", "hk_stock", "index", "etf", "commodity"]:
        cat = MARKET_CATALOG.get(market_key, {})
        symbols = list(cat.get("symbols", {}).keys())
        if symbols:
            plan.append((market_key, cat.get("name", market_key), symbols))

    plan.append(("crypto", MARKET_NAMES["crypto"], list(settings.crypto_watchlist)))
    plan.append(("forex", MARKET_NAMES["forex"], list(settings.forex_watchlist)))

    all_codes = []
    for _, _, codes in plan:
        all_codes.extend(codes)
    total_symbols = len(all_codes)

    all_results = []
    grand_total = 0
    done = 0

    _update_download_meta(
        task_id,
        message=f"準備下載全市場（共 {total_symbols} 個標的）",
        index=0,
        total=total_symbols,
        records_total=0,
        progress=1,
    )

    flat_codes: list[str] = []
    flat_meta: list[tuple[str, str]] = []
    for market_key, market_label, codes in plan:
        for code in codes:
            flat_codes.append(code)
            flat_meta.append((market_key, market_label))

    workers = _inner_download_workers(len(flat_codes))

    def _one(global_idx: int, code: str) -> tuple[int, str, str, int]:
        market_key, _market_label = flat_meta[global_idx]
        mkt = _market_key_to_mkt(market_key)
        count = _download_one_guarded(code, market_key, mkt, task_id)
        return global_idx, market_key, code, count

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_one, i, code): (i, code) for i, code in enumerate(flat_codes)
        }
        for fut in as_completed(futures):
            _check_cancelled(task_id)
            gi, market_key, code, count = fut.result()
            _, market_label = flat_meta[gi]
            done += 1
            grand_total += count
            all_results.append({"market": market_key, "code": code, "records": count})
            with _meta_lock:
                _update_download_meta(
                    task_id,
                    message=f"{market_label}: {code} ({done}/{total_symbols})",
                    market=market_key,
                    current_code=code,
                    index=done,
                    total=total_symbols,
                    records_total=grand_total,
                    progress=min(95, int(done / max(total_symbols, 1) * 100)),
                )

    success_count = sum(1 for r in all_results if r["records"] > 0)
    by_market = {}
    for r in all_results:
        mk = r["market"]
        if mk not in by_market:
            by_market[mk] = {
                "market": mk,
                "market_name": MARKET_NAMES.get(mk, mk),
                "records": 0,
                "symbols": 0,
                "success": 0,
            }
        by_market[mk]["records"] += r["records"]
        by_market[mk]["symbols"] += 1
        if r["records"] > 0:
            by_market[mk]["success"] += 1

    result = {
        "total_records": grand_total,
        "total_symbols": len(all_results),
        "success_symbols": success_count,
        "failed_symbols": len(all_results) - success_count,
        "market_summary": list(by_market.values()),
        "details": all_results,
    }

    try:
        from src.core.stock_universe import refresh_universe_from_local_kline

        _update_download_meta(
            task_id,
            message="正在用本地日 K 更新股票庫…",
            progress=97,
        )
        uni = refresh_universe_from_local_kline(task_id=task_id)
        result["universe_refresh"] = uni
    except Exception as e:
        logger.warning(f"下載後股票庫更新失敗: {e}")
        result["universe_refresh"] = {"error": str(e)}

    return result


def run_incremental(
    codes: list[str] = None, force: bool = False, task_id: str = None
) -> dict:
    """增量更新（包裝 history.download_incremental，帶進度）"""
    from src.core.history import download_incremental

    if codes is None:
        codes = settings.watchlist
    total = len(codes)

    _update_download_meta(
        task_id,
        message=f"增量更新 A 股（{total} 只）" + (" [強制]" if force else ""),
        market="a_share",
        total=total,
        progress=5,
    )

    result = download_incremental(codes=codes, force=force, task_id=task_id)

    _update_download_meta(
        task_id,
        message="增量更新完成",
        records_total=result.get("total_records", 0),
        progress=100,
    )
    return result
