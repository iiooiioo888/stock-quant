"""
股票 Logo：從遠端拉取後快取至 data/stock_logos/，API 僅讀本地檔案。
"""
from __future__ import annotations

import re
import threading
import time
from pathlib import Path
from typing import List, Optional, Tuple

import requests

from src.config import DATA_DIR

LOGO_DIR = DATA_DIR / "stock_logos"
_LOGO_EXTS = {".png", ".svg", ".jpg", ".jpeg", ".webp", ".ico"}

_fetch_lock = threading.Lock()
_fetch_inflight: set[str] = set()
_fetch_negative: dict[str, float] = {}
_MAX_BG_FETCH = 8
_bg_sem = threading.Semaphore(_MAX_BG_FETCH)
_NEGATIVE_TTL = 3600.0

# 常見代碼 → 公司網域（favicon 補強）
_CRYPTO_BASES = frozenset({
    "BTC", "ETH", "BNB", "SOL", "XRP", "DOGE", "ADA", "AVAX", "DOT", "MATIC",
    "LINK", "UNI", "LTC", "BCH", "ATOM", "FIL", "APT", "ARB", "OP", "PEPE", "SHIB",
    "USDT", "USDC", "TRX",
})


def is_crypto_code(code: str) -> bool:
    """加密貨幣代碼不應走股票 Logo 快取。"""
    raw = str(code or "").strip().upper()
    base = re.sub(r"(USDT|USD|PERP)$", "", raw)
    return base in _CRYPTO_BASES


_CODE_DOMAINS = {
    "AAPL": "apple.com",
    "MSFT": "microsoft.com",
    "GOOGL": "google.com",
    "GOOG": "google.com",
    "AMZN": "amazon.com",
    "META": "meta.com",
    "TSLA": "tesla.com",
    "NVDA": "nvidia.com",
    "00700": "tencent.com",
    "09988": "alibabagroup.com",
    "03690": "meituan.com",
    "00992": "lenovo.com",
    "01810": "mi.com",
    "600519": "moutaichina.com",
    "000001": "bank.pingan.com",
    "601318": "pingan.cn",
}


def infer_market(code: str, market: str = "") -> str:
    if is_crypto_code(code):
        return "crypto"
    m = (market or "").strip().lower()
    if "hk" in m:
        return "hk_stock"
    if "us" in m:
        return "us_stock"
    if m in ("sh", "sz", "a_share", "a"):
        return "a_share"
    if m:
        return m

    raw = str(code or "").strip().upper()
    if re.fullmatch(r"\d{5}", raw):
        return "hk_stock"
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 6 or re.fullmatch(r"\d{6}", raw):
        return "a_share"
    if re.fullmatch(r"[A-Z][A-Z0-9.-]{0,9}", raw) and not raw.isdigit():
        return "us_stock"
    return "a_share"


def _a_share_prefix(code: str) -> str:
    c = re.sub(r"\D", "", code).zfill(6)[-6:]
    return "sse" if re.match(r"^[569]", c) else "szse"


def trading_view_logo_id(code: str, market: str = "") -> Optional[str]:
    slugs = trading_view_logo_slugs(code, market)
    return slugs[0] if slugs else None


def trading_view_logo_slugs(code: str, market: str = "") -> List[str]:
    """TradingView slug 候選（美股嘗試多交易所）。"""
    raw = str(code or "").strip().upper()
    mkt = infer_market(code, market)

    if mkt == "hk_stock":
        hk = raw.lstrip("0") or raw
        return [f"hkex-{hk}"]

    if mkt == "us_stock":
        s = raw.lower()
        return [f"nasdaq-{s}", f"nyse-{s}", f"amex-{s}"]

    if mkt == "a_share":
        c6 = re.sub(r"\D", "", raw).zfill(6)[-6:]
        if re.fullmatch(r"\d{6}", c6):
            return [f"{_a_share_prefix(c6)}-{c6}"]

    return []


def fmp_symbol(code: str, market: str = "") -> str:
    raw = str(code or "").strip().upper()
    mkt = infer_market(code, market)
    if mkt == "hk_stock":
        hk = raw.lstrip("0") or raw
        return f"{hk}.HK"
    if mkt == "us_stock":
        return raw
    if mkt == "a_share":
        c6 = re.sub(r"\D", "", raw).zfill(6)[-6:]
        suffix = "SS" if _a_share_prefix(c6) == "sse" else "SZ"
        return f"{c6}.{suffix}"
    return raw


