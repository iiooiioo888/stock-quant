"""預警"""
import json
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends, Query, UploadFile, File, Request
from src.config import settings
from src.core.auth import require_auth, require_admin
from src.core.db import get_conn, get_alert_logs
from src.utils.logger import logger
from src.api.constants import STOCK_NAMES
from src.api.dispatch import dispatch_async_task

router = APIRouter()

@router.get("/api/alerts")
async def list_alerts(limit: int = 50, code: str = None):
    """獲取預警歷史"""
    logs = get_alert_logs(limit=limit, code=code)
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


@router.post("/api/watchlist/add")
async def add_to_watchlist(
    code: str,
    name: str = "",
    auto_rule: bool = False,
    above_pct: float = 3.0,
    below_pct: float = 3.0,
    change_pct: float = 5.0,
):
    """添加股票到監控列表；auto_rule=true 時依最新價生成預警閾值"""
    if code in settings.alert_rules:
        return {"success": True, "message": f"{code} 已在監控列表", "rules": settings.alert_rules}

    rule = {
        "name": name or code,
        "price_above": None,
        "price_below": None,
        "change_pct": change_pct,
    }
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
        except ValueError as e:
            raise HTTPException(400, str(e))

    settings.alert_rules[code] = rule
    if code not in settings.watchlist:
        settings.watchlist.append(code)
    msg = f"{code} 已加入監控"
    if auto_rule:
        msg += "（已自動生成預警規則）"
    return {"success": True, "message": msg, "rules": settings.alert_rules, "rule": rule}
