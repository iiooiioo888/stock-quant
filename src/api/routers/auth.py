"""認證與用戶"""
import json
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends, Query, UploadFile, File, Request
from src.config import settings
from src.core.auth import require_auth, require_admin
from src.core.db import get_conn
from src.utils.logger import logger
from src.api.constants import STOCK_NAMES
from src.api.dispatch import dispatch_async_task

router = APIRouter()

@router.post("/api/auth/register")
async def auth_register(body: dict):
    """用戶註冊（需邀請碼）"""
    from src.core.auth import create_user
    from src.core.invite_codes import validate_code, use_code
    from src.core.admin_controls import is_allowed

    username = (body.get("username") or "").strip()
    password = body.get("password") or ""
    invite_code = (body.get("invite_code") or "").strip()

    if not username or not password:
        raise HTTPException(400, "用戶名和密碼不能為空")
    if len(username) < 3:
        raise HTTPException(400, "用戶名至少 3 個字符")
    if len(password) < 6:
        raise HTTPException(400, "密碼至少 6 個字符")

    # 檢查註冊開關
    if not is_allowed("users", "register"):
        raise HTTPException(403, "目前未開放註冊")

    # 邀請碼驗證（invite_only 模式下必填）
    if is_allowed("users", "invite_only"):
        if not invite_code:
            raise HTTPException(400, "需要邀請碼才能註冊")
        valid, reason = validate_code(invite_code)
        if not valid:
            raise HTTPException(400, reason)

    try:
        user = create_user(username, password)
        # 註冊成功後標記邀請碼已使用
        if invite_code:
            use_code(invite_code)
        from src.core.auth import create_token
        token = create_token(user.id, user.role)
        return {
            "success": True,
            "message": "註冊成功",
            "token": token,
            "user": user.to_dict(),
        }
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/api/auth/login")
async def auth_login(body: dict):
    """用戶登錄"""
    from src.core.auth import get_user_by_username, verify_password, create_token
    
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""
    
    if not username or not password:
        raise HTTPException(400, "用戶名和密碼不能為空")
    
    user = get_user_by_username(username)
    if not user or not verify_password(password, user.password_hash):
        raise HTTPException(401, "用戶名或密碼錯誤")
    
    token = create_token(user.id, user.role)
    return {
        "success": True,
        "message": "登錄成功",
        "token": token,
        "user": user.to_dict(),
    }


@router.get("/api/auth/me")
async def auth_me(user = Depends(require_auth)):
    """獲取當前登錄用戶信息"""
    from src.core.entitlements import billing_summary

    payload = user.to_dict()
    payload["billing"] = billing_summary(user)
    return {"success": True, "user": payload}


@router.put("/api/auth/settings")
async def auth_update_settings(body: dict, user = Depends(require_auth)):
    """更新當前用戶設置"""
    import sqlite3
    settings_json = json.dumps(body.get("settings", {}), ensure_ascii=False)
    with get_conn() as conn:
        conn.execute("UPDATE users SET settings = ? WHERE id = ?", (settings_json, user.id))
    user.settings = body.get("settings", {})
    return {"success": True, "message": "設置已更新", "settings": user.settings}


# ====== 用戶數據 API（需登錄） ======

@router.get("/api/user/watchlists")
async def user_get_watchlists(user = Depends(require_auth)):
    """獲取當前用戶的監控列表"""
    import sqlite3
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM user_watchlists WHERE user_id = ? ORDER BY id", (user.id,)
        ).fetchall()
    watchlists = []
    for row in rows:
        d = dict(row)
        try:
            d["codes"] = json.loads(d["codes"])
        except (json.JSONDecodeError, TypeError):
            d["codes"] = []
        watchlists.append(d)
    return {"success": True, "watchlists": watchlists}


@router.post("/api/user/watchlists")
async def user_create_watchlist(body: dict, user = Depends(require_auth)):
    """創建監控列表"""
    import sqlite3
    from src.core.entitlements import check_watchlist_codes_cap

    name = (body.get("name") or "").strip()
    codes = body.get("codes", [])
    if not name:
        raise HTTPException(400, "請提供監控列表名稱")
    if isinstance(codes, list):
        check_watchlist_codes_cap(user, len(codes))
    
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    codes_json = json.dumps(codes, ensure_ascii=False)
    with get_conn() as conn:
        cursor = conn.execute(
            "INSERT INTO user_watchlists (user_id, name, codes, created_at) VALUES (?, ?, ?, ?)",
            (user.id, name, codes_json, now),
        )
    return {"success": True, "id": cursor.lastrowid, "message": f"監控列表 '{name}' 已創建"}


