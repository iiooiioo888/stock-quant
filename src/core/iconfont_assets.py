"""
[iconfont.cn](https://www.iconfont.cn/) 圖標資源：本地 SVG、專案 Symbol JS、代碼映射。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

import requests

from src.config import BASE_DIR, DATA_DIR

ICONFONT_DATA_DIR = DATA_DIR / "iconfont"
ICONFONT_STATIC_DIR = BASE_DIR / "static" / "iconfont"
ICONFONT_STOCKS_STATIC = ICONFONT_STATIC_DIR / "stocks"
ICONFONT_STOCKS_DATA = ICONFONT_DATA_DIR / "stocks"
PROJECT_CONFIG_PATH = DATA_DIR / "iconfont_project.json"
SYMBOL_JS_CACHE = ICONFONT_DATA_DIR / "symbol_cached.js"

_SYMBOL_ID_RE = re.compile(
    r'<symbol\s+id="([^"]+)"([^>]*)>(.*?)</symbol>',
    re.DOTALL | re.IGNORECASE,
)
_VIEWBOX_RE = re.compile(r'viewBox="([^"]+)"', re.IGNORECASE)


def _ensure_dirs() -> None:
    for d in (ICONFONT_DATA_DIR, ICONFONT_STOCKS_STATIC, ICONFONT_STOCKS_DATA):
        d.mkdir(parents=True, exist_ok=True)


def load_project_config() -> dict[str, Any]:
    """讀取 data/iconfont_project.json（不存在則返回預設）。"""
    default: dict[str, Any] = {
        "enabled": True,
        "symbol_js_url": "",
        "css_url": "/static/iconfont/iconfont.css",
        "stock_icons": {},
    }
    if not PROJECT_CONFIG_PATH.is_file():
        return default
    try:
        raw = json.loads(PROJECT_CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default
    if not isinstance(raw, dict):
        return default
    out = {**default, **raw}
    if not isinstance(out.get("stock_icons"), dict):
        out["stock_icons"] = {}
    return out


def public_config() -> dict[str, Any]:
    """供前端載入的公開設定（不含 token）。"""
    cfg = load_project_config()
    return {
        "enabled": bool(cfg.get("enabled", True)),
        "symbol_js_url": str(cfg.get("symbol_js_url") or "").strip(),
        "css_url": str(cfg.get("css_url") or "/static/iconfont/iconfont.css").strip(),
        "stock_icons": dict(cfg.get("stock_icons") or {}),
        "stocks_static_prefix": "/static/iconfont/stocks/",
    }


def _normalize_code(code: str) -> str:
    return str(code or "").strip().upper()


def resolve_icon_id(code: str, name: str = "") -> str:
    """代碼 / 名稱 → iconfont symbol id（如 icon-tencent）。"""
    cfg = load_project_config()
    icons: dict = cfg.get("stock_icons") or {}
    c = _normalize_code(code)
    if c and c in icons:
        return str(icons[c]).strip()
    c6 = c.zfill(6) if c.isdigit() and len(c) <= 6 else c
    if c6 in icons:
        return str(icons[c6]).strip()
    n = str(name or "").strip()
    if n and n in icons:
        return str(icons[n]).strip()
    return ""


def find_local_stock_svg(code: str) -> Optional[Path]:
    """static/iconfont/stocks 或 data/iconfont/stocks 下的 {CODE}.svg。"""
    c = _normalize_code(code)
    if not c:
        return None
    _ensure_dirs()
    for base in (ICONFONT_STOCKS_STATIC, ICONFONT_STOCKS_DATA):
        for name in (f"{c}.svg", f"{c.lower()}.svg"):
            p = base / name
            if p.is_file() and p.stat().st_size >= 40:
                return p
    return None


def _fetch_symbol_js_text(url: str, timeout: float = 12.0) -> Optional[str]:
    u = (url or "").strip()
    if not u:
        return None
    if u.startswith("//"):
        u = "https:" + u
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; stock-quant/1.0)",
        "Referer": "https://www.iconfont.cn/",
    }
    try:
        r = requests.get(u, timeout=timeout, headers=headers)
        if r.status_code != 200:
            return None
        text = r.text or ""
        if len(text) < 200 or "<symbol" not in text:
            return None
        _ensure_dirs()
        SYMBOL_JS_CACHE.write_text(text, encoding="utf-8")
        return text
    except requests.RequestException:
        return None


def _load_symbol_js_text() -> Optional[str]:
    cfg = load_project_config()
    url = str(cfg.get("symbol_js_url") or "").strip()
    if url:
        fresh = _fetch_symbol_js_text(url)
        if fresh:
            return fresh
    if SYMBOL_JS_CACHE.is_file():
        try:
            return SYMBOL_JS_CACHE.read_text(encoding="utf-8")
        except OSError:
            pass
    static_js = ICONFONT_STATIC_DIR / "iconfont.js"
    if static_js.is_file():
        try:
            return static_js.read_text(encoding="utf-8")
        except OSError:
            pass
    return None


def extract_symbol_svg(icon_id: str, js_text: str) -> Optional[bytes]:
    """從 iconfont Symbol JS 抽出單一 symbol 為獨立 SVG。"""
    iid = str(icon_id or "").strip()
    if not iid or not js_text:
        return None
    for sid, attrs, inner in _SYMBOL_ID_RE.findall(js_text):
        if sid != iid:
            continue
        vb_m = _VIEWBOX_RE.search(attrs)
        viewbox = vb_m.group(1) if vb_m else "0 0 1024 1024"
        body = inner.strip()
        if not body:
            continue
        svg = (
            f'<?xml version="1.0" encoding="UTF-8"?>'
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{viewbox}">{body}</svg>'
        )
        return svg.encode("utf-8")
    return None


def fetch_iconfont_logo_bytes(
    code: str,
    market: str = "",
    name: str = "",
    timeout: float = 10.0,
) -> Optional[tuple[bytes, str]]:
    """
    取得 iconfont 圖案（優先本地 SVG，其次 Symbol JS 映射）。
    需在 [iconfont.cn](https://www.iconfont.cn/) 建立專案並配置 data/iconfont_project.json。
    """
    if not load_project_config().get("enabled", True):
        return None

    local = find_local_stock_svg(code)
    if local:
        try:
            body = local.read_bytes()
            if len(body) >= 40:
                return body, "image/svg+xml"
        except OSError:
            pass

    icon_id = resolve_icon_id(code, name)
    if not icon_id:
        return None

    js_text = _load_symbol_js_text()
    if not js_text:
        cfg = load_project_config()
        if not cfg.get("symbol_js_url"):
            static_js = ICONFONT_STATIC_DIR / "iconfont.js"
            if not static_js.is_file():
                return None
        js_text = _load_symbol_js_text()
    if not js_text:
        return None

    body = extract_symbol_svg(icon_id, js_text)
    if body and len(body) >= 40:
        return body, "image/svg+xml"
    return None
