"""
FastAPI 應用 — Web API + 靜態前端 + WebSocket 實時推送
"""

import os
import time
import json
from pathlib import Path
from datetime import datetime
from contextlib import asynccontextmanager


from fastapi import (
    FastAPI,
    WebSocket,
    WebSocketDisconnect,
    HTTPException,
    Query,
    UploadFile,
    File,
    Depends,
    Request,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse

from src.config import settings
from src.core.db import init_db, get_db_stats, get_alert_logs, get_conn
from src.core.auth import require_auth, require_admin, get_current_user
from src.core.entitlements import gate_portfolio_task
from src.models.user import User
from src.utils.logger import logger

from src.api.constants import STOCK_NAMES
from src.api.demo import seed_demo_data
from src.api import state
from src.api.routers.health import router as health_router
from src.api.routers.tasks import router as tasks_router
from src.api.routers.indices import router as indices_router
from src.api.routers.assets import router as assets_router
from src.api.routers.dashboard_market import router as dashboard_market_router
from src.api.routers.auth import router as auth_router
from src.api.routers.stocks import router as stocks_router
from src.api.routers.backtest import router as backtest_router
from src.api.routers.target_search import router as target_search_router
from src.api.routers.alerts import router as alerts_router
from src.api.routers.data_center import router as data_center_router
from src.api.routers.crypto import router as crypto_router
from src.api.routers.external_check import router as external_check_router
from src.api.routers.llm import router as llm_router
from src.api.routers.portfolio_settlement import router as portfolio_settlement_router
from src.api.routers.user_allocation import router as user_allocation_router
from src.api.routers.billing import router as billing_router
from src.api.routers.stream import router as stream_router
from src.api.routers.indicators import router as indicators_router
from src.api.routers.factors import router as factors_router
from src.api.routers.ml_strategy import router as ml_strategy_router
from src.api.routers.stress import router as stress_router
from src.api.errors import register_exception_handlers, api_error_response
from src.api.portfolio_dispatch import dispatch_portfolio_async
from src.api.ws import router as ws_router, ws_realtime_push

# 啟動時間


@asynccontextmanager
async def lifespan(app: FastAPI):
    """應用生命週期"""
    init_db()
    try:
        from src.core.watchlist_store import apply_runtime_on_startup

        apply_runtime_on_startup()
    except Exception as e:
        logger.debug(f"自選股 runtime 載入跳過: {e}")
    # 生產環境安全檢查
    from src.core.auth import _validate_jwt_secret_for_production

    _validate_jwt_secret_for_production()

    try:
        from src.integrations.sentry_setup import init_sentry

        init_sentry()
    except Exception as e:
        logger.debug(f"Sentry 初始化跳過: {e}")

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

    # 自動發現用戶策略
    try:
        from src.core.strategy_base import list_user_strategies

        user_strategies = list_user_strategies()
        if user_strategies:
            logger.info(
                f"📋 已加載 {len(user_strategies)} 個用戶策略: {[s['name'] for s in user_strategies]}"
            )
        else:
            logger.info(
                "📋 用戶策略目錄為空（運行 `python main.py strategy create <名稱>` 創建）"
            )
    except Exception as e:
        logger.debug(f"用戶策略發現跳過: {e}")

    # 載入管理員控制開關（功能/策略/任務可見性）
    try:
        from src.core.admin_controls import apply_controls_on_startup

        apply_controls_on_startup()
    except Exception as e:
        logger.debug(f"管理員控制開關載入跳過: {e}")

    # 啟動定時任務調度器
    try:
        from src.core.scheduler import start_scheduler

        start_scheduler()
    except Exception as e:
        logger.debug(f"調度器啟動跳過: {e}")

    # 安全摘要
    _ws_auth = (
        "✅ 已啟用"
        if settings.effective_ws_auth_required
        else "⚠️ 已關閉（演示/開發模式）"
    )
    _jwt_ok = "✅ 已配置" if settings.jwt_secret else "⚠️ 未配置（自動生成）"
    logger.info(
        f"🔒 安全摘要: WS認證={_ws_auth} | JWT={_jwt_ok} | CORS={settings.cors_origins[:50]}"
    )
    settings.log_demo_security_warnings(logger)

    # 啟動 WebSocket 後台推送
    import asyncio
    from src.api.ws import set_event_loop, sync_broadcast, ws_realtime_push
    from src.api.sse import set_event_loop as set_sse_loop, sync_publish as sse_publish
    from src.core.task_manager import register_ws_broadcaster, register_task_broadcaster

    set_event_loop(asyncio.get_running_loop())
    set_sse_loop(asyncio.get_running_loop())
    register_ws_broadcaster(sync_broadcast)
    register_task_broadcaster(sse_publish)

    async def _ws_push_with_restart():
        """WebSocket 推送任務：異常時自動重啟（最多連續 5 次）。"""
        consecutive_failures = 0
        max_failures = 5
        while consecutive_failures < max_failures:
            try:
                await ws_realtime_push()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                consecutive_failures += 1
                logger.warning(
                    f"WebSocket 推送任務異常（{consecutive_failures}/{max_failures}）: {e}"
                )
                await asyncio.sleep(min(5 * consecutive_failures, 30))
        logger.error(f"WebSocket 推送任務連續失敗 {max_failures} 次，已停止重啟")

    _ws_task = asyncio.create_task(_ws_push_with_restart())

    try:
        from src.core.task_manager import (
            load_recent_tasks_from_db,
            recover_stale_tasks_on_startup,
            start_task_watchdog,
        )

        load_recent_tasks_from_db()
        recover_stale_tasks_on_startup()
        start_task_watchdog()
    except Exception as e:
        logger.debug(f"任務自癒/看門狗啟動跳過: {e}")

    if settings.cache_warmup_on_startup:
        try:
            import asyncio
            from src.core.cache_warmup import warmup_cache_async

            asyncio.create_task(warmup_cache_async())
        except Exception as e:
            logger.debug(f"緩存預熱跳過: {e}")

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
    try:
        from src.core.task_manager import stop_task_watchdog

        stop_task_watchdog()
    except Exception:
        pass
    logger.info("👋 應用關閉")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)
