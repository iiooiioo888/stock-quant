"""
FastAPI 應用 — Web API + 靜態前端 + WebSocket 實時推送
"""
import os
import time
import json
from pathlib import Path
from datetime import datetime
from contextlib import asynccontextmanager


from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query, UploadFile, File, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse

from src.config import settings
from src.core.db import init_db, get_db_stats, get_alert_logs, get_conn
from src.core.auth import require_auth, require_admin
from src.utils.logger import logger

from src.api.constants import STOCK_NAMES
from src.api.demo import seed_demo_data
from src.api import state
from src.api.routers.health import router as health_router
from src.api.routers.tasks import router as tasks_router
from src.api.routers.indices import router as indices_router
from src.api.routers.dashboard_market import router as dashboard_market_router
from src.api.ws import router as ws_router, ws_realtime_push

# 啟動時間




@asynccontextmanager
async def lifespan(app: FastAPI):
    """應用生命週期"""
    init_db()
    logger.info(f"🚀 {settings.app_name} v{settings.app_version} 啟動")
    logger.info(f"   http://{settings.web_host}:{settings.web_port}")

    # 演示模式或數據為空時：自動填充數據
    if settings.demo_mode:
        seed_demo_data()
    else:
        # 非演示模式也檢查：如果數據庫為空，自動下載基礎數據
        try:
            from src.core.db import load_all_codes
            codes = load_all_codes()
            if not codes:
                logger.info("📦 數據庫為空，自動下載基礎數據...")
                seed_demo_data()
        except Exception:
            seed_demo_data()

    # 初始化排行榜表
    try:
        from src.core.leaderboard import init_leaderboard_table
        init_leaderboard_table()
    except Exception as e:
        logger.debug(f"排行榜表初始化跳過: {e}")

    # 自動發現用戶策略
    try:
        from src.core.strategy_base import list_user_strategies
        user_strategies = list_user_strategies()
        if user_strategies:
            logger.info(f"📋 已加載 {len(user_strategies)} 個用戶策略: {[s['name'] for s in user_strategies]}")
        else:
            logger.info("📋 用戶策略目錄為空（運行 `python main.py strategy create <名稱>` 創建）")
    except Exception as e:
        logger.debug(f"用戶策略發現跳過: {e}")

    # 啟動定時任務調度器
    try:
        from src.core.scheduler import start_scheduler
        start_scheduler()
    except Exception as e:
        logger.debug(f"調度器啟動跳過: {e}")

    # 安全摘要
    _ws_auth = "✅ 已啟用" if settings.effective_ws_auth_required else "⚠️ 已關閉（演示/開發模式）"
    _jwt_ok = "✅ 已配置" if settings.jwt_secret else "⚠️ 未配置（自動生成）"
    logger.info(f"🔒 安全摘要: WS認證={_ws_auth} | JWT={_jwt_ok} | CORS={settings.cors_origins[:50]}")

    # 啟動 WebSocket 後台推送
    import asyncio
    _ws_task = asyncio.create_task(ws_realtime_push())

    yield

    # 關閉 WebSocket 推送
    _ws_task.cancel()
    try:
        await _ws_task
    except asyncio.CancelledError:
        pass
    # 關閉調度器
    try:
        from src.core.scheduler import stop_scheduler
        stop_scheduler()
    except Exception:
        pass
    logger.info("👋 應用關閉")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)

app.include_router(health_router)
app.include_router(tasks_router)
app.include_router(indices_router)
app.include_router(dashboard_market_router)
app.include_router(ws_router)

# CORS
_cors_origins = settings.cors_origins.split(",") if settings.cors_origins else ["http://localhost:8000"]

# 安全檢查：非 debug 模式下，CORS 包含 localhost 時警告
if not settings.debug:
    _localhost_origins = [o for o in _cors_origins if "localhost" in o or "127.0.0.1" in o]
    if _localhost_origins and len(_localhost_origins) == len(_cors_origins):
        logger.warning(
            "⚠️  CORS 僅允許 localhost！雲端部署請設置 SQ_CORS_ORIGINS 環境變量為實際域名，"
            "否則前端將無法調用 API。示例: SQ_CORS_ORIGINS=https://your-domain.com"
        )

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API / 靜態資源 GZip（減少傳輸體積）
app.add_middleware(GZipMiddleware, minimum_size=512)


@app.middleware("http")
async def static_cache_middleware(request: Request, call_next):
    """靜態資源長期緩存，加速頁面二次載入"""
    response = await call_next(request)
    path = request.url.path
    if path.startswith("/static/"):
        if path.endswith((".js", ".css")):
            response.headers["Cache-Control"] = "public, max-age=86400"
        elif path.endswith((".png", ".jpg", ".ico", ".svg", ".woff2")):
            response.headers["Cache-Control"] = "public, max-age=604800"
    return response


# ============================================================
# API 限流 — 有界滑動窗口限流（自動清理，無內存泄漏）
# ============================================================
class _RateLimiter:
    """
    有界滑動窗口限流器。

    - 每 IP 維護最近 60 秒的請求時間戳列表
    - 當 IP 數超過 _MAX_IPS 時，批量驅逐最老的 IP
    - 每次請求自動清理該 IP 的過期時間戳
    """

    _MAX_IPS = 10000          # 最多追蹤 1 萬個 IP
    _EVICT_BATCH = 2000       # 每次驅逐 2000 個最老 IP
    _CLEANUP_INTERVAL = 300   # 全量過期清理間隔（秒）

    def __init__(self, limit_per_minute: int):
        self._limit = limit_per_minute
        self._store: dict[str, list[float]] = {}        # {ip: [timestamps]}
        self._last_seen: dict[str, float] = {}           # {ip: last_request_time}
        self._last_full_cleanup = time.time()

    def check(self, client_ip: str) -> tuple[bool, int]:
        """
        檢查是否允許請求。

        Returns:
            (allowed: bool, retry_after: int)
        """
        now = time.time()
        window_start = now - 60

        # 定期全量清理過期 IP（防止長時間無請求的 IP 殘留）
        if now - self._last_full_cleanup > self._CLEANUP_INTERVAL:
            self._full_cleanup(now)
            self._last_full_cleanup = now

        # IP 數超限時驅逐最老的
        if len(self._store) >= self._MAX_IPS:
            self._evict_oldest()

        # 取出並清理該 IP 的過期時間戳
        timestamps = self._store.get(client_ip, [])
        timestamps = [t for t in timestamps if t > window_start]

        if len(timestamps) >= self._limit:
            retry_after = int(timestamps[0] - window_start) + 1
            self._store[client_ip] = timestamps
            self._last_seen[client_ip] = now
            return False, max(retry_after, 1)

        timestamps.append(now)
        self._store[client_ip] = timestamps
        self._last_seen[client_ip] = now
        return True, 0

    def _evict_oldest(self):
        """驅逐最久沒活動的 _EVICT_BATCH 個 IP"""
        if len(self._last_seen) < self._EVICT_BATCH:
            return
        sorted_ips = sorted(self._last_seen, key=lambda ip: self._last_seen[ip])
        for ip in sorted_ips[: self._EVICT_BATCH]:
            self._store.pop(ip, None)
            self._last_seen.pop(ip, None)

    def _full_cleanup(self, now: float):
        """清理所有超過 2 分鐘沒活動的 IP"""
        cutoff = now - 120
        stale_ips = [ip for ip, ts in self._last_seen.items() if ts < cutoff]
        for ip in stale_ips:
            self._store.pop(ip, None)
            self._last_seen.pop(ip, None)


_rate_limiter = _RateLimiter(settings.rate_limit_per_minute)
_auth_rate_limiter = _RateLimiter(10)  # login/register 防暴力


_RATE_LIMIT_SKIP_PREFIX = (
    "/api/health",
    "/api/status",
    "/api/tasks",
    "/static",
    "/ws",
)
if settings.demo_mode or settings.debug:
    _RATE_LIMIT_SKIP_PREFIX = _RATE_LIMIT_SKIP_PREFIX + (
        "/api/dashboard",
        "/api/data/",
    )


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """滑動窗口限流：每 IP 每分鐘最多 N 次請求"""
    path = request.url.path
    if not path.startswith("/api/"):
        return await call_next(request)
    if any(path.startswith(prefix) for prefix in _RATE_LIMIT_SKIP_PREFIX):
        return await call_next(request)

    client_ip = request.client.host if request.client else "unknown"
    limiter = _auth_rate_limiter if path.startswith("/api/auth/login") or path.startswith("/api/auth/register") else _rate_limiter
    allowed, retry_after = limiter.check(client_ip)

    if not allowed:
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=429,
            content={"detail": "請求過於頻繁，請稍後再試"},
            headers={"Retry-After": str(retry_after)},
        )

    return await call_next(request)


# ============================================================
# 認證中間件 — 向後兼容（無 token 時允許通過）
# ============================================================

# 不需要認證的路徑前綴（白名單）
AUTH_WHITELIST_PREFIX = (
    "/api/auth/login", "/api/auth/register", "/api/health", "/api/health/detailed", "/api/status",
    "/api/config", "/api/strategies/list", "/api/stocks", "/api/stocks/names", "/api/data-sources",
    "/api/markets", "/api/indices", "/api/dashboard", "/api/data/", "/api/tasks",
    "/api/sparkline", "/api/signals/", "/api/backtest/history", "/api/alerts",
    "/docs", "/openapi.json",
    "/redoc", "/static", "/", "/ws",
)
# 精確匹配，避免 /api/strategies/leaderboard/update 被誤放行
AUTH_WHITELIST_EXACT = (
    "/api/strategies/leaderboard",
    "/api/strategies/params",
)

# 演示模式：GET 可讀，POST/PUT/PATCH/DELETE 需登錄
_AUTH_WRITE_PROTECTED_PREFIX = (
    "/api/tasks",
    "/api/stocks",
    "/api/markets",
    "/api/data/",
    "/api/backtest",
    "/api/alerts",
    "/api/portfolio",
    "/api/strategies/",
    "/api/scheduler/",
)


def _auth_read_allowed(path: str) -> bool:
    return path in AUTH_WHITELIST_EXACT or any(
        path.startswith(prefix) for prefix in AUTH_WHITELIST_PREFIX
    )


def _auth_write_requires_login(path: str, method: str) -> bool:
    if method in ("GET", "HEAD", "OPTIONS"):
        return False
    if not path.startswith("/api/"):
        return False
    if path.startswith("/api/auth/login") or path.startswith("/api/auth/register"):
        return False
    if _auth_read_allowed(path):
        return any(path.startswith(prefix) for prefix in _AUTH_WRITE_PROTECTED_PREFIX)
    return True


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """
    認證中間件 — 檢查 Authorization header

    - 白名單路徑 GET：放行（演示可讀）
    - 白名單下寫操作：需登錄
    - 有有效 token：注入 request.state.user
    - 無 token：返回 401
    """
    path = request.url.path
    method = request.method.upper()

    needs_auth = (
        path.startswith("/api/")
        and (
            not _auth_read_allowed(path)
            or _auth_write_requires_login(path, method)
        )
    )

    if needs_auth:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            from src.core.auth import verify_token, get_user_by_id
            payload = verify_token(token)
            if payload:
                user = get_user_by_id(payload.get("user_id"))
                request.state.user = user
            else:
                # Token 無效
                from fastapi.responses import JSONResponse
                return JSONResponse(status_code=401, content={"detail": "Token 無效或已過期，請重新登錄"})
        else:
            # 無 token
            from fastapi.responses import JSONResponse
            return JSONResponse(status_code=401, content={"detail": "未登錄，請先獲取 Token（POST /api/auth/login）"})

    response = await call_next(request)
    return response


# ============================================================
# API 路由
# ============================================================

# ====== 認證 API ======

@app.post("/api/auth/register")
async def auth_register(body: dict):
    """用戶註冊"""
    from src.core.auth import create_user
    
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""
    
    if not username or not password:
        raise HTTPException(400, "用戶名和密碼不能為空")
    if len(username) < 3:
        raise HTTPException(400, "用戶名至少 3 個字符")
    if len(password) < 6:
        raise HTTPException(400, "密碼至少 6 個字符")
    
    try:
        user = create_user(username, password)
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


@app.post("/api/auth/login")
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


@app.get("/api/auth/me")
async def auth_me(user = Depends(require_auth)):
    """獲取當前登錄用戶信息"""
    return {"success": True, "user": user.to_dict()}


@app.put("/api/auth/settings")
async def auth_update_settings(body: dict, user = Depends(require_auth)):
    """更新當前用戶設置"""
    import sqlite3
    settings_json = json.dumps(body.get("settings", {}), ensure_ascii=False)
    with get_conn() as conn:
        conn.execute("UPDATE users SET settings = ? WHERE id = ?", (settings_json, user.id))
    user.settings = body.get("settings", {})
    return {"success": True, "message": "設置已更新", "settings": user.settings}


# ====== 用戶數據 API（需登錄） ======

