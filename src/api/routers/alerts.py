"""預警"""
import json
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends, Query, UploadFile, File, Request
from src.config import settings
from src.core.auth import require_auth, require_admin, get_current_user
from src.core.db import get_conn, get_alert_logs
from src.utils.logger import logger
from src.api.constants import STOCK_NAMES
from src.api.dispatch import dispatch_async_task

router = APIRouter()

@router.get("/api/alerts")
async def list_alerts(limit: int = 50, code: str = None, user = Depends(get_current_user)):
    """獲取預警歷史（登錄用戶僅看自己的數據）"""
    user_id = user.id if user else None
    logs = get_alert_logs(limit=limit, code=code, user_id=user_id)
    return {"alerts": logs, "total": len(logs)}


@router.get("/api/alerts/rules")
async def get_alert_rules():
    """獲取預警規則"""
    return {"rules": settings.alert_rules}


@router.put("/api/alerts/rules")
async def update_alert_rules(rules: dict):
    """更新預警規則（運行時生效，重啟後恢復）"""
    settings.alert_rules.update(rules)
    return {"success": True, "rules": settings.alert_rules}


@router.delete("/api/alerts/rules/{code}")
async def delete_alert_rule(code: str):
    """刪除預警規則"""
    if code in settings.alert_rules:
        del settings.alert_rules[code]
        return {"success": True, "message": f"已刪除 {code}"}
    raise HTTPException(404, f"規則不存在: {code}")


@router.get("/api/alerts/rules/suggest")
async def suggest_alert_rule_api(
    code: str,
    above_pct: float = 3.0,
    below_pct: float = 3.0,
    change_pct: float = 5.0,
):
    """依最新價建議單條預警閾值（供前端一鍵填充）"""
    from src.core.alert_rules_auto import suggest_alert_rule

    try:
        return suggest_alert_rule(
            code,
            above_pct=above_pct,
            below_pct=below_pct,
            change_pct=change_pct,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/api/alerts/rules/auto")
async def auto_add_alert_rules_api(body: dict = None):
    """
    批量自動添加預警規則（依最新價 ± 百分比）

    body:
      codes: 可選代碼列表
      source: missing | watchlist | config
      above_pct / below_pct / change_pct
      skip_existing: 跳過已有規則
      overwrite: 覆蓋已有規則
    """
    from src.core.alert_rules_auto import auto_add_alert_rules

    body = body or {}
    try:
        return auto_add_alert_rules(
            codes=body.get("codes"),
            source=(body.get("source") or "missing").strip(),
            above_pct=float(body.get("above_pct", 3.0)),
            below_pct=float(body.get("below_pct", 3.0)),
            change_pct=float(body.get("change_pct", 5.0)),
            skip_existing=bool(body.get("skip_existing", True)),
            overwrite=bool(body.get("overwrite", False)),
        )
    except ValueError as e:
        raise HTTPException(400, str(e))


def _normalize_watchlist_code(code: str) -> str:
    code = str(code).strip()
    if not code:
        raise HTTPException(400, "股票代碼不能為空")
    if code.isdigit() and len(code) < 6:
        code = code.zfill(6)
    if not (code.isdigit() and len(code) == 6):
        raise HTTPException(400, "請輸入 6 位 A 股代碼，例如 600519")
    return code


def _basic_alert_rule(code: str, name: str = "", change_pct: float = 5.0) -> dict:
    from src.api.constants import STOCK_NAMES

    return {
        "name": name or STOCK_NAMES.get(code) or code,
        "price_above": None,
        "price_below": None,
        "change_pct": float(change_pct),
    }


@router.get("/api/watchlist")
async def list_watchlist(user = Depends(get_current_user)):
    """自選股列表（含簡要行情）。登錄用戶返回個人 + 全局合併列表。"""
    from src.api.constants import STOCK_NAMES
    from src.core.watchlist_store import list_codes_for_user

    user_id = user.id if user else None
    codes = list_codes_for_user(user_id)
    quotes: dict[str, dict] = {}
    try:
        from src.core.realtime import fetch_realtime

        df = fetch_realtime(codes)
        if df is not None and not df.empty:
            for row in df.to_dict(orient="records"):
                c = str(row.get("code", "")).strip()
                if c:
                    quotes[c] = row
    except Exception as e:
        logger.debug(f"自選股行情: {e}")

    items = []
    for code in codes:
        rule = settings.alert_rules.get(code) or {}
        q = quotes.get(code) or {}
        items.append({
            "code": code,
            "name": rule.get("name") or q.get("name") or STOCK_NAMES.get(code) or code,
            "price": q.get("price"),
            "change_pct": q.get("change_pct"),
            "price_above": rule.get("price_above"),
            "price_below": rule.get("price_below"),
            "alert_change_pct": rule.get("change_pct"),
        })
    return {"success": True, "items": items, "total": len(items)}


@router.post("/api/watchlist/add")
async def add_to_watchlist(
    code: str,
    name: str = "",
    auto_rule: bool = False,
    above_pct: float = 3.0,
    below_pct: float = 3.0,
    change_pct: float = 5.0,
    user = Depends(require_auth),
):
    """添加股票到自選 / 監控列表（需登入）；auto_rule=true 時嘗試依最新價生成預警閾值"""
    from src.core.watchlist_store import ensure_in_watchlist_for_user, save_runtime
    from src.core.admin_controls import is_allowed

    # 檢查自選股加入開關
    if not is_allowed("watchlist", "add", user=user):
        raise HTTPException(403, "自選股加入功能目前關閉")

    code = _normalize_watchlist_code(code)
    if code in settings.watchlist and code in settings.alert_rules:
        payload = await list_watchlist()
        return {
            "success": True,
            "message": f"{code} 已在自選列表",
            "items": payload["items"],
        }

    rule = _basic_alert_rule(code, name, change_pct)
    rule_hint = ""
    if auto_rule:
        from src.core.alert_rules_auto import suggest_alert_rule

        try:
            suggested = suggest_alert_rule(
                code,
                above_pct=above_pct,
                below_pct=below_pct,
                change_pct=change_pct,
            )
            rule = suggested["rule"]
            rule_hint = "（已自動生成預警規則）"
        except ValueError as e:
            logger.info(f"{code} 自動預警規則失敗，使用基礎規則: {e}")
            rule_hint = "（已加入；未取得最新價，預警閾值請稍後編輯）"

    settings.alert_rules[code] = rule
    ensure_in_watchlist_for_user(code, user.id)
    save_runtime()
    display = rule.get("name") or code
    return {
        "success": True,
        "message": f"{display}（{code}）已加入自選{rule_hint}",
        "rule": rule,
        "items": (await list_watchlist())["items"],
    }


@router.delete("/api/watchlist/{code}")
async def remove_from_watchlist(code: str, user = Depends(get_current_user)):
    """從自選列表移除。登錄用戶同時從個人列表移除。"""
    from src.core.watchlist_store import remove_from_watchlist_for_user

    code = _normalize_watchlist_code(code)
    user_id = user.id if user else None
    if not remove_from_watchlist_for_user(code, user_id):
        raise HTTPException(404, f"自選列表中無 {code}")
    return {
        "success": True,
        "message": f"已移除 {code}",
        "items": (await list_watchlist())["items"],
    }