register_exception_handlers(app)

app.include_router(health_router)
app.include_router(tasks_router)
app.include_router(indices_router)
app.include_router(assets_router)
app.include_router(dashboard_market_router)
app.include_router(ws_router)
app.include_router(auth_router)
app.include_router(stocks_router)
app.include_router(backtest_router)
app.include_router(target_search_router)
app.include_router(alerts_router)
app.include_router(data_center_router)
app.include_router(crypto_router)
app.include_router(external_check_router)
app.include_router(llm_router)
app.include_router(portfolio_settlement_router)
app.include_router(user_allocation_router)
app.include_router(billing_router)
app.include_router(stream_router)
app.include_router(indicators_router)
app.include_router(factors_router)
app.include_router(ml_strategy_router)
app.include_router(stress_router)

# CORS
_cors_origins = (
    settings.cors_origins.split(",")
    if settings.cors_origins
    else ["http://localhost:8000"]
)

# 安全檢查：非 debug 模式下，CORS 包含 localhost 時警告
if not settings.debug:
    _localhost_origins = [
        o for o in _cors_origins if "localhost" in o or "127.0.0.1" in o
    ]
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

# 注意：全域 GZip 會干擾 SSE/StreamingResponse（可能導致串流端點卡住）。
# 如需壓縮，改用反向代理層（nginx/caddy）或針對非串流端點做選擇性壓縮。


@app.middleware("http")
async def api_timing_middleware(request: Request, call_next):
    """Add X-Response-Time-Ms header for /api routes."""
    path = request.url.path or ""
    if not path.startswith("/api/"):
        return await call_next(request)
    t0 = time.perf_counter()
    response = await call_next(request)
    ms = int((time.perf_counter() - t0) * 1000)
    response.headers["X-Response-Time-Ms"] = str(ms)
    try:
        from src.utils.metrics import observe_request

        observe_request(
            request.method, path, response.status_code, (time.perf_counter() - t0)
        )
    except Exception:
        pass
    return response


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


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    """安全響應頭 — 防禦 XSS / Clickjacking / MIME sniffing"""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    # CSP：允許 inline script（前端 IIFE 架構需要）+ unsafe-eval（ECharts）
    # script-src 去掉 fonts.googleapis.com（僅 style 需要）
    # connect-src 收緊為僅自身 + WebSocket（前端不直接調用外部 API）
    if not response.headers.get("Content-Security-Policy"):
        csp = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "img-src 'self' data: https: blob:; "
            "font-src 'self' https://fonts.gstatic.com data:; "
            "connect-src 'self' ws: wss:; "
            "frame-src 'self' https://www.tradingview.com https://s.tradingview.com; "
            "frame-ancestors 'self'; "
            "base-uri 'self'; "
            "form-action 'self'"
        )
        response.headers["Content-Security-Policy"] = csp
    return response