@app.get("/api/user/watchlists")
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


@app.post("/api/user/watchlists")
async def user_create_watchlist(body: dict, user = Depends(require_auth)):
    """創建監控列表"""
    import sqlite3
    name = (body.get("name") or "").strip()
    codes = body.get("codes", [])
    if not name:
        raise HTTPException(400, "請提供監控列表名稱")
    
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    codes_json = json.dumps(codes, ensure_ascii=False)
    with get_conn() as conn:
        cursor = conn.execute(
            "INSERT INTO user_watchlists (user_id, name, codes, created_at) VALUES (?, ?, ?, ?)",
            (user.id, name, codes_json, now),
        )
    return {"success": True, "id": cursor.lastrowid, "message": f"監控列表 '{name}' 已創建"}


@app.put("/api/user/watchlists/{watchlist_id}")
async def user_update_watchlist(watchlist_id: int, body: dict, user = Depends(require_auth)):
    """更新監控列表"""
    import sqlite3
    name = body.get("name")
    codes = body.get("codes")
    
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


@app.delete("/api/user/watchlists/{watchlist_id}")
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


@app.get("/api/user/alerts")
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


@app.post("/api/user/alerts")
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


@app.put("/api/user/alerts/{alert_id}")
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


@app.delete("/api/user/alerts/{alert_id}")
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


@app.get("/api/user/backtest-history")
async def user_backtest_history(user = Depends(require_auth), limit: int = 50):
    """獲取當前用戶的回測歷史（通過 user_id 標記）"""
    # 注意：現有 backtest_results 表沒有 user_id 字段，
    # 這裡返回全局歷史（向後兼容），未來可擴展為按用戶隔離
    from src.core.db import get_backtest_history
    results = get_backtest_history(limit=limit)
    return {"success": True, "results": results, "total": len(results), "note": "全局歷史（用戶隔離待擴展）"}


# ====== 管理員 API ======

@app.get("/api/admin/users")
async def admin_list_users(user = Depends(require_admin)):
    """列出所有用戶（僅管理員）"""
    from src.core.auth import list_users
    users = list_users()
    return {"success": True, "users": users, "total": len(users)}


@app.put("/api/admin/users/{target_user_id}/role")
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


@app.delete("/api/admin/users/{target_user_id}")
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


@app.get("/api/data-sources")
async def get_data_sources():
    """獲取所有數據源狀態"""
    from src.core.data_sources import health_check
    return {"sources": health_check()}


@app.get("/api/status")
async def system_status():
    """系統狀態"""
    stats = get_db_stats()
    uptime_sec = int(time.time() - state.start_time)

    return {
        "version": settings.app_version,
        "uptime_seconds": uptime_sec,
        "watchlist": settings.watchlist,
        "poll_interval": settings.poll_interval_sec,
        **stats,
    }


# ====== 股票 ======

@app.get("/api/stocks")
async def list_stocks():
    """獲取股票列表"""
    from src.core.api_cache import cached_response
    from src.core.db import load_all_codes

    def _build():
        codes = load_all_codes()
        stocks = []
        for code in codes:
            name = STOCK_NAMES.get(code, "")
            if not name:
                rule = settings.alert_rules.get(code, {})
                name = rule.get("name", code)
            stocks.append({"code": code, "name": name, "data_points": 0})
        return {"stocks": stocks, "total": len(stocks)}

    return cached_response("api:stocks:list", ttl=30, builder=_build)


@app.get("/api/stocks/names")
async def get_stock_names():
    """獲取股票代碼→中文名映射"""
    return {"names": STOCK_NAMES}


def _normalize_compare_code(code: str) -> str:
    """A 股代碼補零（000001）"""
    code = str(code).strip()
    if code.isdigit() and len(code) < 6:
        return code.zfill(6)
    return code


@app.post("/api/stocks/compare")
async def compare_stocks(body: dict):
    """多股收益率對比（本地優先，缺失時首次自動入庫）"""
    codes = body.get("codes", [])
    days = body.get("days", 250)
    start = body.get("start")

    if not codes:
        raise HTTPException(400, "請提供股票代碼列表")

    from src.core.local_kline import ensure_daily_kline

    result = {}
    missing = []
    for raw in codes:
        code = _normalize_compare_code(raw)
        df, _src = ensure_daily_kline(code, start_date=start, min_bars=2)
        if df.empty:
            missing.append(raw)
            continue
        if len(df) > days:
            df = df.tail(days)

        closes = df["close"].tolist()
        dates = df["date"].tolist()
        if not closes or closes[0] == 0:
            continue

        base = closes[0]
        relative = [round((c / base - 1) * 100, 2) for c in closes]
        result[code] = {
            "dates": [str(d) for d in dates],
            "relative_return": relative,
            "close": [round(float(c), 2) for c in closes],
        }

    return {
        "success": True,
        "comparison": result,
        "missing": missing,
        "loaded": len(result),
        "total": len(codes),
    }


@app.get("/api/stocks/{code}/overview")
async def get_stock_overview(code: str, lookback: int = 250):
    """單股基本數據：技術指標、區間統計、基本面摘要"""
    from src.core.api_cache import cached_response
    from src.core.result_cache import get_data_version
    from src.core.stock_basics import build_stock_overview

    code = _normalize_compare_code(code)
    lb = min(max(lookback, 20), 500)
    cache_key = f"api:overview:{code}:{lb}:{get_data_version(code)}"

    def _build():
        return build_stock_overview(code, lookback=lb)

    try:
        overview = cached_response(cache_key, ttl=30, builder=_build)
        return {"success": True, "overview": overview}
    except Exception as e:
        logger.error(f"股票概覽失敗 {code}: {e}")
        raise HTTPException(500, str(e))


@app.get("/api/strategies/params")
async def get_all_strategy_params_api():
    """全部策略默認參數與優化網格"""
    from src.core.api_cache import cached_response
    from src.core.strategy_params_meta import get_all_strategy_params

    return cached_response(
        "api:strategies:params",
        ttl=120,
        builder=lambda: {"strategies": get_all_strategy_params()},
    )


@app.get("/api/stocks/{code}/kline")
async def get_kline(code: str, start: str = None, end: str = None, limit: int = 500):
    """獲取 K 線數據（本地優先，僅首次無數據時爬取入庫）"""
    from src.core.local_kline import ensure_daily_kline, normalize_kline_code

    code = normalize_kline_code(code)
    df, source = ensure_daily_kline(code, start_date=start, end_date=end, min_bars=1)

    if df.empty:
        raise HTTPException(404, f"股票 {code} 無數據（外網拉取亦失敗）")

    if len(df) > limit:
        df = df.tail(limit)

    records = df.to_dict(orient="records")
    return {"code": code, "data": records, "count": len(records), "source": source}


@app.post("/api/stocks/download")
async def download_stocks(codes: list[str] = None):
    """下載歷史數據（異步任務）"""
    from src.core.task_manager import create_task
    from src.core.download_tasks import run_stocks_download, MARKET_NAMES

    if codes is None:
        codes = settings.watchlist

    task_params = {"codes": codes, "market": "a_share"}
    task = create_task(
        "data_download",
        task_params,
        title=f"下載 {MARKET_NAMES['a_share']}（{len(codes)} 只）",
    )
    if task.get("is_duplicate"):
        return {"success": True, "task_id": task["task_id"], "is_duplicate": True,
                "message": "相同下載任務執行中", "async": True}

    task_id = task["task_id"]
    if task.get("status") == "completed" and task.get("result"):
        return {"success": True, "task_id": task_id, "async": False,
                "from_cache": task.get("from_cache"), "result": task.get("result")}

    return _dispatch_async_task(
        task_id,
        lambda: run_stocks_download(codes, task_id=task_id),
        cache_namespace=None,
    )


@app.post("/api/stocks/update")
async def incremental_update(codes: list[str] = None, force: bool = False):
    """增量更新歷史數據（異步任務）"""
    from src.core.task_manager import create_task
    from src.core.download_tasks import run_incremental

    task_params = {"codes": codes or settings.watchlist, "force": force}
    task = create_task(
        "data_incremental",
        task_params,
        title=f"增量更新 A 股（{len(task_params['codes'])} 只）",
    )
    if task.get("is_duplicate"):
        return {"success": True, "task_id": task["task_id"], "is_duplicate": True,
                "message": "相同增量任務執行中", "async": True}

    task_id = task["task_id"]
    return _dispatch_async_task(
        task_id,
        lambda: run_incremental(codes=codes, force=force, task_id=task_id),
    )


# ====== 多市場支持 ======

@app.get("/api/markets")
async def list_markets():
    """獲取所有市場及標的數量"""
    from src.core.db import load_all_markets, load_all_codes_by_market
    from src.core.crypto import get_crypto_symbols
    from src.core.forex import get_forex_pairs
    from src.core.global_market import get_market_catalog

    markets = load_all_markets()

    # 基礎市場
    available = {
        "a_share": {"name": "A股", "icon": "🇨🇳", "description": "滬深 A 股"},
        "crypto": {"name": "加密貨幣", "icon": "₿", "description": "Binance 交易對"},
        "forex": {"name": "外匯", "icon": "💱", "description": "主要貨幣對"},
    }

    # 全球市場
    catalog = get_market_catalog()
    for key, cat in catalog.items():
        available[key] = {"name": cat["name"], "icon": cat["icon"], "description": f"{len(cat['symbols'])} 個標的"}

    result = []
    for mkt_key, info in available.items():
        count = next((m["count"] for m in markets if m["market"] == mkt_key), 0)
        result.append({
            "market": mkt_key,
            "name": info.get("name", mkt_key),
            "icon": info.get("icon", ""),
            "description": info.get("description", ""),
            "data_count": count,
        })

    return {"markets": result}


@app.get("/api/markets/{market}/symbols")
async def list_market_symbols(market: str):
    """獲取指定市場的可用標的列表"""
    from src.core.db import load_all_codes_by_market
    from src.core.crypto import get_crypto_symbols
    from src.core.forex import get_forex_pairs
    from src.core.global_market import get_market_catalog

    catalog = get_market_catalog()

    if market == "crypto":
        symbols = get_crypto_symbols()
        existing = set(load_all_codes_by_market("crypto"))
        result = [{"code": k, "name": v, "has_data": k in existing} for k, v in symbols.items()]
        return {"market": market, "symbols": result, "total": len(result)}

    elif market == "forex":
        pairs = get_forex_pairs()
        existing = set(load_all_codes_by_market("forex"))
        result = [{"code": k, "name": v, "has_data": k in existing} for k, v in pairs.items()]
        return {"market": market, "symbols": result, "total": len(result)}

    elif market in catalog:
        cat = catalog[market]
        existing = set(load_all_codes_by_market(market))
        result = [{"code": k, "name": v, "has_data": k in existing} for k, v in cat["symbols"].items()]
        return {"market": market, "symbols": result, "total": len(result)}

    else:
        codes = load_all_codes_by_market("a_share")
        result = [{"code": c, "name": STOCK_NAMES.get(c, c), "has_data": True} for c in codes]
        return {"market": market, "symbols": result, "total": len(result)}


def _resolve_market_codes(market: str, codes: list[str] = None) -> list[str]:
    from src.core.global_market import MARKET_CATALOG

    if codes:
        return codes
    if market == "crypto":
        return list(settings.crypto_watchlist)
    if market == "forex":
        return list(settings.forex_watchlist)
    if market in MARKET_CATALOG:
        return list(MARKET_CATALOG[market]["symbols"].keys())
    return list(settings.watchlist)


@app.post("/api/markets/{market}/download")
async def download_market_data(market: str, body: list | dict | None = None):
    """下載指定市場的歷史數據（異步任務）"""
    from src.core.task_manager import create_task
    from src.core.download_tasks import run_market_download, MARKET_NAMES

    codes = None
    if isinstance(body, list):
        codes = body
    elif isinstance(body, dict):
        codes = body.get("codes")
    codes = _resolve_market_codes(market, codes)
    market_name = MARKET_NAMES.get(market, market)
    task_params = {"market": market, "codes": codes}
    task = create_task(
        "data_download",
        task_params,
        title=f"下載 {market_name}（{len(codes)} 個標的）",
    )
    if task.get("is_duplicate"):
        return {"success": True, "task_id": task["task_id"], "is_duplicate": True,
                "message": "相同下載任務執行中", "async": True}

    task_id = task["task_id"]
    return _dispatch_async_task(
        task_id,
        lambda: run_market_download(market, codes, task_id=task_id),
    )


@app.post("/api/download-all")
async def download_all_markets():
    """批量下載所有市場數據（異步任務）"""
    from src.core.task_manager import create_task
    from src.core.download_tasks import run_download_all

    task_params = {"scope": "all_markets"}
    task = create_task("data_download_all", task_params, title="下載全市場數據")
    if task.get("is_duplicate"):
        return {"success": True, "task_id": task["task_id"], "is_duplicate": True,
                "message": "全市場下載任務執行中", "async": True}

    task_id = task["task_id"]
    return _dispatch_async_task(
        task_id,
        lambda: run_download_all(task_id=task_id),
    )


