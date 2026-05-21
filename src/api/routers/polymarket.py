"""
Polymarket 預測市場 API — 只讀端點（Gamma + CLOB）

演示模式：GET 在白名單內可無 Token 訪問；POST /sync 需登錄。
"""
from fastapi import APIRouter, Depends, HTTPException, Query

from src.config import settings
from src.core.auth import require_auth
from src.core.polymarket.service import PolymarketDisabledError, get_polymarket_service
from src.api.dispatch import dispatch_async_task

router = APIRouter(tags=["polymarket"])


def _svc():
    """獲取業務服務單例。"""
    return get_polymarket_service()


def _handle_disabled(exc: PolymarketDisabledError):
    raise HTTPException(status_code=503, detail=str(exc))


@router.get("/api/polymarket/markets")
async def api_polymarket_markets(
    limit: int = Query(None, ge=1, le=200),
    offset: int = Query(0, ge=0),
    active: bool = True,
    tag: str = None,
    order: str = "volume",
):
    """市場列表：成交量/流動性排序，可選標籤篩選。"""
    try:
        return _svc().list_markets(
            limit=limit, offset=offset, active=active, tag=tag, order=order,
        )
    except PolymarketDisabledError as e:
        _handle_disabled(e)


@router.get("/api/polymarket/markets/{market_id}")
async def api_polymarket_market_detail(market_id: str):
    """市場詳情（id、condition_id 或 slug）。"""
    try:
        return _svc().get_market(market_id)
    except PolymarketDisabledError as e:
        _handle_disabled(e)
    except Exception as e:
        raise HTTPException(404, f"未找到市場: {market_id} — {e}")


@router.get("/api/polymarket/events")
async def api_polymarket_events(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    active: bool = True,
):
    """事件列表。"""
    try:
        return _svc().list_events(limit=limit, offset=offset, active=active)
    except PolymarketDisabledError as e:
        _handle_disabled(e)


@router.get("/api/polymarket/tags")
async def api_polymarket_tags():
    """可用標籤。"""
    try:
        return _svc().list_tags()
    except PolymarketDisabledError as e:
        _handle_disabled(e)


@router.get("/api/polymarket/search")
async def api_polymarket_search(
    q: str = Query(..., min_length=1, max_length=200),
    limit: int = Query(20, ge=1, le=100),
):
    """關鍵字搜尋。"""
    try:
        return _svc().search(q, limit=limit)
    except PolymarketDisabledError as e:
        _handle_disabled(e)


@router.get("/api/polymarket/price-history")
async def api_polymarket_price_history(
    token_id: str = Query(..., min_length=1),
    interval: str = "1d",
    fidelity: int = Query(60, ge=1, le=1440),
    start_ts: int = None,
    end_ts: int = None,
):
    """CLOB 價格歷史（用於圖表）。"""
    try:
        return _svc().get_price_history(
            token_id,
            interval=interval,
            fidelity=fidelity,
            start_ts=start_ts,
            end_ts=end_ts,
            persist=False,
        )
    except PolymarketDisabledError as e:
        _handle_disabled(e)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/api/polymarket/orderbook")
async def api_polymarket_orderbook(
    token_id: str = Query(..., min_length=1),
):
    """CLOB 訂單簿（Yes/No token 各可查）。"""
    try:
        return _svc().get_orderbook(token_id)
    except PolymarketDisabledError as e:
        _handle_disabled(e)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/api/polymarket/snapshots")
async def api_polymarket_snapshots(limit: int = Query(50, ge=1, le=500)):
    """讀取本地快照（無需外網）。"""
    try:
        return _svc().list_snapshots(limit=limit)
    except PolymarketDisabledError as e:
        _handle_disabled(e)