@router.put("/api/user/watchlists/{watchlist_id}")
async def user_update_watchlist(watchlist_id: int, body: dict, user = Depends(require_auth)):
    """更新監控列表"""
    import sqlite3
    from src.core.entitlements import check_watchlist_codes_cap

    name = body.get("name")
    codes = body.get("codes")
    if codes is not None and isinstance(codes, list):
        check_watchlist_codes_cap(user, len(codes))

    with get_conn() as conn:
        # 確認屬於當前用戶
        existing = conn.execute(
            "SELECT id FROM user_watchlists WHERE id = ? AND user_id = ?",
            (watchlist_id, user.id),
        ).fetchone()
        if not existing:
            raise HTTPException(404, "監控列表不存在")
        
        updates = []
        params = []
        if name is not None:
            updates.append("name = ?")
            params.append(name)
        if codes is not None:
            updates.append("codes = ?")
            params.append(json.dumps(codes, ensure_ascii=False))
        
        if updates:
            params.append(watchlist_id)
            conn.execute(f"UPDATE user_watchlists SET {', '.join(updates)} WHERE id = ?", params)
    
    return {"success": True, "message": "監控列表已更新"}


@router.delete("/api/user/watchlists/{watchlist_id}")
async def user_delete_watchlist(watchlist_id: int, user = Depends(require_auth)):
    """刪除監控列表"""
    with get_conn() as conn:
        cursor = conn.execute(
            "DELETE FROM user_watchlists WHERE id = ? AND user_id = ?",
            (watchlist_id, user.id),
        )
    if cursor.rowcount == 0:
        raise HTTPException(404, "監控列表不存在")
    return {"success": True, "message": "監控列表已刪除"}


@router.get("/api/user/alerts")
async def user_get_alerts(user = Depends(require_auth)):
    """獲取當前用戶的預警規則"""
    import sqlite3
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM user_alert_rules WHERE user_id = ? ORDER BY id", (user.id,)
        ).fetchall()
    alerts = []
    for row in rows:
        d = dict(row)
        try:
            d["params"] = json.loads(d["params"])
        except (json.JSONDecodeError, TypeError):
            d["params"] = {}
        alerts.append(d)
    return {"success": True, "alerts": alerts}


@router.post("/api/user/alerts")
async def user_create_alert(body: dict, user = Depends(require_auth)):
    """創建預警規則"""
    code = (body.get("code") or "").strip()
    rule_type = (body.get("rule_type") or "").strip()
    params = body.get("params", {})
    
    if not code or not rule_type:
        raise HTTPException(400, "請提供 code 和 rule_type")
    
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    params_json = json.dumps(params, ensure_ascii=False)
    with get_conn() as conn:
        cursor = conn.execute(
            """INSERT INTO user_alert_rules (user_id, code, rule_type, params, enabled, created_at)
               VALUES (?, ?, ?, ?, 1, ?)""",
            (user.id, code, rule_type, params_json, now),
        )
    return {"success": True, "id": cursor.lastrowid, "message": "預警規則已創建"}


@router.put("/api/user/alerts/{alert_id}")
async def user_update_alert(alert_id: int, body: dict, user = Depends(require_auth)):
    """更新預警規則"""
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT id FROM user_alert_rules WHERE id = ? AND user_id = ?",
            (alert_id, user.id),
        ).fetchone()
        if not existing:
            raise HTTPException(404, "預警規則不存在")
        
        updates = []
        params = []
        if "code" in body:
            updates.append("code = ?")
            params.append(body["code"])
        if "rule_type" in body:
            updates.append("rule_type = ?")
            params.append(body["rule_type"])
        if "params" in body:
            updates.append("params = ?")
            params.append(json.dumps(body["params"], ensure_ascii=False))
        if "enabled" in body:
            updates.append("enabled = ?")
            params.append(1 if body["enabled"] else 0)
        
        if updates:
            params.append(alert_id)
            conn.execute(f"UPDATE user_alert_rules SET {', '.join(updates)} WHERE id = ?", params)
    
    return {"success": True, "message": "預警規則已更新"}


@router.delete("/api/user/alerts/{alert_id}")
async def user_delete_alert(alert_id: int, user = Depends(require_auth)):
    """刪除預警規則"""
    with get_conn() as conn:
        cursor = conn.execute(
            "DELETE FROM user_alert_rules WHERE id = ? AND user_id = ?",
            (alert_id, user.id),
        )
    if cursor.rowcount == 0:
        raise HTTPException(404, "預警規則不存在")
    return {"success": True, "message": "預警規則已刪除"}


@router.get("/api/user/backtest-history")
async def user_backtest_history(user = Depends(require_auth), limit: int = 50):
    """獲取當前用戶的回測歷史"""
    from src.core.db import get_backtest_history
    results = get_backtest_history(limit=limit, user_id=user.id)
    return {"success": True, "results": results, "total": len(results)}