@app.get("/api/markets/{market}/realtime")
async def get_market_realtime(market: str, symbols: str = None):
    """獲取指定市場的實時行情"""
    if market == "crypto":
        from src.core.crypto import get_crypto_multi_realtime
        sym_list = symbols.split(",") if symbols else settings.crypto_watchlist
        data = get_crypto_multi_realtime(sym_list)
        return {"market": "crypto", "data": data}

    elif market == "forex":
        from src.core.forex import get_forex_multi_realtime
        sym_list = symbols.split(",") if symbols else settings.forex_watchlist
        data = get_forex_multi_realtime(sym_list)
        return {"market": "forex", "data": data}

    elif market in ("us_stock", "hk_stock", "index", "etf", "commodity"):
        from src.core.global_market import get_global_realtime, MARKET_CATALOG
        if symbols:
            sym_list = symbols.split(",")
        else:
            cat = MARKET_CATALOG.get(market, {})
            sym_list = list(cat.get("symbols", {}).keys())[:20]
        data = get_global_realtime(sym_list)
        return {"market": market, "data": data}

    else:
        raise HTTPException(400, f"不支持的實時市場: {market}")


@app.get("/api/sparkline")
async def get_sparkline(codes: str, days: int = 30):
    """
    獲取多個標的的迷你走勢圖數據（最近 N 天收盤價）。
    多源降級：本地庫 → Yahoo → 東財 → Twelve Data。
    """
    from src.core.market_fetch import build_sparkline_item

    code_list = [c.strip() for c in codes.split(",") if c.strip()]
    result = {code: build_sparkline_item(code, days) for code in code_list}
    return {"sparklines": result}


# ====== 任務調度輔助 ======

def _dispatch_async_task(
    task_id: str,
    work_fn,
    *,
    cache_namespace: str = None,
    cache_params: dict = None,
    cache_code: str = None,
) -> dict:
    """將任務提交到線程池；支持結果緩存讀寫"""
    from src.core.task_manager import get_task, submit_task, STATUS_COMPLETED

    task = get_task(task_id)
    if task and task.get("status") == STATUS_COMPLETED:
        return {
            "success": True,
            "task_id": task_id,
            "async": False,
            "from_cache": bool(task.get("from_cache")),
            "result": task.get("result"),
        }

    def _work():
        result = work_fn()
        if cache_namespace and cache_params is not None:
            try:
                from src.core.result_cache import set_cached_compute
                set_cached_compute(
                    cache_namespace, cache_params, result, code=cache_code,
                )
            except Exception as e:
                logger.debug(f"緩存寫入跳過: {e}")
        return result

    submit_task(task_id, _work)
    return {"success": True, "task_id": task_id, "async": True}


# ====== 回測 ======

@app.post("/api/backtest")
async def run_backtest_api(
    code: str,
    strategy: str = "dual_ma",
    params: dict = None,
    cash: float = None,
    stop_loss_pct: float = None,
    take_profit_pct: float = None,
    trailing_stop_pct: float = None,
    benchmark: bool = False,
):
    """執行回測（自動去重：相同參數的回測不會重複執行）"""
    from src.core.backtest import run_backtest, STRATEGIES
    from src.core.task_manager import create_task

    if strategy not in STRATEGIES:
        raise HTTPException(400, f"未知策略: {strategy}，可選: {list(STRATEGIES.keys())}")

    task_params = {"code": code, "strategy": strategy, "params": params, "cash": cash}
    task = create_task("backtest", task_params, title=f"回測 {code}/{strategy}")
    if task.get("is_duplicate"):
        return {"success": True, "task_id": task["task_id"], "is_duplicate": True,
                "message": "相同回測正在執行中，請等待完成", "async": True}

    task_id = task["task_id"]

    def _work():
        return run_backtest(
            code, strategy_name=strategy, params=params, cash=cash,
            stop_loss_pct=stop_loss_pct, take_profit_pct=take_profit_pct,
            trailing_stop_pct=trailing_stop_pct, benchmark=benchmark,
            task_id=task_id,
        )

    return _dispatch_async_task(
        task_id, _work,
        cache_namespace="backtest", cache_params=task_params, cache_code=code,
    )


@app.post("/api/backtest/advanced")
async def run_advanced_backtest_api(body: dict):
    """
    進階回測 — 支持滑點、T+1、漲跌停控制（自動加入任務列表）

    請求體參數：
        code: 股票代碼
        strategy: 策略名稱（默認 dual_ma）
        params: 策略參數（可選）
        cash: 初始資金（可選）
        commission: 手續費率（可選）
        stop_loss_pct: 止損百分比（可選）
        take_profit_pct: 止盈百分比（可選）
        trailing_stop_pct: 移動止損百分比（可選）
        benchmark: 是否基準對比（默認 False）
        slippage_pct: 滑點百分比（默認 0.0，即 0%）
        enable_t1: 是否啟用 T+1 限制（默認 True）
        enable_limit: 是否啟用漲跌停限制（默認 True）
    """
    from src.core.backtest import run_backtest, STRATEGIES
    from src.core.task_manager import create_task

    code = body.get("code", "")
    strategy = body.get("strategy", "dual_ma")
    params = body.get("params")
    cash = body.get("cash")
    commission = body.get("commission")
    stop_loss_pct = body.get("stop_loss_pct")
    take_profit_pct = body.get("take_profit_pct")
    trailing_stop_pct = body.get("trailing_stop_pct")
    benchmark = body.get("benchmark", False)
    slippage_pct = body.get("slippage_pct", 0.0)
    enable_t1 = body.get("enable_t1", True)
    enable_limit = body.get("enable_limit", True)

    if not code:
        raise HTTPException(400, "請提供股票代碼")
    if strategy not in STRATEGIES:
        raise HTTPException(400, f"未知策略: {strategy}，可選: {list(STRATEGIES.keys())}")

    # 任務去重
    task_params = {
        "code": code, "strategy": strategy, "params": params, "cash": cash,
        "slippage_pct": slippage_pct, "enable_t1": enable_t1, "enable_limit": enable_limit,
    }
    task = create_task("backtest_advanced", task_params, title=f"進階回測 {code}/{strategy}")
    if task.get("is_duplicate"):
        return {"success": True, "task_id": task["task_id"], "is_duplicate": True,
                "message": "相同進階回測正在執行中，請等待完成", "async": True}

    task_id = task["task_id"]

    def _work():
        return run_backtest(
            code, strategy_name=strategy, params=params, cash=cash,
            commission=commission, stop_loss_pct=stop_loss_pct,
            take_profit_pct=take_profit_pct, trailing_stop_pct=trailing_stop_pct,
            benchmark=benchmark, slippage_pct=slippage_pct,
            enable_t1=enable_t1, enable_limit=enable_limit,
            task_id=task_id,
        )

    return _dispatch_async_task(
        task_id, _work,
        cache_namespace="backtest_advanced", cache_params=task_params, cache_code=code,
    )


@app.post("/api/backtest/multi")
async def run_multi_backtest_api(code: str):
    """所有策略對比（自動加入任務列表）"""
    from src.core.backtest import run_multi_strategy
    from src.core.task_manager import create_task

    if not code:
        raise HTTPException(400, "請提供股票代碼")

    task_params = {"code": code}
    task = create_task("backtest_multi", task_params, title=f"多策略對比 {code}")
    if task.get("is_duplicate"):
        return {"success": True, "task_id": task["task_id"], "is_duplicate": True,
                "message": "相同多策略對比正在執行中，請等待完成", "async": True}

    task_id = task["task_id"]
    return _dispatch_async_task(
        task_id,
        lambda: run_multi_strategy(code, task_id=task_id),
        cache_namespace="backtest_multi",
        cache_params=task_params,
        cache_code=code,
    )


# ====== 優化 ======

@app.post("/api/optimize")
async def run_optimize_api(
    code: str,
    strategy: str = "all",
    method: str = "grid",
    objective: str = "sharpe",
    n_trials: int = 100,
    top_n: int = 10,
):
    """參數優化（自動加入任務列表）"""
    from src.core.optimize import grid_search, optuna_search, optimize_all
    from src.core.task_manager import create_task

    if not code:
        raise HTTPException(400, "請提供股票代碼")

    task_params = {"code": code, "strategy": strategy, "method": method, "objective": objective, "n_trials": n_trials}
    display_strategy = strategy if strategy != "all" else "全部策略"
    task = create_task("optimize", task_params, title=f"參數優化 {code}/{display_strategy}")
    if task.get("is_duplicate"):
        return {"success": True, "task_id": task["task_id"], "is_duplicate": True,
                "message": "相同優化正在執行中，請等待完成", "async": True}

    task_id = task["task_id"]

    def _work():
        if strategy == "all":
            results = optimize_all(
                code, objective=objective, method=method,
                n_trials=n_trials, top_n=top_n, task_id=task_id,
            )
            serialized = {}
            for name, res_list in results.items():
                serialized[name] = [{k: v for k, v in r.items()} for r in res_list]
            return serialized
        if method == "optuna":
            return optuna_search(code, strategy, objective=objective, n_trials=n_trials, task_id=task_id)
        return grid_search(code, strategy, objective=objective, top_n=top_n, task_id=task_id)

    task_params["top_n"] = top_n
    return _dispatch_async_task(
        task_id, _work,
        cache_namespace="optimize", cache_params=task_params, cache_code=code,
    )


# ====== 組合 ======

@app.post("/api/portfolio")
async def run_portfolio_api(
    allocations: list[dict],
    weights: list[float] = None,
    rebalance: str = "none",
    rebalance_freq_days: int = 20,
    cash: float = None,
):
    """組合回測（自動加入任務列表）"""
    from src.core.portfolio import run_portfolio
    from src.core.task_manager import create_task

    if not allocations:
        raise HTTPException(400, "請提供組合配置")

    codes = [a.get("code", "") for a in allocations]
    task_params = {
        "allocations": allocations,
        "codes": codes,
        "weights": weights,
        "rebalance": rebalance,
        "rebalance_freq_days": rebalance_freq_days,
        "cash": cash,
        "count": len(allocations),
    }
    task = create_task("portfolio", task_params, title=f"組合回測 ({len(allocations)}隻)")
    if task.get("is_duplicate"):
        return {"success": True, "task_id": task["task_id"], "is_duplicate": True,
                "message": "相同組合回測正在執行中，請等待完成", "async": True}

    task_id = task["task_id"]

    def _work():
        return run_portfolio(
            allocations=allocations,
            weights=weights,
            rebalance=rebalance,
            rebalance_freq_days=rebalance_freq_days,
            cash=cash,
        )

    return _dispatch_async_task(
        task_id, _work,
        cache_namespace="portfolio", cache_params=task_params, cache_code=codes[0] if codes else None,
    )


# ====== 預警 ======

@app.get("/api/alerts")
async def list_alerts(limit: int = 50, code: str = None):
    """獲取預警歷史"""
    logs = get_alert_logs(limit=limit, code=code)
    return {"alerts": logs, "total": len(logs)}


@app.get("/api/alerts/rules")
async def get_alert_rules():
    """獲取預警規則"""
    return {"rules": settings.alert_rules}


@app.put("/api/alerts/rules")
async def update_alert_rules(rules: dict):
    """更新預警規則（運行時生效，重啟後恢復）"""
    settings.alert_rules.update(rules)
    return {"success": True, "rules": settings.alert_rules}


@app.delete("/api/alerts/rules/{code}")
async def delete_alert_rule(code: str):
    """刪除預警規則"""
    if code in settings.alert_rules:
        del settings.alert_rules[code]
        return {"success": True, "message": f"已刪除 {code}"}
    raise HTTPException(404, f"規則不存在: {code}")


@app.get("/api/alerts/rules/suggest")
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


@app.post("/api/alerts/rules/auto")
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


@app.post("/api/watchlist/add")
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


# ====== 回測歷史 ======

@app.get("/api/backtest/history")
async def backtest_history(code: str = None, strategy: str = None, limit: int = 50):
    """查詢回測歷史"""
    from src.core.db import get_backtest_history
    results = get_backtest_history(code=code, strategy=strategy, limit=limit)
    return {"results": results, "total": len(results)}


@app.get("/api/backtest/compare")
async def backtest_compare(ids: str = ""):
    """對比指定回測結果"""
    from src.core.db import get_backtest_by_ids
    if not ids:
        return {"results": []}
    id_list = [int(x.strip()) for x in ids.split(",") if x.strip().isdigit()]
    results = get_backtest_by_ids(id_list)
    return {"results": results, "total": len(results)}


# ====== Walk-Forward ======