@router.post("/api/polymarket/sync")
async def api_polymarket_sync(
    limit: int = Query(None, ge=1, le=200),
    user=Depends(require_auth),
):
    """異步同步熱門市場到本地 SQLite 快照。"""
    from src.core.task_manager import create_task

    try:
        _svc()._ensure_enabled()
    except PolymarketDisabledError as e:
        _handle_disabled(e)

    cap = limit or settings.polymarket_default_limit
    task_params = {"limit": cap}
    task = create_task(
        "polymarket_sync",
        task_params,
        title=f"Polymarket 快照同步（{cap} 條）",
    )
    if task.get("is_duplicate"):
        return {
            "success": True,
            "task_id": task["task_id"],
            "is_duplicate": True,
            "message": "相同同步任務執行中",
            "async": True,
        }

    task_id = task["task_id"]
    if task.get("status") == "completed" and task.get("result"):
        return {
            "success": True,
            "task_id": task_id,
            "async": False,
            "from_cache": task.get("from_cache"),
            "result": task.get("result"),
        }

    return dispatch_async_task(
        task_id,
        lambda: _svc().sync_snapshots(limit=cap),
        cache_namespace=None,
    )


# ── 概率驅動預警與策略信號 ─────────────────────────────────────


@router.get("/api/polymarket/alerts/rules")
async def api_polymarket_alert_rules_list():
    """列出 Polymarket 預警規則。"""
    from src.core.polymarket.alert_store import init_polymarket_alert_tables, list_alert_rules

    try:
        _svc()._ensure_enabled()
    except PolymarketDisabledError as e:
        _handle_disabled(e)
    init_polymarket_alert_tables()
    rules = list_alert_rules()
    return {"rules": rules, "total": len(rules)}


@router.post("/api/polymarket/alerts/rules")
async def api_polymarket_alert_rules_upsert(body: dict, user=Depends(require_auth)):
    """新增/更新預警規則（按 market_key 唯一）。"""
    from src.core.polymarket.alert_store import init_polymarket_alert_tables, upsert_alert_rule

    try:
        _svc()._ensure_enabled()
    except PolymarketDisabledError as e:
        _handle_disabled(e)
    init_polymarket_alert_tables()
    try:
        rule = upsert_alert_rule(body or {})
        return {"success": True, "rule": rule}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.delete("/api/polymarket/alerts/rules/{rule_id}")
async def api_polymarket_alert_rules_delete(rule_id: int, user=Depends(require_auth)):
    from src.core.polymarket.alert_store import delete_alert_rule

    try:
        _svc()._ensure_enabled()
    except PolymarketDisabledError as e:
        _handle_disabled(e)
    if not delete_alert_rule(rule_id):
        raise HTTPException(404, f"規則不存在: {rule_id}")
    return {"success": True}


@router.get("/api/polymarket/alerts/logs")
async def api_polymarket_alert_logs(limit: int = Query(50, ge=1, le=200)):
    from src.core.polymarket.alerts import get_polymarket_alert_logs

    try:
        _svc()._ensure_enabled()
    except PolymarketDisabledError as e:
        _handle_disabled(e)
    logs = get_polymarket_alert_logs(limit=limit)
    return {"alerts": logs, "total": len(logs)}


@router.post("/api/polymarket/alerts/evaluate")
async def api_polymarket_alerts_evaluate(user=Depends(require_auth)):
    """立即執行一輪概率預警評估（並發通知）。"""
    from src.core.polymarket.alerts import run_polymarket_alert_cycle

    try:
        return run_polymarket_alert_cycle()
    except PolymarketDisabledError as e:
        _handle_disabled(e)


@router.get("/api/polymarket/strategy-signals")
async def api_polymarket_strategy_signals(
    limit: int = Query(30, ge=1, le=100),
    tag: str = None,
    markets: str = Query(None, description="逗號分隔 slug/id"),
):
    """概率驅動策略信號（偏多/偏空/觀望，非 Backtrader 回測）。"""
    from src.core.polymarket.strategy_signals import compute_strategy_signals

    try:
        keys = [k.strip() for k in (markets or "").split(",") if k.strip()] or None
        return compute_strategy_signals(market_keys=keys, limit=limit, tag=tag)
    except PolymarketDisabledError as e:
        _handle_disabled(e)