@app.middleware("http")
async def admin_controls_middleware(request: Request, call_next):
    """
    管理員全域控制開關：
    - 可一鍵控制 功能/策略/任務中心 是否對一般用戶可用
    - admin 一律放行
    """
    path = request.url.path or ""
    if not path.startswith("/api/"):
        return await call_next(request)

    # scope/action 判定（越靠前越精準，避免誤攔）
    scope = None
    action = None
    if path.startswith("/api/tasks"):
        scope = "tasks"
        if path == "/api/tasks":
            action = "list"
        elif path == "/api/tasks/queue":
            action = "queue"
        elif path == "/api/tasks/types":
            action = "types"
        elif path == "/api/tasks/stats":
            action = "stats"
        elif path.endswith("/cancel"):
            action = "cancel"
        elif path.endswith("/retry"):
            action = "retry"
        elif path.startswith("/api/tasks/batch/cancel"):
            action = "batch_cancel"
        elif path.startswith("/api/tasks/batch/delete"):
            action = "batch_delete"
        elif path.startswith("/api/tasks/cancel-pending"):
            action = "cancel_pending"
        elif path.startswith("/api/tasks/clear-completed"):
            action = "clear_completed"
        elif path.startswith("/api/tasks/cleanup"):
            action = "cleanup"
        elif path.endswith("/logs"):
            action = "logs"
        elif path.endswith("/params"):
            action = "params"
        elif path.endswith("/full"):
            action = "full"
        elif path.startswith("/api/tasks/pipeline"):
            action = "pipeline"
        elif path.startswith("/api/tasks/") and path.count("/") >= 3:
            action = "detail"
    elif path.startswith("/api/strategies"):
        scope = "strategies"
        if path == "/api/strategies/list":
            action = "list"
        elif path == "/api/strategies/likes":
            action = "list"
        elif path.startswith("/api/strategies/likes/toggle"):
            action = "list"
        elif path == "/api/strategies/params":
            action = "params"
        elif path == "/api/strategies/create":
            action = "create"
    elif path.startswith("/api/backtest/target-search"):
        scope = "features"
        action = "target_search"
    elif path.startswith("/api/backtest/advanced"):
        scope = "features"
        action = "backtest_advanced"
    elif path.startswith("/api/backtest/multi"):
        scope = "features"
        action = "backtest_multi"
    elif path.startswith("/api/backtest"):
        scope = "features"
        action = "backtest"
    elif path.startswith("/api/optimize") or path.startswith("/api/auto-optimize"):
        scope = "features"
        action = "optimize" if path.startswith("/api/optimize") else "auto_optimize"
    elif path.startswith("/api/portfolio") or path.startswith("/api/walkforward"):
        scope = "features"
        action = "portfolio" if path.startswith("/api/portfolio") else "walkforward"

    if not scope:
        return await call_next(request)

    # 取得 user（可選）：若無 token → 視為非 admin
    user = None
    try:
        auth = request.headers.get("Authorization") or ""
        if auth.lower().startswith("bearer "):
            token = auth.split(" ", 1)[1].strip()
            from src.core.auth import verify_token, get_user_by_id

            payload = verify_token(token)
            if payload:
                user = get_user_by_id(payload.get("user_id"))
    except Exception:
        user = None

    try:
        from src.core.admin_controls import is_allowed

        if not is_allowed(scope, action, user=user):
            return api_error_response(
                request, 403, "此功能已被管理員關閉（僅管理員可用）"
            )
    except Exception:
        # 保守策略：控制開關異常時不阻擋
        pass

    return await call_next(request)


# ============================================================
# API 限流 — 有界滑動窗口限流（自動清理，無內存泄漏）
# ============================================================
# --- Rate Limiter：優先 Redis（跨實例），降級進程內存 ---
from src.core.rate_limiter import check_rate_limit