@app.post("/api/walkforward")
async def run_walkforward(
    code: str,
    strategy: str = "dual_ma",
    train_days: int = 750,
    test_days: int = 250,
    step_days: int = 250,
    objective: str = "sharpe",
    n_trials: int = 50,
):
    """Walk-Forward 分析（自動加入任務列表）"""
    from src.core.walkforward import walk_forward
    from src.core.task_manager import create_task

    if not code:
        raise HTTPException(400, "請提供股票代碼")

    task_params = {"code": code, "strategy": strategy, "train_days": train_days, "test_days": test_days}
    task = create_task("walkforward", task_params, title=f"Walk-Forward {code}/{strategy}")
    if task.get("is_duplicate"):
        return {"success": True, "task_id": task["task_id"], "is_duplicate": True,
                "message": "相同 Walk-Forward 正在執行中，請等待完成", "async": True}

    task_id = task["task_id"]

    def _work():
        return walk_forward(
            code=code, strategy_name=strategy,
            train_days=train_days, test_days=test_days, step_days=step_days,
            objective=objective, n_trials=n_trials,
        )

    return _dispatch_async_task(
        task_id, _work,
        cache_namespace="walkforward", cache_params=task_params, cache_code=code,
    )


# ====== 自動優化 ======

@app.post("/api/auto-optimize")
async def run_auto_optimize(body: dict = None):
    """自動參數優化（自動加入任務列表）"""
    from src.core.auto_optimize import auto_optimize_watchlist
    from src.core.task_manager import create_task

    if body is None:
        body = {}

    task_params = {"codes": body.get("codes"), "strategies": body.get("strategies"), "method": body.get("method", "optuna")}
    task = create_task("auto_optimize", task_params, title="全自動參數優化")
    if task.get("is_duplicate"):
        return {"success": True, "task_id": task["task_id"], "is_duplicate": True,
                "message": "全自動優化正在執行中，請等待完成", "async": True}

    task_id = task["task_id"]

    def _work():
        return auto_optimize_watchlist(
            codes=body.get("codes"),
            strategies=body.get("strategies"),
            method=body.get("method", "optuna"),
            n_trials=body.get("n_trials", 50),
            objective=body.get("objective", "sharpe"),
        )

    return _dispatch_async_task(
        task_id, _work,
        cache_namespace="auto_optimize", cache_params=task_params,
    )


# ====== 緩存管理 ======

@app.get("/api/cache/stats")
async def cache_stats_api():
    """緩存統計（LRU / Redis）"""
    from src.core.result_cache import cache_stats
    return {"success": True, **cache_stats()}


@app.post("/api/cache/clear")
async def cache_clear_api(code: str = None):
    """清除計算結果緩存；可選按股票代碼"""
    from src.core.result_cache import invalidate_compute
    from src.core.db import clear_data_cache
    if code:
        removed = invalidate_compute(code=code)
    else:
        clear_data_cache()
        removed = invalidate_compute()
    return {"success": True, "removed": removed, "code": code}


# ====== 調度器 ======

@app.get("/api/scheduler/jobs")
async def list_scheduler_jobs():
    """列出已註冊的調度任務"""
    from src.core.scheduler import list_jobs
    return {"jobs": list_jobs()}


@app.get("/api/scheduler/catalog")
async def scheduler_catalog():
    """定時任務目錄（含是否已啟用）"""
    from src.core.scheduler import get_catalog, list_jobs
    return {"catalog": get_catalog(), "jobs": list_jobs()}


@app.post("/api/scheduler/setup")
async def scheduler_setup():
    """按 config 重新註冊默認定時任務"""
    from src.core.scheduler import setup_from_settings
    jobs = setup_from_settings()
    return {
        "success": True,
        "message": f"已註冊 {len(jobs)} 個定時任務",
        "jobs": jobs,
    }


@app.post("/api/scheduler/enable")
async def enable_scheduler():
    """啟用默認定時任務套件（同 /api/scheduler/setup）"""
    from src.core.scheduler import setup_from_settings
    jobs = setup_from_settings()
    return {
        "success": True,
        "message": f"已啟用 {len(jobs)} 個定時任務",
        "jobs": jobs,
    }


@app.post("/api/scheduler/disable")
async def disable_scheduler():
    """禁用全部定時任務"""
    from src.core.scheduler import _DISABLE_BY_ID
    for fn in _DISABLE_BY_ID.values():
        fn()
    return {"success": True, "message": "已禁用全部定時任務"}


@app.post("/api/scheduler/jobs/{job_id}/enable")
async def enable_scheduler_job(job_id: str):
    """啟用單個定時任務"""
    from src.core.scheduler import enable_job
    try:
        enable_job(job_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"success": True, "message": f"任務 {job_id} 已啟用"}


@app.post("/api/scheduler/jobs/{job_id}/disable")
async def disable_scheduler_job(job_id: str):
    """禁用單個定時任務"""
    from src.core.scheduler import disable_job
    try:
        disable_job(job_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"success": True, "message": f"任務 {job_id} 已禁用"}


