"""自選股持久化（data/runtime_watchlist.json）— 重啟後保留用戶添加的標的"""
from __future__ import annotations

import json
from typing import Any

from src.config import DATA_DIR, settings
from src.utils.logger import logger

_RUNTIME_PATH = DATA_DIR / "runtime_watchlist.json"


def _normalize_code(code: str) -> str:
    code = str(code).strip()
    if code.isdigit() and len(code) < 6:
        return code.zfill(6)
    return code


def load_runtime() -> dict[str, Any]:
    if not _RUNTIME_PATH.is_file():
        return {"watchlist": [], "alert_rules": {}}
    try:
        data = json.loads(_RUNTIME_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except Exception as e:
        logger.warning(f"讀取 runtime_watchlist 失敗: {e}")
    return {"watchlist": [], "alert_rules": {}}


def save_runtime() -> None:
    payload = {
        "watchlist": list(settings.watchlist),
        "alert_rules": dict(settings.alert_rules),
    }
    try:
        _RUNTIME_PATH.parent.mkdir(parents=True, exist_ok=True)
        _RUNTIME_PATH.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as e:
        logger.warning(f"寫入 runtime_watchlist 失敗: {e}")


def apply_runtime_on_startup() -> None:
    """啟動時合併用戶曾保存的自選（不覆蓋 .env 默認，僅追加）。"""
    data = load_runtime()
    extra_wl = data.get("watchlist") or []
    extra_rules = data.get("alert_rules") or {}
    for code in extra_wl:
        c = _normalize_code(code)
        if c and c not in settings.watchlist:
            settings.watchlist.append(c)
    for code, rule in extra_rules.items():
        c = _normalize_code(code)
        if c and c not in settings.alert_rules:
            settings.alert_rules[c] = rule


def list_codes() -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for c in settings.watchlist:
        c = _normalize_code(c)
        if not c or c in seen:
            continue
        seen.add(c)
        out.append(c)
    return out


def ensure_in_watchlist(code: str) -> bool:
    code = _normalize_code(code)
    if not code:
        return False
    if code not in settings.watchlist:
        settings.watchlist.append(code)
        save_runtime()
        return True
    return False


def remove_from_watchlist(code: str) -> bool:
    code = _normalize_code(code)
    changed = False
    if code in settings.watchlist:
        settings.watchlist.remove(code)
        changed = True
    if code in settings.alert_rules:
        del settings.alert_rules[code]
        changed = True
    if changed:
        save_runtime()
    return changed