def logo_domain(code: str) -> str:
    c = str(code or "").strip().upper()
    c6 = c.zfill(6) if c.isdigit() and len(c) <= 6 else c
    return _CODE_DOMAINS.get(c) or _CODE_DOMAINS.get(c6) or ""


def logo_candidate_urls(code: str, market: str = "") -> List[str]:
    """遠端 Logo 來源（FMP 優先；TradingView 常 403 故放後）。"""
    if is_crypto_code(code):
        return []
    urls: List[str] = []
    mkt = infer_market(code, market)
    raw = str(code or "").strip().upper()

    sym = fmp_symbol(code, market)
    if sym:
        urls.append(f"https://financialmodelingprep.com/image-stock/{sym}.png")

    if mkt == "us_stock" and raw:
        urls.append(
            f"https://static2.finnhub.io/file/publicdatany/finnhubimage/stock_logo/{raw}.png"
        )

    base = "https://s3-symbol-logo.tradingview.com"
    for slug in trading_view_logo_slugs(code, market):
        urls.append(f"{base}/{slug}--big.svg")

    domain = logo_domain(code)
    if domain:
        urls.append(f"https://www.google.com/s2/favicons?domain={domain}&sz=128")

    seen = set()
    out: List[str] = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def _cache_stem(code: str, market: str = "") -> str:
    c = re.sub(r"[^\w.-]", "_", str(code or "").strip().upper())[:48] or "unknown"
    mkt = infer_market(code, market)
    return f"{c}_{mkt}"


def _media_type_for_path(path: Path) -> str:
    ext = path.suffix.lower()
    return {
        ".svg": "image/svg+xml",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".ico": "image/x-icon",
    }.get(ext, "image/png")


def _extension_for_content_type(content_type: str, url: str = "", body: bytes = b"") -> str:
    ct = (content_type or "").split(";")[0].strip().lower()
    if "svg" in ct or (url and "svg" in url):
        return ".svg"
    if "jpeg" in ct or "jpg" in ct:
        return ".jpg"
    if "webp" in ct:
        return ".webp"
    if "icon" in ct or url.endswith(".ico"):
        return ".ico"
    if body.lstrip()[:5] == b"<?xml" or body.lstrip()[:4] == b"<svg":
        return ".svg"
    return ".png"


def _ensure_logo_dir() -> Path:
    LOGO_DIR.mkdir(parents=True, exist_ok=True)
    return LOGO_DIR


def find_cached_logo(code: str, market: str = "") -> Optional[Tuple[bytes, str]]:
    """讀取已下載至伺服器的 Logo 檔。"""
    stem = _cache_stem(code, market)
    if not LOGO_DIR.is_dir():
        return None
    candidates = sorted(
        (p for p in LOGO_DIR.glob(f"{stem}.*") if p.suffix.lower() in _LOGO_EXTS),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for path in candidates:
        try:
            body = path.read_bytes()
        except OSError:
            continue
        if len(body) < 80:
            continue
        return body, _media_type_for_path(path)
    return None


def save_cached_logo(code: str, market: str, body: bytes, content_type: str, source_url: str = "") -> Path:
    """將 Logo 寫入 data/stock_logos/（同一代碼僅保留一個副檔名）。"""
    _ensure_logo_dir()
    stem = _cache_stem(code, market)
    ext = _extension_for_content_type(content_type, source_url, body)
    target = LOGO_DIR / f"{stem}{ext}"
    for old in LOGO_DIR.glob(f"{stem}.*"):
        if old.suffix.lower() in _LOGO_EXTS and old != target:
            try:
                old.unlink()
            except OSError:
                pass
    target.write_bytes(body)
    return target


def fetch_iconfont_logo_bytes(
    code: str,
    market: str = "",
    name: str = "",
    timeout: float = 10.0,
) -> Optional[Tuple[bytes, str]]:
    """從 iconfont 本地 SVG 或專案 Symbol JS 取得圖案。"""
    from src.core.iconfont_assets import fetch_iconfont_logo_bytes as _ifn

    return _ifn(code, market, name=name, timeout=timeout)


def _is_image_body(body: bytes, content_type: str, url: str) -> bool:
    if len(body) < 80:
        return False
    ct = (content_type or "").lower()
    if "html" in ct or "json" in ct or "text/plain" in ct:
        return False
    if body.lstrip()[:15].lower().startswith(b"<!doctype") or body.lstrip()[:5].lower() == b"<html":
        return False
    return True


def fetch_logo_bytes(code: str, market: str = "", timeout: float = 6.0) -> Optional[Tuple[bytes, str]]:
    """從遠端候選 URL 拉取 Logo（僅在本地無快取時使用）。"""
    base_headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
    }
    for url in logo_candidate_urls(code, market):
        headers = dict(base_headers)
        if "tradingview.com" in url:
            headers["Referer"] = "https://www.tradingview.com/"
        try:
            r = requests.get(url, timeout=timeout, headers=headers)
            if r.status_code != 200:
                continue
            body = r.content or b""
            ct = (r.headers.get("Content-Type") or "image/png").split(";")[0].strip()
            if not _is_image_body(body, ct, url):
                continue
            if "svg" in url or body.lstrip()[:5] == b"<?xml" or body.lstrip()[:4] == b"<svg":
                ct = "image/svg+xml"
            return body, ct
        except requests.RequestException:
            continue
    return None