@app.post("/api/scheduler/jobs/{job_id}/run")
async def run_scheduler_job_now(job_id: str):
    """立即執行一次定時任務"""
    from src.core.scheduler import run_job_now
    try:
        run_job_now(job_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        raise HTTPException(500, str(e))
    return {"success": True, "message": f"任務 {job_id} 已觸發執行"}


# ====== 通知渠道 ======

@app.get("/api/notify/channels")
async def list_notify_channels():
    """列出通知渠道狀態"""
    from src.core.alerts import get_notification_channels
    return {"channels": get_notification_channels()}


@app.post("/api/notify/test")
async def test_notify():
    """測試所有通知渠道"""
    from src.core.alerts import test_all_channels
    results = test_all_channels()
    return {"success": True, "results": results}


# ====== 配置 ======

@app.get("/api/config")
async def get_config():
    """獲取當前配置"""
    from src.core.api_cache import cached_response
    from src.core.optimize import PARAM_GRIDS, PARAM_RANGES

    def _build():
        return {
            "watchlist": settings.watchlist,
            "crypto_watchlist": settings.crypto_watchlist,
            "forex_watchlist": settings.forex_watchlist,
            "poll_interval": settings.poll_interval_sec,
            "alert_cooldown": settings.alert_cooldown_sec,
            "history_start_date": settings.history_start_date,
            "backtest_cash": settings.backtest_cash,
            "backtest_commission": settings.backtest_commission,
            "backtest_stamp_tax": settings.backtest_stamp_tax,
            "task_max_workers": settings.task_max_workers,
            "task_parallel_grid": settings.task_parallel_grid,
            "strategy_params": settings.strategy_params,
            "param_grids": PARAM_GRIDS,
            "param_ranges": {k: {pk: list(pv) for pk, pv in v.items()} for k, v in PARAM_RANGES.items()},
            "alert_rules": settings.alert_rules,
            "portfolio_presets": settings.portfolio_presets,
        }

    return cached_response("api:config", ttl=60, builder=_build)


@app.get("/api/portfolio/presets")
async def get_portfolio_presets():
    """獲取預設組合模板"""
    return {"presets": settings.portfolio_presets}


@app.post("/api/portfolio/preset/{preset_name}")
async def run_preset_portfolio(preset_name: str, cash: float = None):
    """用預設模板跑組合回測"""
    from src.core.portfolio import run_portfolio

    preset = settings.portfolio_presets.get(preset_name)
    if not preset:
        raise HTTPException(404, f"預設組合不存在: {preset_name}，可選: {list(settings.portfolio_presets.keys())}")

    try:
        result = run_portfolio(
            allocations=preset["allocations"],
            rebalance=preset.get("rebalance", "none"),
            rebalance_freq_days=preset.get("rebalance_freq_days", 20),
            cash=cash,
        )
        return {"success": True, "preset": preset["name"], "result": result}
    except Exception as e:
        logger.error(f"預設組合回測失敗: {e}")
        raise HTTPException(500, str(e))


# ====== 進階組合功能 ======

@app.post("/api/portfolio/dynamic")
async def run_dynamic_portfolio(body: dict):
    """動態權重組合回測 — 根據滾動夏普自動調整子策略權重"""
    from src.core.portfolio import dynamic_weight_portfolio

    allocations = body.get("allocations", [])
    rolling_window = body.get("rolling_window", 60)
    rebalance_freq_days = body.get("rebalance_freq_days", 20)
    cash = body.get("cash")

    if not allocations:
        raise HTTPException(400, "請提供 allocations")

    try:
        result = dynamic_weight_portfolio(
            allocations=allocations,
            rolling_window=rolling_window,
            rebalance_freq_days=rebalance_freq_days,
            cash=cash,
        )
        return {"success": True, "result": result}
    except Exception as e:
        logger.error(f"動態權重組合失敗: {e}")
        raise HTTPException(500, str(e))


@app.post("/api/portfolio/kelly")
async def run_kelly_criterion(body: dict):
    """Kelly 公式計算最優倉位比例"""
    from src.core.portfolio import kelly_criterion

    allocations = body.get("allocations", [])
    cash = body.get("cash")
    fraction_limit = body.get("fraction_limit", 0.5)

    if not allocations:
        raise HTTPException(400, "請提供 allocations")

    try:
        result = kelly_criterion(
            allocations=allocations,
            cash=cash,
            fraction_limit=fraction_limit,
        )
        return {"success": True, "result": result}
    except Exception as e:
        logger.error(f"Kelly 公式計算失敗: {e}")
        raise HTTPException(500, str(e))


@app.post("/api/portfolio/degradation")
async def run_degradation_detection(body: dict):
    """策略衰退檢測 — 檢測子策略是否連續跑輸基準"""
    from src.core.portfolio import detect_degradation

    allocations = body.get("allocations", [])
    lookback_days = body.get("lookback_days", 30)
    threshold_days = body.get("threshold_days", 5)
    weight_reduction = body.get("weight_reduction", 0.5)
    cash = body.get("cash")

    if not allocations:
        raise HTTPException(400, "請提供 allocations")

    try:
        result = detect_degradation(
            allocations=allocations,
            lookback_days=lookback_days,
            threshold_days=threshold_days,
            weight_reduction=weight_reduction,
            cash=cash,
        )
        return {"success": True, "result": result}
    except Exception as e:
        logger.error(f"衰退檢測失敗: {e}")
        raise HTTPException(500, str(e))


@app.post("/api/portfolio/arbitrate")
async def run_signal_arbitration(body: dict):
    """信號衝突仲裁 — 多策略矛盾信號加權投票"""
    from src.core.portfolio import arbitrate_signals

    strategy_signals = body.get("strategy_signals", [])
    allocations = body.get("allocations")
    rolling_window = body.get("rolling_window", 60)
    cash = body.get("cash")

    if not strategy_signals:
        raise HTTPException(400, "請提供 strategy_signals")

    try:
        result = arbitrate_signals(
            strategy_signals=strategy_signals,
            allocations=allocations,
            rolling_window=rolling_window,
            cash=cash,
        )
        return {"success": True, "result": result}
    except Exception as e:
        logger.error(f"信號仲裁失敗: {e}")
        raise HTTPException(500, str(e))


@app.post("/api/portfolio/risk-parity")
async def run_risk_parity(body: dict):
    """風險平價組合 — 每個策略對總風險貢獻相等"""
    from src.core.portfolio import risk_parity_portfolio

    allocations = body.get("allocations", [])
    cash = body.get("cash")

    if not allocations:
        raise HTTPException(400, "請提供 allocations")

    try:
        result = risk_parity_portfolio(allocations=allocations, cash=cash)
        return {"success": True, "result": result}
    except Exception as e:
        logger.error(f"風險平價組合失敗: {e}")
        raise HTTPException(500, str(e))


@app.post("/api/portfolio/mvo")
async def run_mean_variance(body: dict):
    """均值-方差優化 — Markowitz 最優權重"""
    from src.core.portfolio import mean_variance_optimize

    allocations = body.get("allocations", [])
    objective = body.get("objective", "max_sharpe")
    cash = body.get("cash")
    n_simulations = body.get("n_simulations", 5000)

    if not allocations:
        raise HTTPException(400, "請提供 allocations")

    try:
        result = mean_variance_optimize(
            allocations=allocations, objective=objective,
            cash=cash, n_simulations=n_simulations,
        )
        return {"success": True, "result": result}
    except Exception as e:
        logger.error(f"均值-方差優化失敗: {e}")
        raise HTTPException(500, str(e))


@app.post("/api/portfolio/vol-target")
async def run_vol_targeting(body: dict):
    """波動率目標組合 — 根據已實現波動率動態調整倉位"""
    from src.core.portfolio import volatility_targeting

    allocations = body.get("allocations", [])
    target_vol = body.get("target_vol", 0.15)
    lookback_days = body.get("lookback_days", 20)
    cash = body.get("cash")

    if not allocations:
        raise HTTPException(400, "請提供 allocations")

    try:
        result = volatility_targeting(
            allocations=allocations, target_vol=target_vol,
            lookback_days=lookback_days, cash=cash,
        )
        return {"success": True, "result": result}
    except Exception as e:
        logger.error(f"波動率目標組合失敗: {e}")
        raise HTTPException(500, str(e))


@app.post("/api/portfolio/max-diversification")
async def run_max_diversification(body: dict):
    """最大分散化組合 — 最大化分散化比率"""
    from src.core.portfolio import max_diversification_portfolio

    allocations = body.get("allocations", [])
    cash = body.get("cash")
    n_simulations = body.get("n_simulations", 5000)

    if not allocations:
        raise HTTPException(400, "請提供 allocations")

    try:
        result = max_diversification_portfolio(
            allocations=allocations, cash=cash, n_simulations=n_simulations,
        )
        return {"success": True, "result": result}
    except Exception as e:
        logger.error(f"最大分散化組合失敗: {e}")
        raise HTTPException(500, str(e))


@app.post("/api/portfolio/anti-correlation")
async def run_anti_correlation(body: dict):
    """反相關組合 — 最小化策略間總相關性"""
    from src.core.portfolio import anti_correlation_portfolio

    allocations = body.get("allocations", [])
    cash = body.get("cash")
    n_simulations = body.get("n_simulations", 5000)

    if not allocations:
        raise HTTPException(400, "請提供 allocations")

    try:
        result = anti_correlation_portfolio(
            allocations=allocations, cash=cash, n_simulations=n_simulations,
        )
        return {"success": True, "result": result}
    except Exception as e:
        logger.error(f"反相關組合失敗: {e}")
        raise HTTPException(500, str(e))


@app.post("/api/portfolio/regime-switch")
async def run_regime_switch(body: dict):
    """市場狀態切換組合 — 根據趨勢/波動狀態動態調整策略權重"""
    from src.core.portfolio import regime_switch_portfolio

    allocations = body.get("allocations", [])
    regime_method = body.get("regime_method", "volatility")
    lookback_days = body.get("lookback_days", 60)
    cash = body.get("cash")

    if not allocations:
        raise HTTPException(400, "請提供 allocations")

    try:
        result = regime_switch_portfolio(
            allocations=allocations, regime_method=regime_method,
            lookback_days=lookback_days, cash=cash,
        )
        return {"success": True, "result": result}
    except Exception as e:
        logger.error(f"狀態切換組合失敗: {e}")
        raise HTTPException(500, str(e))


@app.post("/api/portfolio/black-litterman")
async def run_black_litterman(body: dict):
    """Black-Litterman 模型 — 結合市場均衡收益與投資者觀點"""
    from src.core.portfolio import black_litterman_portfolio

    allocations = body.get("allocations", [])
    views = body.get("views", {})
    confidence = body.get("confidence", {})
    cash = body.get("cash")

    if not allocations:
        raise HTTPException(400, "請提供 allocations")
    if not views:
        raise HTTPException(400, "請提供 views（投資者觀點）")

    try:
        result = black_litterman_portfolio(
            allocations=allocations, views=views,
            confidence=confidence, cash=cash,
        )
        return {"success": True, "result": result}
    except Exception as e:
        logger.error(f"Black-Litterman 組合失敗: {e}")
        raise HTTPException(500, str(e))


@app.post("/api/portfolio/hrp")
async def run_hrp(body: dict):
    """層次風險平價 (HRP) — 基於聚類的穩健資產配置"""
    from src.core.portfolio import hierarchical_risk_parity

    allocations = body.get("allocations", [])
    cash = body.get("cash")

    if not allocations:
        raise HTTPException(400, "請提供 allocations")

    try:
        result = hierarchical_risk_parity(allocations=allocations, cash=cash)
        return {"success": True, "result": result}
    except Exception as e:
        logger.error(f"HRP 組合失敗: {e}")
        raise HTTPException(500, str(e))


@app.post("/api/portfolio/cvar-optimize")
async def run_cvar_optimize(body: dict):
    """CVaR 優化 — 最小化條件風險價值"""
    from src.core.portfolio import cvar_optimize

    allocations = body.get("allocations", [])
    alpha = body.get("alpha", 0.05)
    cash = body.get("cash")

    if not allocations:
        raise HTTPException(400, "請提供 allocations")

    try:
        result = cvar_optimize(allocations=allocations, alpha=alpha, cash=cash)
        return {"success": True, "result": result}
    except Exception as e:
        logger.error(f"CVaR 優化失敗: {e}")
        raise HTTPException(500, str(e))


@app.post("/api/portfolio/multi-timeframe")
async def run_multi_timeframe(body: dict):
    """多時間框架信號確認 — 多窗口投票確認交易信號"""
    from src.core.portfolio import multi_timeframe_signal

    allocations = body.get("allocations", [])
    windows = body.get("windows", [5, 20, 60])
    cash = body.get("cash")

    if not allocations:
        raise HTTPException(400, "請提供 allocations")

    try:
        result = multi_timeframe_signal(allocations=allocations, windows=windows, cash=cash)
        return {"success": True, "result": result}
    except Exception as e:
        logger.error(f"多時間框架信號失敗: {e}")
        raise HTTPException(500, str(e))


@app.post("/api/portfolio/dynamic-rebalance")
async def run_dynamic_rebalance(body: dict):
    """動態再平衡觸發 — 波動率和權重偏移驅動的再平衡"""
    from src.core.portfolio import dynamic_rebalance_trigger

    allocations = body.get("allocations", [])
    threshold_pct = body.get("threshold_pct", 5.0)
    vol_window = body.get("vol_window", 20)
    cash = body.get("cash")

    if not allocations:
        raise HTTPException(400, "請提供 allocations")

    try:
        result = dynamic_rebalance_trigger(
            allocations=allocations, threshold_pct=threshold_pct,
            vol_window=vol_window, cash=cash,
        )
        return {"success": True, "result": result}
    except Exception as e:
        logger.error(f"動態再平衡失敗: {e}")
        raise HTTPException(500, str(e))


@app.post("/api/portfolio/sector-limit")
async def run_sector_limit(body: dict):
    """板塊敞口限制 — 控制單板塊最大配置比例"""
    from src.core.portfolio import sector_exposure_limit

    allocations = body.get("allocations", [])
    max_sector_pct = body.get("max_sector_pct", 40.0)
    cash = body.get("cash")

    if not allocations:
        raise HTTPException(400, "請提供 allocations")

    try:
        result = sector_exposure_limit(
            allocations=allocations, max_sector_pct=max_sector_pct, cash=cash,
        )
        return {"success": True, "result": result}
    except Exception as e:
        logger.error(f"板塊敞口限制失敗: {e}")
        raise HTTPException(500, str(e))


@app.post("/api/portfolio/voting")
async def run_voting_portfolio(body: dict):
    """投票式組合 — 多策略投票，>= min_votes 個同意才執行"""
    from src.core.portfolio import strategy_voting_portfolio

    allocations = body.get("allocations", [])
    min_votes = body.get("min_votes", 2)
    cash = body.get("cash")

    if not allocations:
        raise HTTPException(400, "請提供 allocations")

    try:
        result = strategy_voting_portfolio(
            allocations=allocations,
            min_votes=min_votes,
            cash=cash,
        )
        return {"success": True, "result": result}
    except Exception as e:
        logger.error(f"投票式組合失敗: {e}")
        raise HTTPException(500, str(e))


@app.post("/api/portfolio/momentum-of-momentum")
async def run_momentum_of_momentum(body: dict):
    """動量的動量組合 — 二階動量加權，策略改善趨勢越好權重越高"""
    from src.core.portfolio import momentum_of_momentum

    allocations = body.get("allocations", [])
    lookback = body.get("lookback", 60)
    cash = body.get("cash")

    if not allocations:
        raise HTTPException(400, "請提供 allocations")

    try:
        result = momentum_of_momentum(
            allocations=allocations,
            lookback=lookback,
            cash=cash,
        )
        return {"success": True, "result": result}
    except Exception as e:
        logger.error(f"動量的動量組合失敗: {e}")
        raise HTTPException(500, str(e))


@app.post("/api/portfolio/adaptive-regime")
async def run_adaptive_regime(body: dict):
    """自適應市場狀態組合 — 低波動加趨勢策略，高波動加均值回歸策略"""
    from src.core.portfolio import adaptive_regime_portfolio

    allocations = body.get("allocations", [])
    cash = body.get("cash")

    if not allocations:
        raise HTTPException(400, "請提供 allocations")

    try:
        result = adaptive_regime_portfolio(
            allocations=allocations,
            cash=cash,
        )
        return {"success": True, "result": result}
    except Exception as e:
        logger.error(f"自適應狀態組合失敗: {e}")
        raise HTTPException(500, str(e))


# ====== 熱力圖 ======

@app.post("/api/heatmap")
async def run_heatmap(
    code: str,
    strategy: str,
    param_x: str,
    param_y: str,
    grid_size: int = 10,
    objective: str = "sharpe",
):
    """參數敏感度熱力圖"""
    from src.core.heatmap import param_heatmap
    from src.core.result_cache import get_cached_compute, set_cached_compute

    param_x = (param_x or "").strip()
    param_y = (param_y or "").strip()
    if not param_x or not param_y:
        raise HTTPException(400, "請選擇參數 X 和參數 Y（不可為空）")

    cache_params = {
        "code": code, "strategy": strategy,
        "param_x": param_x, "param_y": param_y,
        "grid_size": grid_size, "objective": objective,
    }
    cached = get_cached_compute("heatmap", cache_params, code=code)
    if cached is not None:
        return {"success": True, "result": cached, "from_cache": True}

    try:
        result = param_heatmap(
            code=code, strategy_name=strategy,
            param_x=param_x, param_y=param_y,
            grid_size=grid_size, objective=objective,
        )
        set_cached_compute("heatmap", cache_params, result, code=code)
        return {"success": True, "result": result, "from_cache": False}
    except Exception as e:
        logger.error(f"熱力圖失敗: {e}")
        raise HTTPException(500, str(e))


@app.get("/api/heatmap/params/{strategy}")
async def get_strategy_params(strategy: str):
    """獲取策略的可調參數"""
    from src.core.backtest import STRATEGIES
    from src.core.optimize import PARAM_GRIDS

    if strategy not in STRATEGIES:
        raise HTTPException(400, f"未知策略: {strategy}")

    from src.core.heatmap import _get_default_params
    from src.core.strategy_params_meta import PARAM_LABELS

    defaults = _get_default_params(strategy)
    grid = PARAM_GRIDS.get(strategy, {})

    return {
        "strategy": strategy,
        "params": list(defaults.keys()),
        "defaults": defaults,
        "grid_values": grid,
        "labels": {k: PARAM_LABELS.get(k, k) for k in defaults.keys()},
    }


# ====== 股票篩選 ======

@app.get("/api/screener/stocks")
async def get_stock_list_api(market: str = "all"):
    """獲取可用股票列表"""
    from src.core.screener import get_stock_list

    try:
        stocks = get_stock_list(market=market)
        return {"stocks": stocks, "total": len(stocks)}
    except Exception as e:
        logger.error(f"獲取股票列表失敗: {e}")
        raise HTTPException(500, str(e))


@app.post("/api/screener/screen")
async def screen_stocks_api(body: dict):
    """股票篩選"""
    from src.core.screener import screen_stocks

    filters = body.get("filters", {})
    codes = body.get("codes")

    try:
        results = screen_stocks(codes=codes, filters=filters)
        return {"success": True, "results": results, "total": len(results)}
    except Exception as e:
        logger.error(f"篩選失敗: {e}")
        raise HTTPException(500, str(e))


# ====== 基準對比 ======

@app.get("/api/benchmark")
async def get_benchmark(start: str = None, end: str = None):
    """獲取滬深300基準數據"""
    from src.core.benchmark import get_benchmark_returns

    try:
        result = get_benchmark_returns(start_date=start, end_date=end)
        return {"success": True, "result": result}
    except Exception as e:
        logger.error(f"基準數據獲取失敗: {e}")
        raise HTTPException(500, str(e))


@app.post("/api/benchmark/compare")
async def compare_benchmark_api(body: dict):
    """回測結果與基準對比"""
    from src.core.benchmark import compare_with_benchmark
    from src.core.backtest import run_backtest

    code = body.get("code")
    strategy = body.get("strategy", "dual_ma")
    params = body.get("params")

    try:
        bt_result = run_backtest(code, strategy_name=strategy, params=params)
        comparison = compare_with_benchmark(bt_result)
        return {"success": True, "comparison": comparison}
    except Exception as e:
        logger.error(f"基準對比失敗: {e}")
        raise HTTPException(500, str(e))


# ====== 實時信號 ======

def _fetch_current_signals():
    from src.core.signals import SignalEngine, compute_and_push_signals

    engine = SignalEngine()
    engine.update_weights_from_backtest()
    signals_data = compute_and_push_signals(engine, settings.watchlist)
    return signals_data


@app.get("/api/signals/current")
async def get_current_signals():
    """獲取所有監控股票的當前信號"""
    try:
        signals_data = _fetch_current_signals()
        return {"success": True, "signals": signals_data, "total": len(signals_data)}
    except Exception as e:
        logger.error(f"獲取當前信號失敗: {e}")
        raise HTTPException(500, str(e))


@app.get("/api/signals/trading")
async def get_trading_signals():
    """儀表盤交易信號（與 current 同源，兼容舊前端路由）"""
    try:
        signals_data = _fetch_current_signals()
        return {"success": True, "signals": signals_data, "data": signals_data, "total": len(signals_data)}
    except Exception as e:
        logger.error(f"獲取交易信號失敗: {e}")
        raise HTTPException(500, str(e))


@app.get("/api/signals/history")
async def get_signal_history(code: str = None, strategy: str = None, days: int = 30):
    """獲取歷史信號記錄"""
    from src.core.signals import get_historical_signals
    from src.core.db import get_signal_logs

    try:
        if code:
            # 先嘗試從數據庫讀取
            logs = get_signal_logs(code=code, strategy=strategy, days=days)
            if not logs:
                # 數據庫中沒有，回放計算
                logs = get_historical_signals(code=code, days=days, strategy=strategy)
            return {"success": True, "signals": logs, "total": len(logs)}
        else:
            # 無 code 時直接查數據庫
            logs = get_signal_logs(strategy=strategy, days=days)
            return {"success": True, "signals": logs, "total": len(logs)}
    except Exception as e:
        logger.error(f"獲取歷史信號失敗: {e}")
        raise HTTPException(500, str(e))


@app.get("/api/signals/strength")
async def get_signal_strength(code: str = None):
    """獲取信號強度綜合分數"""
    from src.core.signals import SignalEngine, score_signal_strength, compute_and_push_signals
    from src.core.db import get_signal_logs

    if not code:
        raise HTTPException(400, "請提供股票代碼")

    try:
        # 先嘗試從數據庫取最新信號
        logs = get_signal_logs(code=code, days=1)
        if logs:
            # 取最新時間戳的信號
            latest_time = logs[0]["triggered_at"]
            latest_signals = [l for l in logs if l["triggered_at"] == latest_time]
            strength = score_signal_strength(latest_signals)
            return {
                "success": True,
                "code": code,
                "strength": strength,
                "signals_count": len(latest_signals),
                "updated_at": latest_time,
            }

        # 數據庫中沒有，實時計算
        engine = SignalEngine()
        engine.update_weights_from_backtest()
        raw_signals = engine.compute_signals([code])

        if raw_signals:
            strength = score_signal_strength(raw_signals)
            return {
                "success": True,
                "code": code,
                "strength": strength,
                "signals_count": len(raw_signals),
                "updated_at": raw_signals[0]["triggered_at"],
            }

        return {"success": True, "code": code, "strength": 0, "signals_count": 0, "updated_at": None}
    except Exception as e:
        logger.error(f"獲取信號強度失敗: {e}")
        raise HTTPException(500, str(e))


# ====== 數據導出 ======

@app.get("/api/export/backtest/{result_id}")
async def export_backtest(result_id: int, format: str = "csv"):
    """導出回測結果"""
    from src.core.export import export_backtest_csv, export_backtest_json

    if format == "json":
        content = export_backtest_json(result_id)
        from fastapi.responses import Response
        return Response(content=content, media_type="application/json")
    else:
        content = export_backtest_csv(result_id)
        from fastapi.responses import Response
        return Response(
            content=content,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=backtest_{result_id}.csv"}
        )


@app.get("/api/export/trades")
async def export_trades(code: str, strategy: str, format: str = "csv"):
    """導出交易明細"""
    from src.core.export import export_trades_csv, export_trades_json

    if format == "json":
        content = export_trades_json(code, strategy)
        from fastapi.responses import Response
        return Response(content=content, media_type="application/json")
    else:
        content = export_trades_csv(code, strategy)
        from fastapi.responses import Response
        return Response(
            content=content,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=trades_{code}_{strategy}.csv"}
        )


# ====== 有效前沿 ======

@app.post("/api/portfolio/frontier")
async def run_portfolio_frontier(body: dict):
    """有效前沿分析"""
    from src.core.portfolio import efficient_frontier

    allocations = body.get("allocations", [])
    n_points = body.get("n_points", 20)

    if len(allocations) < 2:
        raise HTTPException(400, "至少需要 2 個子策略")

    try:
        result = efficient_frontier(allocations=allocations, n_points=n_points)
        return {"success": True, "result": result}
    except Exception as e:
        logger.error(f"有效前沿失敗: {e}")
        raise HTTPException(500, str(e))


# ====== 策略開發框架 ======

@app.post("/api/strategies/create")
async def create_strategy(body: dict):
    """從模板創建用戶策略"""
    from src.core.strategy_base import create_strategy_template

    name = body.get("name", "").strip()
    if not name:
        raise HTTPException(400, "請提供策略名稱")

    filepath = body.get("filepath")
    try:
        result_path = create_strategy_template(name, filepath)
        return {"success": True, "filepath": result_path, "name": name}
    except Exception as e:
        logger.error(f"創建策略模板失敗: {e}")
        raise HTTPException(500, str(e))


@app.get("/api/strategies/list")
async def list_strategies_api():
    """列出所有策略（內置 + 用戶）"""
    from src.core.api_cache import cached_response
    from src.core.backtest import STRATEGIES, STRATEGY_NAMES
    from src.core.strategy_base import list_user_strategies

    def _build():
        # 內置策略
        builtin = []
        for name, cls in STRATEGIES.items():
            display = STRATEGY_NAMES.get(name, name)
            desc = (cls.__doc__ or "").strip().split("\n")[0]
            builtin.append({
                "name": name,
                "display_name": display,
                "source": "builtin",
                "description": f"{display} — {desc}" if desc else display,
                "params": {},
            })

        user_strategies = list_user_strategies()
        user = []
        for s in user_strategies:
            user.append({
                "name": s["name"],
                "source": "user",
                "description": s["description"],
                "params": s["params"],
                "filepath": s.get("filepath", ""),
            })

        return {
            "builtin": builtin,
            "user": user,
            "total": len(builtin) + len(user),
        }

    return cached_response("api:strategies:list", ttl=120, builder=_build)


@app.post("/api/strategies/upload")
async def upload_strategy(file: UploadFile = File(...)):
    """上傳用戶策略 .py 文件"""
    from src.core.strategy_base import load_user_strategy
    import tempfile
    import shutil

    if not file.filename.endswith(".py"):
        raise HTTPException(400, "策略文件必須是 .py 格式")

    # 保存到 strategies 目錄
    strategies_dir = Path(__file__).parent.parent.parent / "strategies"
    strategies_dir.mkdir(exist_ok=True)
    dest = strategies_dir / file.filename

    try:
        with open(dest, "wb") as f:
            shutil.copyfileobj(file.file, f)
    except Exception as e:
        raise HTTPException(500, f"文件保存失敗: {e}")

    # 驗證策略
    strategy_classes = load_user_strategy(str(dest))
    if not strategy_classes:
        # 刪除無效文件
        dest.unlink(missing_ok=True)
        raise HTTPException(400, "文件中未找到有效的 UserStrategy 子類，或包含禁止的模塊")

    names = [getattr(s, "name", s.__name__) for s in strategy_classes]
    return {
        "success": True,
        "filename": file.filename,
        "filepath": str(dest),
        "strategies": names,
        "count": len(strategy_classes),
    }


@app.get("/api/strategies/leaderboard")
async def get_leaderboard_api(sort_by: str = "sharpe", limit: int = 50):
    """獲取策略排行榜"""
    from src.core.leaderboard import get_leaderboard, get_leaderboard_summary

    try:
        results = get_leaderboard(sort_by=sort_by, limit=limit)
        summary = get_leaderboard_summary()
        return {
            "success": True,
            "results": results,
            "summary": summary,
            "total": len(results),
            "empty": len(results) == 0,
            "hint": (
                "排行榜暫無數據，請先 POST /api/strategies/leaderboard/update 生成排名"
                if len(results) == 0 else None
            ),
        }
    except Exception as e:
        logger.error(f"獲取排行榜失敗: {e}", exc_info=True)
        raise HTTPException(500, str(e))


@app.post("/api/strategies/leaderboard/update")
async def update_leaderboard_api(codes: list[str] = None):
    """更新策略排行榜"""
    from src.core.leaderboard import update_leaderboard

    try:
        results = update_leaderboard(codes=codes)
        return {
            "success": True,
            "total": len(results),
            "message": f"排行榜已更新，共 {len(results)} 條記錄",
        }
    except Exception as e:
        logger.error(f"更新排行榜失敗: {e}")
        raise HTTPException(500, str(e))


@app.post("/api/strategies/test")
async def test_user_strategy(body: dict):
    """快速回測用戶策略"""
    from src.core.strategy_base import list_user_strategies, quick_backtest_user_strategy

    strategy_name = body.get("strategy_name", "").strip()
    code = body.get("code", "").strip()
    params = body.get("params", {})

    if not strategy_name or not code:
        raise HTTPException(400, "請提供 strategy_name 和 code")

    # 查找策略
    user_strategies = list_user_strategies()
    target = None
    for s in user_strategies:
        if s["name"] == strategy_name:
            target = s
            break

    if not target:
        raise HTTPException(404, f"未找到用戶策略: {strategy_name}，可用: {[s['name'] for s in user_strategies]}")

    try:
        cls = target["class"]
        instance = cls(**params)
        result = quick_backtest_user_strategy(instance, code)
        return {"success": True, "result": result}
    except Exception as e:
        logger.error(f"用戶策略回測失敗: {e}")
        raise HTTPException(500, str(e))


# ====== 實時行情 ======

@app.get("/api/realtime")
async def get_realtime(codes: str = None):
    """獲取實時行情"""
    from src.core.realtime import fetch_realtime

    if codes:
        code_list = codes.split(",")
    else:
        code_list = settings.watchlist

    try:
        df = fetch_realtime(code_list)
        if df.empty:
            return {"quotes": [], "message": "無數據（可能非交易時段）"}
        return {"quotes": df.to_dict(orient="records")}
    except Exception as e:
        logger.error(f"實時行情失敗: {e}")
        raise HTTPException(500, str(e))


# ====== 風險管理 API ======

@app.post("/api/risk/position-size")
async def risk_position_size(body: dict):
    """計算倉位大小 — 支持多種倉位計算方法"""
    from src.core.risk_manager import PositionSizer, calculate_atr

    capital = body.get("capital", 100000)
    method = body.get("method", "atr")  # atr / fixed / kelly / volatility / drawdown
    max_risk = body.get("max_risk_per_trade", 0.02)

    sizer = PositionSizer(total_capital=capital, max_risk_per_trade=max_risk)

    try:
        if method == "fixed":
            fraction = body.get("fraction", 0.1)
            result_value = sizer.fixed_fraction(fraction)
            return {
                "success": True,
                "method": "固定比例",
                "position_value": round(result_value, 2),
                "fraction": fraction,
            }

        elif method == "atr":
            atr = body.get("atr", 0)
            code = body.get("code")
            # 如果未直接提供 ATR，嘗試從股票數據計算
            if atr <= 0 and code:
                atr = calculate_atr(code)
            if atr <= 0:
                raise HTTPException(400, "請提供 ATR 值或股票代碼")

            risk_multiplier = body.get("risk_multiplier", 1.0)
            shares = sizer.atr_based(atr, risk_multiplier)
            position_value = shares * body.get("price", atr * 30)  # 估算金額
            return {
                "success": True,
                "method": "ATR 倉位",
                "shares": shares,
                "atr": atr,
                "risk_multiplier": risk_multiplier,
                "estimated_value": round(position_value, 2),
            }

        elif method == "kelly":
            win_rate = body.get("win_rate", 0.5)
            avg_win = body.get("avg_win", 1)
            avg_loss = body.get("avg_loss", 1)
            result_value = sizer.kelly_position(win_rate, avg_win, avg_loss)
            return {
                "success": True,
                "method": "Kelly 公式",
                "position_value": round(result_value, 2),
                "win_rate": win_rate,
                "avg_win": avg_win,
                "avg_loss": avg_loss,
            }

        elif method == "volatility":
            target_vol = body.get("target_vol", 0.15)
            current_vol = body.get("current_vol", 0.20)
            current_position = body.get("current_position", capital * 0.5)
            result_value = sizer.volatility_target(target_vol, current_vol, current_position)
            return {
                "success": True,
                "method": "波動率目標",
                "position_value": round(result_value, 2),
                "target_vol": target_vol,
                "current_vol": current_vol,
            }

        elif method == "drawdown":
            current_dd = body.get("current_dd_pct", 0)
            base_size = body.get("base_size", capital * 0.1)
            result_value = sizer.drawdown_adjusted(current_dd, base_size)
            return {
                "success": True,
                "method": "回撤調整",
                "position_value": round(result_value, 2),
                "current_dd_pct": current_dd,
            }

        else:
            raise HTTPException(400, f"未知方法: {method}，可選: atr, fixed, kelly, volatility, drawdown")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"倉位計算失敗: {e}")
        raise HTTPException(500, str(e))


