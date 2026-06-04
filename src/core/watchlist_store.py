"""自選股持久化（DB + data/runtime_watchlist.json）— 重啟後保留用戶添加的標的"""
from __future__ import annotations

import json
from typing import Any

from src.config import DATA_DIR, settings
from src.utils.logger import logger

_RUNTIME_PATH = DATA_DIR / "runtime_watchlist.json"

# 默認監控列表名稱（DB 用戶自選股統一使用此名稱）
_DEFAULT_WATCHLIST_NAME = "我的自選股"


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


# ── 全局自選（settings.watchlist，向後兼容） ──────────────────

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


# ── DB 驅動的用戶自選（user_watchlists 表） ──────────────────

def _get_user_default_watchlist_codes(user_id: int) -> list[str]:
    """從 DB 獲取用戶的默認監控列表代碼。"""
    import sqlite3
    from src.core.database.connection import get_conn

    with get_conn() as conn:
        row = conn.execute(
            "SELECT codes FROM user_watchlists WHERE user_id = ? AND name = ? ORDER BY id LIMIT 1",
            (user_id, _DEFAULT_WATCHLIST_NAME),
        ).fetchone()
    if row:
        try:
            codes = json.loads(row[0])
            return [_normalize_code(c) for c in codes if c]
        except (json.JSONDecodeError, TypeError):
            pass
    return []


def _save_user_default_watchlist(user_id: int, codes: list[str]) -> None:
    """保存用戶的默認監控列表到 DB（upsert）。"""
    import sqlite3
    from datetime import datetime
    from src.core.database.connection import get_conn

    codes_json = json.dumps(codes, ensure_ascii=False)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with get_conn() as conn:
        existing = conn.execute(
            "SELECT id FROM user_watchlists WHERE user_id = ? AND name = ? ORDER BY id LIMIT 1",
            (user_id, _DEFAULT_WATCHLIST_NAME),
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE user_watchlists SET codes = ? WHERE id = ?",
                (codes_json, existing[0]),
            )
        else:
            conn.execute(
                "INSERT INTO user_watchlists (user_id, name, codes, created_at) VALUES (?, ?, ?, ?)",
                (user_id, _DEFAULT_WATCHLIST_NAME, codes_json, now),
            )


def _sync_codes_to_settings(codes: list[str]) -> None:
    """將合併後的代碼同步到 settings.watchlist（供後端業務使用）。"""
    for c in codes:
        c = _normalize_code(c)
        if c and c not in settings.watchlist:
            settings.watchlist.append(c)


def list_codes_for_user(user_id: int = None) -> list[str]:
    """獲取自選股列表：用戶 DB 列表 ∪ 全局 settings.watchlist。"""
    if user_id is None:
        return list_codes()

    # 合併：用戶 DB 列表 + 全局列表
    user_codes = _get_user_default_watchlist_codes(user_id)
    global_codes = list_codes()
    seen: set[str] = set()
    out: list[str] = []
    for c in user_codes + global_codes:
        c = _normalize_code(c)
        if not c or c in seen:
            continue
        seen.add(c)
        out.append(c)
    return out


def ensure_in_watchlist_for_user(code: str, user_id: int = None) -> bool:
    """添加到自選：寫入用戶 DB + settings.watchlist。"""
    code = _normalize_code(code)
    if not code:
        return False

    # 始終同步到 settings（後端業務依賴）
    added_to_settings = ensure_in_watchlist(code)

    if user_id is not None:
        user_codes = _get_user_default_watchlist_codes(user_id)
        if code not in user_codes:
            user_codes.append(code)
            _save_user_default_watchlist(user_id, user_codes)
            return True
        return added_to_settings
    return added_to_settings


def remove_from_watchlist_for_user(code: str, user_id: int = None) -> bool:
    """從自選移除：從用戶 DB + settings.watchlist 中移除。"""
    code = _normalize_code(code)

    # 始終從 settings 移除
    changed = remove_from_watchlist(code)

    if user_id is not None:
        user_codes = _get_user_default_watchlist_codes(user_id)
        if code in user_codes:
            user_codes.remove(code)
            _save_user_default_watchlist(user_id, user_codes)
            return True
        return changed
    return changed