_rate_limit_per_minute = settings.rate_limit_per_minute
_auth_rate_limit = 10  # login/register 防暴力


_RATE_LIMIT_SKIP_PREFIX = (
    "/api/health",
    "/api/status",
    "/api/tasks",
    "/api/stock-logo/",
    "/api/iconfont/",
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
    is_auth = path.startswith("/api/auth/login") or path.startswith(
        "/api/auth/register"
    )
    limit = _auth_rate_limit if is_auth else _rate_limit_per_minute
    namespace = "auth" if is_auth else ""
    allowed, retry_after = check_rate_limit(client_ip, limit, namespace=namespace)

    if not allowed:
        resp = api_error_response(request, 429, "請求過於頻繁，請稍後再試")
        resp.headers["Retry-After"] = str(retry_after)
        return resp

    return await call_next(request)


# ============================================================
# 認證中間件 — 向後兼容（無 token 時允許通過）
# ============================================================

# 不需要認證的路徑前綴（白名單）
AUTH_WHITELIST_PREFIX = (
    "/api/auth/login",
    "/api/auth/register",
    "/api/health",
    "/api/health/sop",
    "/api/health/detailed",
    "/api/status",
    "/api/config",
    "/api/iconfont/config",
    "/api/stock-logo/",
    "/api/strategies/list",
    "/api/stocks",
    "/api/stocks/names",
    "/api/stock-universe",
    "/api/data-sources",
    "/api/markets",
    "/api/indices",
    "/api/assets",
    "/api/dashboard",
    "/api/data/",
    "/api/tasks",
    "/api/task-events",
    "/api/external",
    "/api/sparkline",
    "/api/signals/",
    "/api/backtest/history",
    "/api/alerts",
    "/api/watchlist",
    "/api/llm/status",
    "/docs",
    "/openapi.json",
    "/redoc",
    "/static",
    "/",
    "/ws",
)
# 精確匹配，避免 /api/strategies/leaderboard/update 被誤放行
AUTH_WHITELIST_EXACT = (
    "/api/strategies/leaderboard",
    "/api/strategies/params",
    "/api/strategies/likes",
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
    # 本地 debug / 非公開演示：回測/優化/組合允許匿名提交
    if (
        settings.debug or settings.demo_mode
    ) and not settings.is_public_demo_deployment():
        if path.startswith(
            ("/api/backtest", "/api/optimize", "/api/auto-optimize", "/api/portfolio")
        ):
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

    needs_auth = path.startswith("/api/") and (
        not _auth_read_allowed(path) or _auth_write_requires_login(path, method)
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
                return api_error_response(
                    request, 401, "Token 無效或已過期，請重新登錄"
                )
        else:
            # 無 token
            return api_error_response(
                request, 401, "未登錄，請先獲取 Token（POST /api/auth/login）"
            )

    response = await call_next(request)
    return response


# ============================================================
# API 路由
# ============================================================


# ============================================================
# P5: 路由拆分 — 從 app.py 提取的領域路由
# ============================================================
from src.api.routers.portfolio import router as portfolio_router
from src.api.routers.management import router as management_router
from src.api.routers.signals_heatmap import router as signals_heatmap_router
from src.api.routers.risk import router as risk_router
from src.api.routers.report_backtest import router as report_backtest_router
from src.api.routers.paper import router as paper_router
from src.api.routers.data_ops import router as data_ops_router
from src.api.routers.strategies import router as strategies_router
from src.api.routers.static_pages import router as static_pages_router

app.include_router(portfolio_router)
app.include_router(management_router)
app.include_router(signals_heatmap_router)
app.include_router(risk_router)
app.include_router(report_backtest_router)
app.include_router(paper_router)
app.include_router(data_ops_router)
app.include_router(strategies_router)
app.include_router(static_pages_router)

# 靜態文件掛載（必須在路由之後）
_static_dir = Path(__file__).parent.parent.parent / "static"
if _static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")
    logger.info(f"📁 靜態文件目錄: {_static_dir}")
else:
    logger.warning(f"⚠️ 靜態文件目錄不存在: {_static_dir}，使用內建儀表盤")


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