@app.post("/api/risk/budget-check")
async def risk_budget_check(body: dict):
    """風險預算檢查 — 檢查持倉風險是否超限"""
    from src.core.risk_manager import RiskBudget

    max_portfolio_risk = body.get("max_portfolio_risk", 0.15)
    max_single_risk = body.get("max_single_risk", 0.05)
    positions = body.get("positions", [])

    budget = RiskBudget(max_portfolio_risk=max_portfolio_risk, max_single_risk=max_single_risk)

    try:
        # 組合風險預算
        portfolio_result = budget.portfolio_risk_budget(positions)

        # 單個持倉檢查
        total_value = sum(p.get("value", 0) for p in positions)
        position_checks = []
        for p in positions:
            check = budget.check_position(
                position_value=p.get("value", 0),
                total_value=total_value,
                position_vol=p.get("vol", 0),
            )
            check["code"] = p.get("code", "未知")
            position_checks.append(check)

        # 再平衡建議
        rebalance = budget.suggest_rebalance(positions)

        return {
            "success": True,
            "portfolio": portfolio_result,
            "position_checks": position_checks,
            "rebalance_suggestions": rebalance,
        }

    except Exception as e:
        logger.error(f"風險預算檢查失敗: {e}")
        raise HTTPException(500, str(e))