def _logo_task_key(code: str, market: str = "") -> str:
    return _cache_stem(code, market)


def _is_negative_cached(key: str) -> bool:
    ts = _fetch_negative.get(key)
    return bool(ts and time.time() - ts < _NEGATIVE_TTL)


def _download_and_cache(code: str, market: str = "", name: str = "", timeout: float = 6.0) -> bool:
    """下載並寫入快取；成功返回 True。"""
    ifn = fetch_iconfont_logo_bytes(code, market, name=name, timeout=timeout)
    if ifn:
        body, ct = ifn
        save_cached_logo(code, market, body, ct, source_url="iconfont")
        return True
    remote = fetch_logo_bytes(code, market, timeout=timeout)
    if not remote:
        return False
    body, ct = remote
    save_cached_logo(code, market, body, ct)
    return True


def _bg_fetch_worker(code: str, market: str, name: str, key: str) -> None:
    try:
        with _bg_sem:
            if find_cached_logo(code, market):
                _fetch_negative.pop(key, None)
                return
            if _download_and_cache(code, market, name=name):
                _fetch_negative.pop(key, None)
            else:
                _fetch_negative[key] = time.time()
    finally:
        with _fetch_lock:
            _fetch_inflight.discard(key)


def schedule_logo_fetch(code: str, market: str = "", name: str = "") -> bool:
    """背景排隊下載（API 未命中時呼叫，避免阻塞請求）。"""
    c = str(code or "").strip()
    if not c:
        return False
    key = _logo_task_key(c, market)
    if find_cached_logo(c, market) or _is_negative_cached(key):
        return False
    with _fetch_lock:
        if key in _fetch_inflight:
            return False
        _fetch_inflight.add(key)
    threading.Thread(
        target=_bg_fetch_worker,
        args=(c, market, name, key),
        daemon=True,
        name=f"logo-fetch-{key}",
    ).start()
    return True


def read_cached_logo(code: str, market: str = "") -> Optional[Tuple[bytes, str]]:
    """僅讀本地快取（供 API 快速回應）。"""
    return find_cached_logo(code, market)


def get_or_fetch_logo(
    code: str,
    market: str = "",
    timeout: float = 6.0,
    name: str = "",
) -> Optional[Tuple[bytes, str]]:
    """同步下載（批次 sync / CLI）；API 請求請用 read_cached_logo + schedule_logo_fetch。"""
    hit = find_cached_logo(code, market)
    if hit:
        return hit
    if _download_and_cache(code, market, name=name, timeout=timeout):
        return find_cached_logo(code, market)
    return None


def sync_logos_batch(
    codes: List[str],
    market: str = "",
    *,
    code_markets: Optional[dict[str, str]] = None,
    skip_existing: bool = True,
    timeout: float = 6.0,
) -> dict:
    """批次下載 Logo 至伺服器（供管理端或腳本呼叫）。"""
    ok = miss = skipped = 0
    seen: set[str] = set()
    for code in codes:
        c = str(code or "").strip()
        if not c or c in seen:
            continue
        seen.add(c)
        mkt = (code_markets or {}).get(c, market)
        if skip_existing and find_cached_logo(c, mkt):
            skipped += 1
            continue
        if get_or_fetch_logo(c, mkt, timeout=timeout):
            ok += 1
        else:
            miss += 1
    return {
        "total": len(seen),
        "ok": ok,
        "miss": miss,
        "skipped": skipped,
        "dir": str(LOGO_DIR),
    }