# ====== 管理員 API ======

@router.get("/api/admin/users")
async def admin_list_users(user = Depends(require_admin)):
    """列出所有用戶（僅管理員）"""
    from src.core.auth import list_users
    from src.core.entitlements import effective_plan_id
    from src.models.user import User

    users = list_users()
    for row in users:
        u = User.from_row({**row, "password_hash": ""})
        row["plan_id"] = effective_plan_id(u)
    return {"success": True, "users": users, "total": len(users)}


@router.put("/api/admin/users/{target_user_id}/role")
async def admin_change_role(target_user_id: int, body: dict, user = Depends(require_admin)):
    """修改用戶角色（僅管理員）"""
    from src.core.auth import update_user_role
    
    new_role = (body.get("role") or "").strip()
    if new_role not in ("admin", "user"):
        raise HTTPException(400, "無效角色，可選: admin, user")
    
    # 不允許管理員降級自己
    if target_user_id == user.id and new_role != "admin":
        raise HTTPException(400, "不能降級自己的管理員權限")
    
    try:
        success = update_user_role(target_user_id, new_role)
        if not success:
            raise HTTPException(404, "用戶不存在")
        return {"success": True, "message": f"用戶角色已更改為 {new_role}"}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.delete("/api/admin/users/{target_user_id}")
async def admin_delete_user(target_user_id: int, user = Depends(require_admin)):
    """刪除用戶（僅管理員）"""
    from src.core.auth import delete_user
    
    # 不允許管理員刪除自己
    if target_user_id == user.id:
        raise HTTPException(400, "不能刪除自己的賬號")
    
    success = delete_user(target_user_id)
    if not success:
        raise HTTPException(404, "用戶不存在")
    return {"success": True, "message": "用戶已刪除"}


# ====== 管理員控制開關 ======

@router.get("/api/admin/controls")
async def admin_get_controls(user = Depends(require_admin)):
    """獲取管理員全域控制開關（僅管理員）"""
    from src.core.admin_controls import get_controls
    return {"success": True, "controls": get_controls()}


@router.put("/api/admin/controls")
async def admin_update_controls(body: dict, user = Depends(require_admin)):
    """更新管理員全域控制開關（僅管理員）"""
    from src.core.admin_controls import set_controls, get_controls
    controls = body.get("controls") if isinstance(body, dict) else None
    if not isinstance(controls, dict):
        raise HTTPException(400, "請提供 controls（dict）")
    prev = get_controls()
    updated = set_controls(controls)
    return {"success": True, "controls": updated, "previous": prev}


# ====== 邀請碼管理（僅管理員） ======

@router.get("/api/admin/invite-codes")
async def admin_list_invite_codes(user = Depends(require_admin)):
    """列出所有邀請碼"""
    from src.core.invite_codes import list_codes
    codes = list_codes()
    return {"success": True, "codes": codes, "total": len(codes)}


@router.post("/api/admin/invite-codes")
async def admin_generate_invite_code(body: dict, user = Depends(require_admin)):
    """生成邀請碼"""
    from src.core.invite_codes import generate_code

    max_uses = int(body.get("max_uses", 1))
    expires_at = body.get("expires_at")  # ISO format string or None

    if max_uses < 1:
        raise HTTPException(400, "最大使用次數至少為 1")

    code = generate_code(created_by=user.id, max_uses=max_uses, expires_at=expires_at)
    return {"success": True, "code": code, "message": f"邀請碼 {code} 已生成"}


@router.delete("/api/admin/invite-codes/{code}")
async def admin_delete_invite_code(code: str, user = Depends(require_admin)):
    """刪除邀請碼"""
    from src.core.invite_codes import delete_code
    if not delete_code(code):
        raise HTTPException(404, "邀請碼不存在")
    return {"success": True, "message": f"邀請碼 {code} 已刪除"}


# ====== 策略管理（僅管理員） ======

@router.get("/api/admin/strategies")
async def admin_list_strategies(user = Depends(require_admin)):
    """列出所有策略（管理員用）"""
    from src.marketplace.registry import StrategyMarketplace
    marketplace = StrategyMarketplace()
    strategies = marketplace.list_all_strategies()
    return {"success": True, "strategies": strategies, "total": len(strategies)}


@router.delete("/api/admin/strategies/{strategy_id}")
async def admin_delete_strategy(strategy_id: str, user = Depends(require_admin)):
    """管理員刪除策略"""
    from src.marketplace.registry import StrategyMarketplace
    marketplace = StrategyMarketplace()
    result = marketplace.admin_delete_strategy(strategy_id)
    if not result["success"]:
        raise HTTPException(404, result.get("error", "策略不存在"))
    return result
