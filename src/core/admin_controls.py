"""
管理員全域控制開關（可持久化）：

- 讓 admin 可以一鍵控制：功能入口 / 策略庫 / 任務列表等是否對一般用戶可用
- 使用 data/runtime_admin_controls.json 持久化（類似 watchlist_store）
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.config import DATA_DIR
from src.utils.logger import logger

_RUNTIME_PATH = DATA_DIR / "runtime_admin_controls.json"


DEFAULT_CONTROLS: dict[str, Any] = {
    "version": 3,
    # master: True=對所有人開放；False=僅 admin 可用（非 admin 一律視為關閉）
    "public_enabled": True,
    # v1 兼容欄位（仍接受寫入；讀取時會映射到 scopes.*）
    "features_enabled": True,
    "strategies_enabled": True,
    "tasks_enabled": True,
    "users_enabled": True,
    "watchlist_enabled": True,
    # v2/v3: 細粒度控制
    "scopes": {
        "features": {
            "enabled": True,
            # 逐功能控制（可單獨關閉某個端點族群）
            "backtest": True,
            "backtest_advanced": True,
            "backtest_multi": True,
            "optimize": True,
            "portfolio": True,
            "walkforward": True,
            "auto_optimize": True,
            "target_search": True,
        },
        "strategies": {
            "enabled": True,
            # API 動作
            "list": True,
            "params": True,
            "create": True,
            # 來源控制
            "builtin_enabled": True,
            "user_enabled": True,
            # 名稱白/黑名單（空＝不限制）
            "allowed_names": [],
            "blocked_names": [],
        },
        "users": {
            "enabled": True,
            "register": True,
            "invite_only": True,
        },
        "watchlist": {
            "enabled": True,
            "add": True,
        },
        "tasks": {
            "enabled": True,
            # 查詢類
            "list": True,
            "queue": True,
            "types": True,
            "stats": True,
            "detail": True,
            "params": True,
            "full": True,
            "logs": True,
            # 操作類
            "cancel": True,
            "delete": True,
            "retry": True,
            "pipeline": True,
            "batch_cancel": True,
            "batch_delete": True,
            "cancel_pending": True,
            "clear_completed": True,
            "cleanup": True,
        },
    },
}

_controls: dict[str, Any] | None = None


def load_controls() -> dict[str, Any]:
    if not _RUNTIME_PATH.is_file():
        return dict(DEFAULT_CONTROLS)
    try:
        data = json.loads(_RUNTIME_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return _normalize_controls(data)
    except Exception as e:
        logger.warning(f"讀取 runtime_admin_controls 失敗: {e}")
    return dict(DEFAULT_CONTROLS)


def save_controls(controls: dict[str, Any]) -> None:
    payload = _normalize_controls(controls)
    try:
        _RUNTIME_PATH.parent.mkdir(parents=True, exist_ok=True)
        _RUNTIME_PATH.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as e:
        logger.warning(f"寫入 runtime_admin_controls 失敗: {e}")


def get_controls() -> dict[str, Any]:
    global _controls
    if _controls is None:
        _controls = load_controls()
    return dict(_controls)


def set_controls(new_controls: dict[str, Any]) -> dict[str, Any]:
    global _controls
    merged = _merge_controls(get_controls(), new_controls)
    _controls = merged
    save_controls(merged)
    return dict(_controls)


def apply_controls_on_startup() -> None:
    """啟動時載入持久化控制開關到記憶體。"""
    global _controls
    _controls = load_controls()


def is_admin(user: Any) -> bool:
    return bool(getattr(user, "role", None) == "admin")


def is_scope_enabled(scope: str, user: Any = None) -> bool:
    """
    scope:
      - features
      - strategies
      - tasks
    """
    c = get_controls()
    if is_admin(user):
        return True
    if not c.get("public_enabled", True):
        return False
    scopes = (c.get("scopes") or {})
    s = scopes.get(scope) if isinstance(scopes, dict) else None
    if isinstance(s, dict) and "enabled" in s:
        return bool(s.get("enabled", True))
    # fallback to v1
    if scope == "features":
        return bool(c.get("features_enabled", True))
    if scope == "strategies":
        return bool(c.get("strategies_enabled", True))
    if scope == "tasks":
        return bool(c.get("tasks_enabled", True))
    if scope == "users":
        return bool(c.get("users_enabled", True))
    if scope == "watchlist":
        return bool(c.get("watchlist_enabled", True))
    return True


def is_allowed(scope: str, action: str | None = None, *, user: Any = None, name: str | None = None) -> bool:
    """
    更細粒度判定：
    - scope: features / strategies / tasks
    - action: 具體動作或子功能 key
    - name: 例如策略名稱（策略列表時可套用白/黑名單）
    """
    c = get_controls()
    if is_admin(user):
        return True
    if not c.get("public_enabled", True):
        return False
    if not is_scope_enabled(scope, user=user):
        return False
    scopes = c.get("scopes") or {}
    s = scopes.get(scope) if isinstance(scopes, dict) else None
    if not isinstance(s, dict):
        return True
    if action:
        if action in s and s.get(action) is False:
            return False
    # strategies name filtering
    if scope == "strategies" and name:
        allowed = s.get("allowed_names") or []
        blocked = s.get("blocked_names") or []
        if isinstance(blocked, list) and name in blocked:
            return False
        if isinstance(allowed, list) and allowed:
            return name in allowed
    return True


def _normalize_controls(raw: dict[str, Any]) -> dict[str, Any]:
    """
    將 v1/v2 任意輸入轉成完整 v2 結構（保留向下相容）。
    """
    out = json.loads(json.dumps(DEFAULT_CONTROLS))  # deep copy

    def _bool(k: str, default: bool) -> bool:
        if k in raw:
            return bool(raw.get(k))
        return bool(default)

    out["public_enabled"] = _bool("public_enabled", out["public_enabled"])
    out["features_enabled"] = _bool("features_enabled", out["features_enabled"])
    out["strategies_enabled"] = _bool("strategies_enabled", out["strategies_enabled"])
    out["tasks_enabled"] = _bool("tasks_enabled", out["tasks_enabled"])
    out["users_enabled"] = _bool("users_enabled", out.get("users_enabled", True))
    out["watchlist_enabled"] = _bool("watchlist_enabled", out.get("watchlist_enabled", True))

    scopes = raw.get("scopes")
    if isinstance(scopes, dict):
        for scope_name, scope_def in out["scopes"].items():
            incoming = scopes.get(scope_name)
            if not isinstance(incoming, dict):
                continue
            for k in list(scope_def.keys()):
                if k in incoming:
                    if k in ("allowed_names", "blocked_names"):
                        scope_def[k] = incoming.get(k) if isinstance(incoming.get(k), list) else scope_def[k]
                    else:
                        scope_def[k] = bool(incoming.get(k))

    # v1 映射到 v2 scopes.enabled（若使用者只傳 v1）
    out["scopes"]["features"]["enabled"] = bool(out["features_enabled"]) and bool(out["scopes"]["features"]["enabled"])
    out["scopes"]["strategies"]["enabled"] = bool(out["strategies_enabled"]) and bool(out["scopes"]["strategies"]["enabled"])
    out["scopes"]["tasks"]["enabled"] = bool(out["tasks_enabled"]) and bool(out["scopes"]["tasks"]["enabled"])
    out["scopes"]["users"]["enabled"] = bool(out["users_enabled"]) and bool(out["scopes"]["users"]["enabled"])
    out["scopes"]["watchlist"]["enabled"] = bool(out["watchlist_enabled"]) and bool(out["scopes"]["watchlist"]["enabled"])
    return out


def _merge_controls(current: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    merged = _normalize_controls(current)
    # 允許直接更新 v1 欄位
    for k in ("public_enabled", "features_enabled", "strategies_enabled", "tasks_enabled", "users_enabled", "watchlist_enabled"):
        if k in patch:
            merged[k] = bool(patch.get(k))
    # 允許更新 scopes（巢狀）
    if isinstance(patch.get("scopes"), dict):
        tmp = _normalize_controls({**merged, "scopes": patch.get("scopes")})
        merged["scopes"] = tmp["scopes"]
    # 最後再跑一次 v1→v2 映射
    return _normalize_controls(merged)