@app.post("/api/risk/drawdown-protect")
async def risk_drawdown_protect(body: dict):
    """回撤保護 — 分析淨值序列的回撤狀態和熔斷點"""
    from src.core.risk_manager import DrawdownProtector, drawdown_circuit_breaker

    mode = body.get("mode", "monitor")  # monitor / circuit_breaker

    try:
        if mode == "monitor":
            # 實時監控模式：傳入一系列淨值
            nav_values = body.get("nav_values", [])
            max_dd = body.get("max_drawdown_pct", 20.0)
            warning_dd = body.get("warning_pct", 10.0)

            protector = DrawdownProtector(max_drawdown_pct=max_dd, warning_pct=warning_dd)
            results = []
            for v in nav_values:
                result = protector.update(v)
                results.append(result)

            return {
                "success": True,
                "mode": "monitor",
                "results": results,
                "final_state": results[-1] if results else None,
            }

        elif mode == "circuit_breaker":
            # 熔斷分析模式：傳入完整淨值和日期序列
            nav = body.get("nav", [])
            dates = body.get("dates", [])
            max_dd = body.get("max_dd", 20.0)

            if not nav or not dates:
                raise HTTPException(400, "請提供 nav 和 dates 序列")

            result = drawdown_circuit_breaker(nav, dates, max_dd)
            return {"success": True, "mode": "circuit_breaker", "result": result}

        else:
            raise HTTPException(400, f"未知模式: {mode}，可選: monitor, circuit_breaker")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"回撤保護分析失敗: {e}")
        raise HTTPException(500, str(e))


# ====== 信號增強 API ======

@app.get("/api/signals/backtest")
async def signals_backtest(
    codes: str = None,
    strategies: str = None,
    days: int = 250,
):
    """信號回測驗證 — 計算歷史信號的準確率和前向收益"""
    from src.core.signals import backtest_signals

    try:
        code_list = codes.split(",") if codes else None
        strat_list = strategies.split(",") if strategies else None

        result = backtest_signals(codes=code_list, strategies=strat_list, days=days)
        return {"success": True, "result": result}

    except Exception as e:
        logger.error(f"信號回測失敗: {e}")
        raise HTTPException(500, str(e))


@app.get("/api/signals/heatmap")
async def signals_heatmap(
    codes: str = None,
    days: int = 30,
):
    """信號熱力圖 — codes × dates × signal_strength 矩陣"""
    from src.core.signals import signal_heatmap

    try:
        code_list = codes.split(",") if codes else None
        result = signal_heatmap(codes=code_list, days=days)
        return {"success": True, "result": result}

    except Exception as e:
        logger.error(f"信號熱力圖失敗: {e}")
        raise HTTPException(500, str(e))


@app.get("/api/signals/ranking")
async def signals_ranking(
    codes: str = None,
):
    """綜合信號排名 — 按複合信號強度排名所有股票"""
    from src.core.signals import composite_signal_ranking

    try:
        code_list = codes.split(",") if codes else None
        result = composite_signal_ranking(codes=code_list)
        return {"success": True, "result": result, "total": len(result)}

    except Exception as e:
        logger.error(f"信號排名失敗: {e}")
        raise HTTPException(500, str(e))


# ====== 數據增強 API ======

@app.get("/api/data/minutes")
async def get_minutes_data(code: str, period: str = "5m"):
    """獲取分鐘 K 線數據"""
    from src.core.db import load_minute_kline
    
    # 先從數據庫讀取
    df = load_minute_kline(code, period)
    
    if df.empty:
        # 數據庫無數據，嘗試下載
        try:
            from src.core.history import download_minute_data
            download_minute_data(code, period)
            df = load_minute_kline(code, period)
        except Exception as e:
            logger.error(f"分鐘K線下載失敗: {e}")
            raise HTTPException(500, f"分鐘K線數據獲取失敗: {e}")
    
    if df.empty:
        raise HTTPException(404, f"{code} {period} 無分鐘K線數據")
    
    records = df.to_dict(orient="records")
    return {"code": code, "period": period, "data": records, "count": len(records)}


@app.post("/api/data/minutes/download")
async def download_minutes_api(code: str, period: str = "5m"):
    """下載分鐘 K 線數據"""
    from src.core.history import download_minute_data
    
    try:
        count = download_minute_data(code, period)
        return {"success": True, "code": code, "period": period, "records": count}
    except Exception as e:
        logger.error(f"分鐘K線下載失敗: {e}")
        raise HTTPException(500, str(e))


@app.get("/api/data/sectors")
async def get_sectors(sector_type: str = "industry", top_n: int = 30):
    """獲取板塊列表（行業/概念）"""
    from src.core.sector import get_sector_list, get_sector_performance
    
    try:
        sectors = get_sector_performance(sector_type=sector_type, top_n=top_n)
        from_snapshot = bool(sectors and sectors[0].get("from_snapshot"))
        snapshot_date = sectors[0].get("snapshot_date") if from_snapshot else None
        source = sectors[0].get("source") if sectors else None
        return {
            "success": True,
            "sectors": sectors,
            "total": len(sectors),
            "type": sector_type,
            "from_snapshot": from_snapshot,
            "snapshot_date": snapshot_date,
            "source": source,
            "hint": (
                "實時板塊接口暫不可用且無本地快照；請稍後重試，或收盤後調用 POST /api/data/sectors/snapshot 保存快照"
                if not sectors else None
            ),
        }
    except Exception as e:
        logger.error(f"獲取板塊列表失敗: {e}", exc_info=True)
        raise HTTPException(500, str(e))


@app.get("/api/data/sector/{name}/stocks")
async def get_sector_stocks_api(name: str, sector_type: str = "industry"):
    """獲取板塊成分股"""
    from src.core.sector import get_sector_stocks
    
    try:
        stocks = get_sector_stocks(name, sector_type=sector_type)
        return {"sector": name, "stocks": stocks, "total": len(stocks)}
    except Exception as e:
        logger.error(f"獲取板塊 {name} 成分股失敗: {e}")
        raise HTTPException(500, str(e))


@app.get("/api/data/sectors/rotation")
async def get_sector_rotation_api(days: int = 10):
    """板塊輪動分析 — 排名變化最大的板塊"""
    from src.core.sector import get_sector_rotation
    try:
        rotation = get_sector_rotation(days)
        return {"rotation": rotation, "total": len(rotation), "days": days}
    except Exception as e:
        logger.error(f"板塊輪動分析失敗: {e}")
        raise HTTPException(500, str(e))


@app.get("/api/data/sector/{name}/trend")
async def get_sector_trend_api(name: str, days: int = 20):
    """板塊歷史趨勢 — 近 N 天漲跌走勢"""
    from src.core.sector import get_sector_trend
    try:
        trend = get_sector_trend(name, days)
        return {"sector": name, "trend": trend, "total": len(trend)}
    except Exception as e:
        logger.error(f"獲取板塊 {name} 趨勢失敗: {e}")
        raise HTTPException(500, str(e))


@app.post("/api/data/sectors/snapshot")
async def save_sector_snapshot_api(sector_type: str = "industry"):
    """保存當日板塊快照（收盤後調用）"""
    from src.core.sector import save_sector_snapshot
    try:
        count = save_sector_snapshot(sector_type)
        return {"success": True, "count": count, "sector_type": sector_type}
    except Exception as e:
        logger.error(f"保存板塊快照失敗: {e}")
        raise HTTPException(500, str(e))


@app.get("/api/data/sectors/heatmap")
async def get_sector_heatmap_api(sector_type: str = "industry"):
    """板塊全景數據 — 用於前端熱力圖"""
    from src.core.sector import get_sector_heatmap_data
    try:
        sectors = get_sector_heatmap_data(sector_type)
        return {"sectors": sectors, "total": len(sectors), "type": sector_type}
    except Exception as e:
        logger.error(f"板塊全景數據失敗: {e}")
        raise HTTPException(500, str(e))


@app.get("/api/data/sector/{name}/capital-flow")
async def get_sector_capital_flow_api(name: str):
    """板塊資金流向"""
    from src.core.sector import get_sector_capital_flow
    try:
        flows = get_sector_capital_flow(name)
        return {"sector": name, "flows": flows, "total": len(flows)}
    except Exception as e:
        logger.error(f"獲取板塊 {name} 資金流向失敗: {e}")
        raise HTTPException(500, str(e))


@app.get("/api/data/capital-flow")
async def get_capital_flow_api(code: str, days: int = 30):
    """獲取個股資金流向"""
    from src.core.capital_flow import get_capital_flow
    
    try:
        flows = get_capital_flow(code, days=days)
        return {"code": code, "flows": flows, "total": len(flows)}
    except Exception as e:
        logger.error(f"獲取 {code} 資金流向失敗: {e}")
        raise HTTPException(500, str(e))


@app.get("/api/data/market-flow")
async def get_market_flow_api():
    """獲取大盤資金流向"""
    from src.core.capital_flow import get_market_capital_flow
    
    try:
        flows = get_market_capital_flow()
        return {"flows": flows, "total": len(flows)}
    except Exception as e:
        logger.error(f"獲取大盤資金流向失敗: {e}")
        raise HTTPException(500, str(e))


@app.get("/api/data/north-flow")
async def get_north_flow_api(days: int = 30):
    """獲取北向資金流入"""
    from src.core.capital_flow import get_north_flow
    
    try:
        from src.core.capital_flow import aggregate_north_flow_daily

        flows = get_north_flow(days=days)
        daily = aggregate_north_flow_daily(flows)
        return {"flows": flows, "daily": daily, "total": len(flows), "daily_total": len(daily)}
    except Exception as e:
        logger.error(f"獲取北向資金失敗: {e}")
        raise HTTPException(500, str(e))


@app.get("/api/data/dragon-tiger")
async def get_dragon_tiger_api(date: str = None):
    """獲取龍虎榜數據"""
    from src.core.dragon_tiger import get_dragon_tiger
    
    try:
        records = get_dragon_tiger(date=date)
        return {"date": date or "today", "records": records, "total": len(records)}
    except Exception as e:
        logger.error(f"獲取龍虎榜失敗: {e}")
        raise HTTPException(500, str(e))


@app.get("/api/data/dragon-tiger/{code}/history")
async def get_dragon_tiger_history_api(code: str, days: int = 30):
    """獲取股票龍虎榜歷史"""
    from src.core.dragon_tiger import get_dragon_tiger_history
    
    try:
        records = get_dragon_tiger_history(code, days=days)
        return {"code": code, "records": records, "total": len(records)}
    except Exception as e:
        logger.error(f"獲取 {code} 龍虎榜歷史失敗: {e}")
        raise HTTPException(500, str(e))


@app.get("/api/data/fundamentals")
async def get_fundamentals_api(code: str):
    """獲取股票基本面數據"""
    from src.core.fundamental import get_fundamentals
    
    try:
        data = get_fundamentals(code)
        if not data:
            raise HTTPException(404, f"{code} 無基本面數據")
        return {"fundamentals": data}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"獲取 {code} 基本面失敗: {e}")
        raise HTTPException(500, str(e))


@app.post("/api/data/fundamentals/screen")
async def screen_fundamentals_api(body: dict):
    """按基本面指標篩選股票"""
    from src.core.fundamental import screen_by_fundamentals
    
    filters = body.get("filters", {})
    if not filters:
        raise HTTPException(400, "請提供篩選條件，如 pe_max, pb_max, roe_min 等")
    
    try:
        results = screen_by_fundamentals(filters)
        return {"results": results, "total": len(results), "filters": filters}
    except Exception as e:
        logger.error(f"基本面篩選失敗: {e}")
        raise HTTPException(500, str(e))


# ====== 增強回測分析 API ======

@app.post("/api/backtest/trade-analysis")
async def backtest_trade_analysis(body: dict):
    """交易深度分析 — 連勝連敗、盈虧比、期望收益等"""
    from src.core.backtest import run_backtest, trade_analysis

    code = body.get("code", "")
    strategy = body.get("strategy", "dual_ma")
    params = body.get("params")

    if not code:
        raise HTTPException(400, "請提供股票代碼")

    try:
        bt_result = run_backtest(code, strategy_name=strategy, params=params)
        analysis = trade_analysis(bt_result.get("trade_details", []))
        return {"success": True, "code": code, "strategy": strategy, "trade_analysis": analysis}
    except Exception as e:
        logger.error(f"交易分析失敗: {e}")
        raise HTTPException(500, str(e))


@app.post("/api/backtest/monte-carlo")
async def backtest_monte_carlo(body: dict):
    """蒙特卡羅模擬 — 基於歷史收益率的概率分析"""
    from src.core.backtest import run_backtest, monte_carlo_simulation

    code = body.get("code", "")
    strategy = body.get("strategy", "dual_ma")
    params = body.get("params")
    n_simulations = body.get("n_simulations", 1000)
    days = body.get("days", 252)

    if not code:
        raise HTTPException(400, "請提供股票代碼")

    try:
        bt_result = run_backtest(code, strategy_name=strategy, params=params)
        mc = monte_carlo_simulation(bt_result.get("daily_returns", []), n_simulations=n_simulations, days=days)
        return {"success": True, "code": code, "strategy": strategy, "monte_carlo": mc}
    except Exception as e:
        logger.error(f"蒙特卡羅模擬失敗: {e}")
        raise HTTPException(500, str(e))


@app.post("/api/backtest/rolling-metrics")
async def backtest_rolling_metrics(body: dict):
    """滾動指標 — 滾動夏普、Sortino、波動率時間序列"""
    from src.core.backtest import run_backtest, rolling_metrics

    code = body.get("code", "")
    strategy = body.get("strategy", "dual_ma")
    params = body.get("params")
    window = body.get("window", 60)

    if not code:
        raise HTTPException(400, "請提供股票代碼")

    try:
        bt_result = run_backtest(code, strategy_name=strategy, params=params)
        rm = rolling_metrics(bt_result.get("daily_returns", []), bt_result.get("dates", []), window=window)
        return {"success": True, "code": code, "strategy": strategy, "rolling_metrics": rm}
    except Exception as e:
        logger.error(f"滾動指標失敗: {e}")
        raise HTTPException(500, str(e))


@app.post("/api/report/full")
async def report_full(body: dict):
    """全面回測報告 — 包含所有分析維度"""
    from src.core.report_enhanced import generate_full_report

    code = body.get("code", "")
    strategy = body.get("strategy", "dual_ma")
    params = body.get("params")

    if not code:
        raise HTTPException(400, "請提供股票代碼")

    try:
        report = generate_full_report(code, strategy, params=params)
        return {"success": True, "report": report}
    except Exception as e:
        logger.error(f"全面報告失敗: {e}")
        raise HTTPException(500, str(e))


@app.post("/api/report/comparison")
async def report_comparison(body: dict):
    """多股對比報告 — 同一策略在多隻股票上的表現對比"""
    from src.core.report_enhanced import generate_comparison_report

    codes = body.get("codes", [])
    strategy = body.get("strategy", "dual_ma")

    if not codes:
        raise HTTPException(400, "請提供股票代碼列表")

    try:
        report = generate_comparison_report(codes, strategy)
        return {"success": True, "report": report}
    except Exception as e:
        logger.error(f"對比報告失敗: {e}")
        raise HTTPException(500, str(e))


@app.post("/api/report/strategy")
async def report_strategy(body: dict):
    """策略分析報告 — 一個策略在所有 watchlist 股票上的表現"""
    from src.core.report_enhanced import generate_strategy_report

    strategy = body.get("strategy", "")
    codes = body.get("codes")

    if not strategy:
        raise HTTPException(400, "請提供策略名稱")

    try:
        report = generate_strategy_report(strategy, codes=codes)
        return {"success": True, "report": report}
    except Exception as e:
        logger.error(f"策略報告失敗: {e}")
        raise HTTPException(500, str(e))


# ====== 風控管道 API ======

@app.post("/api/risk-pipeline/run")
async def run_risk_pipeline_api(body: dict = None):
    """運行信號→風控→交易管道"""
    from src.core.risk_pipeline import run_signal_pipeline

    if body is None:
        body = {}

    try:
        result = run_signal_pipeline(
            codes=body.get("codes"),
            total_capital=body.get("total_capital"),
            sizing_method=body.get("sizing_method", "atr"),
        )
        return {"success": True, "result": result}
    except Exception as e:
        logger.error(f"風控管道失敗: {e}")
        raise HTTPException(500, str(e))


@app.get("/api/risk-pipeline/state")
async def get_risk_pipeline_state():
    """獲取風控管道狀態"""
    from src.core.risk_pipeline import RiskPipeline
    pipeline = RiskPipeline()
    return {"success": True, "state": pipeline.get_state()}


# ====== 數據質量 API ======

@app.get("/api/data-quality/check")
async def data_quality_check(code: str = None, severity: str = None):
    """數據質量校驗"""
    from src.core.data_quality import validate_stock_data, validate_all

    try:
        if code:
            issues = validate_stock_data(code)
            return {"success": True, "code": code, "issues": [i.to_dict() for i in issues], "total": len(issues)}
        else:
            report = validate_all(severity_filter=severity)
            return {"success": True, **report}
    except Exception as e:
        logger.error(f"數據質量校驗失敗: {e}")
        raise HTTPException(500, str(e))


@app.post("/api/data-quality/repair")
async def data_quality_repair(code: str, dry_run: bool = True):
    """自動修復數據問題"""
    from src.core.data_quality import repair_data

    try:
        repairs = repair_data(code, dry_run=dry_run)
        return {"success": True, "code": code, "dry_run": dry_run, "repairs": repairs}
    except Exception as e:
        logger.error(f"數據修復失敗: {e}")
        raise HTTPException(500, str(e))


@app.get("/api/data-quality/splits")
async def detect_splits(code: str):
    """檢測除權除息事件"""
    from src.core.data_quality import detect_split_adjustments

    try:
        events = detect_split_adjustments(code)
        return {"success": True, "code": code, "events": events, "total": len(events)}
    except Exception as e:
        logger.error(f"除權檢測失敗: {e}")
        raise HTTPException(500, str(e))


# ====== 模擬交易 API ======

@app.post("/api/paper/start")
async def start_paper_trading(body: dict = None):
    """啟動模擬交易"""
    from src.core.paper_trading import PaperTradingEngine

    if body is None:
        body = {}

    try:
        engine = PaperTradingEngine(
            capital=body.get("capital"),
            name=body.get("name", "默認模擬盤"),
            sizing_method=body.get("sizing_method", "atr"),
            min_signal_strength=body.get("min_signal_strength", 10.0),
        )
        engine.start()
        return {"success": True, "session_id": engine.session_id, "status": engine.get_status()}
    except Exception as e:
        logger.error(f"啟動模擬交易失敗: {e}")
        raise HTTPException(500, str(e))


@app.post("/api/paper/{session_id}/tick")
async def paper_trading_tick(session_id: str):
    """執行一個模擬交易週期"""
    from src.core.paper_trading import PaperTradingEngine

    # 從數據庫恢復 session
    from src.core.paper_trading import get_paper_session
    session = get_paper_session(session_id)
    if not session:
        raise HTTPException(404, f"模擬盤不存在: {session_id}")

    try:
        config = {}
        if session.get("config"):
            import json
            config = json.loads(session["config"])

        engine = PaperTradingEngine(
            capital=session["initial_capital"],
            name=session["name"],
            session_id=session_id,
            sizing_method=config.get("sizing_method", "atr"),
            min_signal_strength=config.get("min_signal_strength", 10.0),
        )
        engine.start()
        trades = engine.tick()
        return {"success": True, "trades": trades, "status": engine.get_status()}
    except Exception as e:
        logger.error(f"模擬交易 tick 失敗: {e}")
        raise HTTPException(500, str(e))


@app.get("/api/paper/{session_id}/status")
async def paper_trading_status(session_id: str):
    """獲取模擬盤狀態"""
    from src.core.paper_trading import get_paper_session
    session = get_paper_session(session_id)
    if not session:
        raise HTTPException(404, f"模擬盤不存在: {session_id}")
    return {"success": True, "session": session}


@app.get("/api/paper/{session_id}/trades")
async def paper_trading_log(session_id: str, limit: int = 100):
    """獲取模擬盤交易日誌"""
    from src.core.paper_trading import PaperTradingEngine
    engine = PaperTradingEngine(session_id=session_id)
    return {"success": True, "trades": engine.get_trade_log(limit)}


@app.get("/api/paper/{session_id}/nav")
async def paper_trading_nav(session_id: str):
    """獲取模擬盤淨值歷史"""
    from src.core.paper_trading import PaperTradingEngine
    engine = PaperTradingEngine(session_id=session_id)
    return {"success": True, "nav_history": engine.get_nav_history()}


@app.get("/api/paper/sessions")
async def list_paper_sessions_api():
    """列出所有模擬盤"""
    from src.core.paper_trading import list_paper_sessions
    return {"success": True, "sessions": list_paper_sessions()}


@app.delete("/api/paper/{session_id}")
async def delete_paper_session_api(session_id: str):
    """刪除模擬盤"""
    from src.core.paper_trading import delete_paper_session
    success = delete_paper_session(session_id)
    if not success:
        raise HTTPException(404, f"模擬盤不存在: {session_id}")
    return {"success": True, "message": "已刪除"}


# ====== 調度器增強 API ======

@app.post("/api/scheduler/degradation/enable")
async def enable_degradation_api(codes: list[str] = None):
    """啟用策略衰減檢測"""
    from src.core.scheduler import enable_degradation_check
    enable_degradation_check(codes)
    return {"success": True, "message": "策略衰減檢測已啟用 (每日 16:00)"}


@app.post("/api/scheduler/degradation/disable")
async def disable_degradation_api():
    """禁用策略衰減檢測"""
    from src.core.scheduler import disable_degradation_check
    disable_degradation_check()
    return {"success": True, "message": "策略衰減檢測已禁用"}


@app.post("/api/scheduler/correlation/enable")
async def enable_correlation_api(codes: list[str] = None):
    """啟用策略相關性監控"""
    from src.core.scheduler import enable_correlation_monitor
    enable_correlation_monitor(codes)
    return {"success": True, "message": "策略相關性監控已啟用 (每週一 16:30)"}


@app.post("/api/scheduler/correlation/disable")
async def disable_correlation_api():
    """禁用策略相關性監控"""
    from src.core.scheduler import disable_correlation_monitor
    disable_correlation_monitor()
    return {"success": True, "message": "策略相關性監控已禁用"}


@app.post("/api/scheduler/data-quality/enable")
async def enable_data_quality_api():
    """啟用數據質量巡檢"""
    from src.core.scheduler import enable_data_quality_check
    enable_data_quality_check()
    return {"success": True, "message": "數據質量巡檢已啟用 (每日 09:00)"}


@app.post("/api/scheduler/data-quality/disable")
async def disable_data_quality_api():
    """禁用數據質量巡檢"""
    from src.core.scheduler import disable_data_quality_check
    disable_data_quality_check()
    return {"success": True, "message": "數據質量巡檢已禁用"}


# ====== 靜態文件（前端） ======

static_dir = Path(__file__).parent.parent.parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    logger.info(f"📁 靜態文件目錄: {static_dir}")
else:
    logger.warning(f"⚠️ 靜態文件目錄不存在: {static_dir}，使用內建儀表盤")


@app.get("/", response_class=HTMLResponse)
async def index():
    """首頁 — 返回前端 SPA"""
    index_file = static_dir / "index.html"
    if index_file.exists():
        return HTMLResponse(content=index_file.read_text(encoding="utf-8"))

    # 內建最小儀表盤（fallback）
    return HTMLResponse(content=_builtin_dashboard())


def _builtin_dashboard() -> str:
    """內建儀表盤 HTML — fallback 版（從 dashboard_fallback.py 載入）"""
    try:
        from src.api.dashboard_fallback import _builtin_dashboard as _fb_dashboard
        return _fb_dashboard()
    except ImportError:
        # 極簡 fallback：只顯示基本鏈接
        return """<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><title>stock-quant</title></head>
<body style="background:#0f172a;color:#e2e8f0;font-family:sans-serif;text-align:center;padding:80px">
<h1>📈 stock-quant</h1>
<p>static/index.html 未找到，使用內建 fallback。</p>
<p>請檢查 static/ 目錄是否存在。</p>
<p style="margin-top:30px"><a href="/api/health" style="color:#38bdf8">健康檢查</a> ·
<a href="/docs" style="color:#38bdf8">API 文檔</a></p>
</body></html>"""
