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
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse

from src.config import settings
from src.core.db import init_db, get_db_stats, get_alert_logs, get_conn
from src.core.auth import require_auth, require_admin
from src.utils.logger import logger


# 啟動時間
_start_time = time.time()


# 常用 A 股中文名映射
STOCK_NAMES = {
    "000001": "平安銀行", "000002": "萬科A", "000063": "中興通訊",
    "000100": "TCL科技", "000157": "中聯重科", "000333": "美的集團",
    "000338": "濰柴動力", "000425": "徐工機械", "000538": "雲南白藥",
    "000568": "瀘州老窖", "000625": "長安汽車", "000651": "格力電器",
    "000661": "長春高新", "000725": "京東方A", "000768": "中航西飛",
    "000776": "廣發證券", "000858": "五糧液", "000895": "雙匯發展",
    "000938": "紫光股份", "000977": "浪潮信息", "002027": "分眾傳媒",
    "002049": "紫光國微", "002120": "韻達股份", "002142": "寧波銀行",
    "002230": "科大訊飛", "002271": "東方雨虹", "002304": "洋河股份",
    "002352": "順豐控股", "002371": "北方華創", "002415": "海康威視",
    "002460": "贛鋒鋰業", "002475": "立訊精密", "002594": "比亞迪",
    "002714": "牧原股份", "002812": "恩捷股份", "002916": "深南電路",
    "003816": "中南傳媒", "300003": "樂普醫療", "300015": "愛爾眼科",
    "300033": "同花順", "300059": "東方財富", "300124": "匯川技術",
    "300142": "沃森生物", "300274": "陽光電源", "300347": "泰格醫藥",
    "300408": "三環集團", "300413": "芒果超媒", "300450": "先導智能",
    "300454": "深信服", "300496": "中科创達", "300529": "健帆生物",
    "300601": "康泰生物", "300628": "億聯網絡", "300750": "寧德時代",
    "300760": "邁瑞醫療", "300782": "卓勝微", "300896": "愛美客",
    "600000": "浦發銀行", "600009": "上海機場", "600016": "民生銀行",
    "600018": "上港集團", "600019": "寶鋼股份", "600028": "中國石化",
    "600030": "中信證券", "600031": "三一重工", "600036": "招商銀行",
    "600048": "保利發展", "600050": "中國聯通", "600056": "中國醫藥",
    "600085": "同仁堂", "600089": "特變電工", "600104": "上汽集團",
    "600111": "北方稀土", "600115": "東方航空", "600132": "重慶啤酒",
    "600150": "中國船舶", "600176": "中國巨石", "600183": "生益科技",
    "600196": "復星醫藥", "600276": "恒瑞醫藥", "600309": "萬華化學",
    "600346": "恒力石化", "600352": "浙江龍盛", "600406": "國電南瑞",
    "600436": "片仔癀", "600438": "通威股份", "600460": "士蘭微",
    "600489": "中金黃金", "600519": "貴州茅台", "600547": "山東黃金",
    "600570": "恒生電子", "600585": "海螺水泥", "600588": "用友網絡",
    "600600": "青島啤酒", "600660": "福耀玻璃", "600690": "海爾智家",
    "600703": "三安光電", "600745": "聞泰科技", "600760": "中航沈飛",
    "600809": "山西汾酒", "600837": "海通證券", "600845": "寶信軟件",
    "600887": "伊利股份", "600893": "航發動力", "600900": "長江電力",
    "600918": "中泰證券", "600919": "江蘇銀行", "600938": "中國海油",
    "601006": "大秦鐵路", "601012": "隆基綠能", "601021": "春秋航空",
    "601066": "中信建投", "601088": "中國神華", "601100": "恒立液壓",
    "601111": "中國國航", "601138": "工業富聯", "601155": "新城控股",
    "601166": "興業銀行", "601169": "北京銀行", "601211": "國泰君安",
    "601225": "陝西煤業", "601236": "紅塔證券", "601288": "農業銀行",
    "601318": "中國平安", "601328": "交通銀行", "601336": "新華保險",
    "601390": "中國中鐵", "601398": "工商銀行", "601601": "中國太保",
    "601628": "中國人壽", "601668": "中國建築", "601669": "中國電建",
    "601688": "華泰證券", "601698": "中國衛通", "601766": "中國中車",
    "601788": "光大證券", "601799": "星宇股份", "601816": "京滬高鐵",
    "601818": "光大銀行", "601857": "中國石油", "601877": "正泰電器",
    "601881": "中國銀河", "601888": "中國中免", "601899": "紫金礦業",
    "601919": "中遠海控", "601985": "中國核電", "601988": "中國銀行",
    "601989": "中國重工", "601995": "中金公司", "601998": "中信銀行",
    "603019": "中科曙光", "603160": "匯頂科技", "603259": "藥明康德",
    "603288": "海天味業", "603501": "韋爾股份", "603799": "華友鈷業",
    "603882": "金域醫學", "603986": "兆易創新", "688005": "容百科技",
    "688009": "中國通號", "688012": "中微公司", "688036": "傳音控股",
    "688111": "金山辦公", "688169": "石頭科技", "688187": "時代電氣",
    "688223": "晶科能源", "688303": "大全能源", "688396": "華潤微",
    "688561": "奇安信", "688599": "天合光能", "688981": "中芯國際",
}


def _seed_demo_data():
    """演示模式：後台填充示範數據（不阻塞啟動，自動重試）"""
    import threading

    DEMO_CODES = ["000001", "600519", "000858", "601318", "000333"]
    DEMO_STRATEGIES = ["dual_ma", "macd", "bollinger", "rsi", "momentum"]

    def _worker():
        try:
            from src.core.db import load_all_codes, load_daily_kline, init_db
            from src.core.auth import ensure_default_admin

            # Step 0: 確保數據庫和管理員存在
            init_db()
            ensure_default_admin()

            # Step 1: 檢查是否已有數據
            has_data = True
            for code in DEMO_CODES[:2]:
                df = load_daily_kline(code)
                if df.empty:
                    has_data = False
                    break

            if has_data:
                logger.info("📦 演示模式：數據已存在，跳過填充")
                return

            # Step 2: 下載 A 股示範數據（帶重試）
            logger.info("📦 演示模式：正在下載 A 股示範數據...")
            from src.core.history import download_one

            total = 0
            for i, code in enumerate(DEMO_CODES, 1):
                for attempt in range(3):
                    try:
                        count = download_one(code)
                        if count > 0:
                            total += count
                            logger.info(f"📦 [{i}/{len(DEMO_CODES)}] {code}: {count} 條")
                            break
                    except Exception as e:
                        logger.debug(f"📦 {code} 第{attempt+1}次下載失敗: {e}")
                        if attempt < 2:
                            time.sleep(3)
                time.sleep(1)

            logger.info(f"📦 A 股下載完成: {total} 條記錄")

            # Step 3: 執行回測填充歷史（每個 demo 股票跑全策略）
            if total > 0:
                logger.info("📦 演示模式：正在生成回測歷史...")
                from src.core.backtest import run_backtest
                bt_count = 0
                for code in DEMO_CODES[:3]:
                    for strat in DEMO_STRATEGIES[:3]:
                        try:
                            run_backtest(code, strategy_name=strat)
                            bt_count += 1
                        except Exception as e:
                            logger.debug(f"📦 回測 {code}/{strat} 跳過: {e}")
                logger.info(f"📦 演示模式：已生成 {bt_count} 條回測記錄")

            logger.info("📦 演示模式初始化完成 ✅")

        except Exception as e:
            logger.warning(f"📦 演示數據填充失敗（服務仍正常運行）: {e}")

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    logger.info("📦 演示模式：後台數據填充已啟動")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """應用生命週期"""
    init_db()
    logger.info(f"🚀 {settings.app_name} v{settings.app_version} 啟動")
    logger.info(f"   http://{settings.web_host}:{settings.web_port}")

    # 演示模式或數據為空時：自動填充數據
    if settings.demo_mode:
        _seed_demo_data()
    else:
        # 非演示模式也檢查：如果數據庫為空，自動下載基礎數據
        try:
            from src.core.db import load_all_codes
            codes = load_all_codes()
            if not codes:
                logger.info("📦 數據庫為空，自動下載基礎數據...")
                _seed_demo_data()
        except Exception:
            _seed_demo_data()

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

    # 啟動 WebSocket 後台推送
    import asyncio
    _ws_task = asyncio.create_task(_ws_realtime_push())

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


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """滑動窗口限流：每 IP 每分鐘最多 N 次請求"""
    if not request.url.path.startswith("/api/"):
        return await call_next(request)

    client_ip = request.client.host if request.client else "unknown"
    allowed, retry_after = _rate_limiter.check(client_ip)

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
AUTH_WHITELIST = ("/api/auth/login", "/api/auth/register", "/api/health", "/api/health/detailed", "/api/status", "/api/config", "/api/strategies/list", "/api/stocks", "/api/stocks/names", "/api/data-sources", "/api/markets", "/docs", "/openapi.json", "/redoc", "/static", "/", "/ws")


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """
    認證中間件 — 檢查 Authorization header

    - 白名單路徑：放行
    - 有有效 token：注入 request.state.user
    - 無 token：返回 401（安全模式）
    """
    path = request.url.path

    # 白名單路徑直接放行
    is_whitelisted = any(path.startswith(prefix) for prefix in AUTH_WHITELIST)

    if not is_whitelisted and path.startswith("/api/"):
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


@app.get("/api/health")
async def health_check():
    """健康檢查"""
    uptime_sec = int(time.time() - _start_time)
    hours, remainder = divmod(uptime_sec, 3600)
    minutes, seconds = divmod(remainder, 60)

    try:
        stats = get_db_stats()
        db_status = "ok"
    except Exception:
        stats = {"db_size_mb": 0, "total_stocks": 0, "total_alerts": 0}
        db_status = "error"

    # 檢查數據是否就緒
    data_ready = stats.get("total_stocks", 0) > 0

    return {
        "status": "ok",
        "version": settings.app_version,
        "database": db_status,
        "data_ready": data_ready,
        "uptime": f"{hours}h {minutes}m {seconds}s",
        **stats,
    }


@app.get("/api/health/detailed")
async def health_detailed():
    """
    詳細健康檢查 — 包含 Redis、DB、磁盤、內存狀態
    """
    import shutil

    uptime_sec = int(time.time() - _start_time)
    hours, remainder = divmod(uptime_sec, 3600)
    minutes, seconds = divmod(remainder, 60)

    result = {
        "status": "ok",
        "version": settings.app_version,
        "uptime": f"{hours}h {minutes}m {seconds}s",
        "uptime_seconds": uptime_sec,
    }

    # ---- 數據庫狀態 ----
    try:
        stats = get_db_stats()
        result["database"] = {"status": "ok", **stats}
    except Exception as e:
        result["database"] = {"status": "error", "error": str(e)}
        result["status"] = "degraded"

    # ---- Redis 狀態 ----
    try:
        from src.core.cache import get_cache
        cache = get_cache()
        cache_stats = cache.stats()
        result["redis"] = {
            "available": cache.is_redis_available,
            "backend": cache_stats.get("backend", "unknown"),
            **cache_stats,
        }
    except Exception as e:
        result["redis"] = {"available": False, "error": str(e)}

    # ---- 磁盤空間 ----
    try:
        disk = shutil.disk_usage("/")
        result["disk"] = {
            "total_gb": round(disk.total / (1024**3), 2),
            "used_gb": round(disk.used / (1024**3), 2),
            "free_gb": round(disk.free / (1024**3), 2),
            "usage_pct": round(disk.used / disk.total * 100, 1),
        }
    except Exception:
        result["disk"] = {"status": "unavailable"}

    # ---- 內存使用 ----
    try:
        import resource
        usage = resource.getrusage(resource.RUSAGE_SELF)
        # maxrss 單位：Linux 是 KB，macOS 是 bytes
        import sys
        maxrss_kb = usage.ru_maxrss if sys.platform == "linux" else usage.ru_maxrss / 1024
        result["memory"] = {
            "max_rss_mb": round(maxrss_kb / 1024, 2),
        }
        # 嘗試 psutil 獲取更詳細信息
        try:
            import psutil
            proc = psutil.Process()
            mem_info = proc.memory_info()
            result["memory"]["rss_mb"] = round(mem_info.rss / (1024**2), 2)
            result["memory"]["vms_mb"] = round(mem_info.vms / (1024**2), 2)
            sys_mem = psutil.virtual_memory()
            result["memory"]["system_total_gb"] = round(sys_mem.total / (1024**3), 2)
            result["memory"]["system_available_gb"] = round(sys_mem.available / (1024**3), 2)
            result["memory"]["system_usage_pct"] = sys_mem.percent
        except ImportError:
            pass
    except Exception:
        result["memory"] = {"status": "unavailable"}

    return result


@app.get("/api/data-sources")
async def get_data_sources():
    """獲取所有數據源狀態"""
    from src.core.data_sources import health_check
    return {"sources": health_check()}


@app.get("/api/status")
async def system_status():
    """系統狀態"""
    stats = get_db_stats()
    uptime_sec = int(time.time() - _start_time)

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
    from src.core.db import load_all_codes
    codes = load_all_codes()

    stocks = []
    for code in codes:
        name = STOCK_NAMES.get(code, "")
        # 嘗試從 alert_rules 獲取名稱
        if not name:
            rule = settings.alert_rules.get(code, {})
            name = rule.get("name", code)
        stocks.append({"code": code, "name": name, "data_points": 0})

    return {"stocks": stocks, "total": len(stocks)}


@app.get("/api/stocks/names")
async def get_stock_names():
    """獲取股票代碼→中文名映射"""
    return {"names": STOCK_NAMES}


@app.post("/api/stocks/compare")
async def compare_stocks(body: dict):
    """多股收益率對比"""
    from src.core.db import load_daily_kline

    codes = body.get("codes", [])
    days = body.get("days", 250)
    start = body.get("start")

    if not codes:
        raise HTTPException(400, "請提供股票代碼列表")

    result = {}
    for code in codes:
        df = load_daily_kline(code, start_date=start)
        if df.empty:
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

    return {"comparison": result}


@app.get("/api/stocks/{code}/kline")
async def get_kline(code: str, start: str = None, end: str = None, limit: int = 500):
    """獲取 K 線數據"""
    from src.core.db import load_daily_kline
    df = load_daily_kline(code, start_date=start, end_date=end)

    if df.empty:
        raise HTTPException(404, f"股票 {code} 無數據")

    # 限制返回量
    if len(df) > limit:
        df = df.tail(limit)

    records = df.to_dict(orient="records")
    return {"code": code, "data": records, "count": len(records)}


@app.post("/api/stocks/download")
async def download_stocks(codes: list[str] = None):
    """下載歷史數據"""
    from src.core.history import download_all

    if codes is None:
        codes = settings.watchlist

    # 異步執行（實際生產中應放到後台任務）
    count = download_all(codes)
    return {"message": f"下載完成", "records": count, "codes": codes}


@app.post("/api/stocks/update")
async def incremental_update(codes: list[str] = None, force: bool = False):
    """增量更新歷史數據"""
    from src.core.history import download_incremental

    try:
        result = download_incremental(codes=codes, force=force)
        return {"success": True, "result": result}
    except Exception as e:
        logger.error(f"增量更新失敗: {e}")
        raise HTTPException(500, str(e))


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


@app.post("/api/markets/{market}/download")
async def download_market_data(market: str, codes: list[str] = None):
    """下載指定市場的歷史數據"""
    from src.core.history import download_one
    from src.core.global_market import MARKET_CATALOG

    if codes is None:
        if market == "crypto":
            codes = settings.crypto_watchlist
        elif market == "forex":
            codes = settings.forex_watchlist
        elif market in MARKET_CATALOG:
            codes = list(MARKET_CATALOG[market]["symbols"].keys())
        else:
            codes = settings.watchlist

    results = []
    total = 0
    for code in codes:
        count = download_one(code)
        total += count
        results.append({"code": code, "records": count})
        time.sleep(0.5)

    return {
        "success": True,
        "market": market,
        "total_records": total,
        "details": results,
    }


@app.post("/api/download-all")
async def download_all_markets():
    """批量下載所有市場的股票數據（A股 + 美股 + 港股 + 指數 + ETF + 商品 + 加密 + 外匯）"""
    from src.core.history import download_one
    from src.core.global_market import MARKET_CATALOG

    all_results = []
    grand_total = 0

    # A 股（watchlist）
    logger.info("===== 開始下載 A 股 =====")
    for code in settings.watchlist:
        count = download_one(code, market="a_share")
        grand_total += count
        all_results.append({"market": "a_share", "code": code, "records": count})
        time.sleep(1)

    # 全球市場（美股、港股、指數、ETF、商品）
    for market_key in ["us_stock", "hk_stock", "index", "etf", "commodity"]:
        cat = MARKET_CATALOG.get(market_key, {})
        symbols = list(cat.get("symbols", {}).keys())
        logger.info(f"===== 開始下載 {cat.get('name', market_key)} ({len(symbols)} 個標的) =====")
        for code in symbols:
            count = download_one(code, market="global")
            grand_total += count
            all_results.append({"market": market_key, "code": code, "records": count})
            time.sleep(0.8)

    # 加密貨幣
    logger.info(f"===== 開始下載加密貨幣 ({len(settings.crypto_watchlist)} 個標的) =====")
    for code in settings.crypto_watchlist:
        count = download_one(code, market="crypto")
        grand_total += count
        all_results.append({"market": "crypto", "code": code, "records": count})
        time.sleep(0.5)

    # 外匯
    logger.info(f"===== 開始下載外匯 ({len(settings.forex_watchlist)} 個標的) =====")
    for code in settings.forex_watchlist:
        count = download_one(code, market="forex")
        grand_total += count
        all_results.append({"market": "forex", "code": code, "records": count})
        time.sleep(0.5)

    success_count = sum(1 for r in all_results if r["records"] > 0)
    return {
        "success": True,
        "total_records": grand_total,
        "total_symbols": len(all_results),
        "success_symbols": success_count,
        "details": all_results,
    }


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
    用於儀表盤監控列表的迷你圖。
    """
    from src.core.db import load_daily_kline

    code_list = [c.strip() for c in codes.split(",") if c.strip()]
    result = {}

    for code in code_list:
        df = load_daily_kline(code)
        if df.empty:
            result[code] = {"prices": [], "change_pct": 0}
            continue

        df = df.tail(days)
        prices = df["close"].tolist()
        dates = df["date"].tolist()

        if len(prices) >= 2:
            change = (prices[-1] - prices[0]) / prices[0] * 100
        else:
            change = 0

        result[code] = {
            "prices": [round(p, 4) for p in prices],
            "dates": dates,
            "change_pct": round(change, 2),
            "latest": round(prices[-1], 4) if prices else 0,
        }

    return {"sparklines": result}


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
    from src.core.task_manager import create_task, update_task, STATUS_COMPLETED, STATUS_FAILED

    if strategy not in STRATEGIES:
        raise HTTPException(400, f"未知策略: {strategy}，可選: {list(STRATEGIES.keys())}")

    # 任務去重
    task_params = {"code": code, "strategy": strategy, "params": params, "cash": cash}
    task = create_task("backtest", task_params, title=f"回測 {code}/{strategy}")
    if task.get("is_duplicate"):
        return {"success": True, "task_id": task["task_id"], "is_duplicate": True,
                "message": "相同回測正在執行中，請等待完成"}

    try:
        result = run_backtest(
            code, strategy_name=strategy, params=params, cash=cash,
            stop_loss_pct=stop_loss_pct, take_profit_pct=take_profit_pct,
            trailing_stop_pct=trailing_stop_pct, benchmark=benchmark,
        )
        update_task(task["task_id"], status=STATUS_COMPLETED, progress=100, result=result)
        return {"success": True, "task_id": task["task_id"], "result": result}
    except Exception as e:
        update_task(task["task_id"], status=STATUS_FAILED, error=str(e))
        logger.error(f"回測失敗: {e}")
        raise HTTPException(500, str(e))


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
    from src.core.task_manager import create_task, update_task, STATUS_COMPLETED, STATUS_FAILED

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
                "message": "相同進階回測正在執行中，請等待完成"}

    try:
        result = run_backtest(
            code, strategy_name=strategy, params=params, cash=cash,
            commission=commission, stop_loss_pct=stop_loss_pct,
            take_profit_pct=take_profit_pct, trailing_stop_pct=trailing_stop_pct,
            benchmark=benchmark, slippage_pct=slippage_pct,
            enable_t1=enable_t1, enable_limit=enable_limit,
        )
        update_task(task["task_id"], status=STATUS_COMPLETED, progress=100, result=result)
        return {"success": True, "task_id": task["task_id"], "result": result}
    except Exception as e:
        update_task(task["task_id"], status=STATUS_FAILED, error=str(e))
        logger.error(f"進階回測失敗: {e}")
        raise HTTPException(500, str(e))


@app.post("/api/backtest/multi")
async def run_multi_backtest_api(code: str):
    """所有策略對比（自動加入任務列表）"""
    from src.core.backtest import run_multi_strategy
    from src.core.task_manager import create_task, update_task, STATUS_COMPLETED, STATUS_FAILED

    if not code:
        raise HTTPException(400, "請提供股票代碼")

    # 任務去重
    task_params = {"code": code}
    task = create_task("backtest_multi", task_params, title=f"多策略對比 {code}")
    if task.get("is_duplicate"):
        return {"success": True, "task_id": task["task_id"], "is_duplicate": True,
                "message": "相同多策略對比正在執行中，請等待完成"}

    try:
        results = run_multi_strategy(code)
        update_task(task["task_id"], status=STATUS_COMPLETED, progress=100, result=results)
        return {"success": True, "task_id": task["task_id"], "results": results}
    except Exception as e:
        update_task(task["task_id"], status=STATUS_FAILED, error=str(e))
        logger.error(f"多策略回測失敗: {e}")
        raise HTTPException(500, str(e))


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
    from src.core.task_manager import create_task, update_task, STATUS_COMPLETED, STATUS_FAILED

    if not code:
        raise HTTPException(400, "請提供股票代碼")

    # 任務去重
    task_params = {"code": code, "strategy": strategy, "method": method, "objective": objective, "n_trials": n_trials}
    display_strategy = strategy if strategy != "all" else "全部策略"
    task = create_task("optimize", task_params, title=f"參數優化 {code}/{display_strategy}")
    if task.get("is_duplicate"):
        return {"success": True, "task_id": task["task_id"], "is_duplicate": True,
                "message": "相同優化正在執行中，請等待完成"}

    try:
        if strategy == "all":
            results = optimize_all(code, objective=objective, method=method, n_trials=n_trials, top_n=top_n)
            # 轉為可序列化格式
            serialized = {}
            for name, res_list in results.items():
                serialized[name] = [{k: v for k, v in r.items()} for r in res_list]
            update_task(task["task_id"], status=STATUS_COMPLETED, progress=100, result=serialized)
            return {"success": True, "task_id": task["task_id"], "results": serialized}
        else:
            if method == "optuna":
                results = optuna_search(code, strategy, objective=objective, n_trials=n_trials)
            else:
                results = grid_search(code, strategy, objective=objective, top_n=top_n)
            update_task(task["task_id"], status=STATUS_COMPLETED, progress=100, result=results)
            return {"success": True, "task_id": task["task_id"], "results": results}
    except Exception as e:
        update_task(task["task_id"], status=STATUS_FAILED, error=str(e))
        logger.error(f"優化失敗: {e}")
        raise HTTPException(500, str(e))


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
    from src.core.task_manager import create_task, update_task, STATUS_COMPLETED, STATUS_FAILED

    if not allocations:
        raise HTTPException(400, "請提供組合配置")

    # 任務去重
    codes = [a.get("code", "") for a in allocations]
    task_params = {"codes": codes, "weights": weights, "rebalance": rebalance}
    task = create_task("portfolio", task_params, title=f"組合回測 ({len(allocations)}隻)")
    if task.get("is_duplicate"):
        return {"success": True, "task_id": task["task_id"], "is_duplicate": True,
                "message": "相同組合回測正在執行中，請等待完成"}

    try:
        result = run_portfolio(
            allocations=allocations,
            weights=weights,
            rebalance=rebalance,
            rebalance_freq_days=rebalance_freq_days,
            cash=cash,
        )
        update_task(task["task_id"], status=STATUS_COMPLETED, progress=100, result=result)
        return {"success": True, "task_id": task["task_id"], "result": result}
    except Exception as e:
        update_task(task["task_id"], status=STATUS_FAILED, error=str(e))
        logger.error(f"組合回測失敗: {e}")
        raise HTTPException(500, str(e))


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


@app.post("/api/watchlist/add")
async def add_to_watchlist(code: str, name: str = ""):
    """添加股票到監控列表"""
    if code in settings.alert_rules:
        return {"success": True, "message": f"{code} 已在監控列表"}
    settings.alert_rules[code] = {
        "name": name or code,
        "price_above": None,
        "price_below": None,
        "change_pct": 5.0,
    }
    if code not in settings.watchlist:
        settings.watchlist.append(code)
    return {"success": True, "message": f"{code} 已加入監控", "rules": settings.alert_rules}


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
    from src.core.task_manager import create_task, update_task, STATUS_COMPLETED, STATUS_FAILED

    if not code:
        raise HTTPException(400, "請提供股票代碼")

    # 任務去重
    task_params = {"code": code, "strategy": strategy, "train_days": train_days, "test_days": test_days}
    task = create_task("walkforward", task_params, title=f"Walk-Forward {code}/{strategy}")
    if task.get("is_duplicate"):
        return {"success": True, "task_id": task["task_id"], "is_duplicate": True,
                "message": "相同 Walk-Forward 正在執行中，請等待完成"}

    try:
        result = walk_forward(
            code=code, strategy_name=strategy,
            train_days=train_days, test_days=test_days, step_days=step_days,
            objective=objective, n_trials=n_trials,
        )
        update_task(task["task_id"], status=STATUS_COMPLETED, progress=100, result=result)
        return {"success": True, "task_id": task["task_id"], "result": result}
    except Exception as e:
        update_task(task["task_id"], status=STATUS_FAILED, error=str(e))
        logger.error(f"Walk-Forward 失敗: {e}")
        raise HTTPException(500, str(e))


# ====== 自動優化 ======

@app.post("/api/auto-optimize")
async def run_auto_optimize(body: dict = None):
    """自動參數優化（自動加入任務列表）"""
    from src.core.auto_optimize import auto_optimize_watchlist
    from src.core.task_manager import create_task, update_task, STATUS_COMPLETED, STATUS_FAILED

    if body is None:
        body = {}

    # 任務去重
    task_params = {"codes": body.get("codes"), "strategies": body.get("strategies"), "method": body.get("method", "optuna")}
    task = create_task("auto_optimize", task_params, title="全自動參數優化")
    if task.get("is_duplicate"):
        return {"success": True, "task_id": task["task_id"], "is_duplicate": True,
                "message": "全自動優化正在執行中，請等待完成"}

    try:
        result = auto_optimize_watchlist(
            codes=body.get("codes"),
            strategies=body.get("strategies"),
            method=body.get("method", "optuna"),
            n_trials=body.get("n_trials", 50),
            objective=body.get("objective", "sharpe"),
        )
        update_task(task["task_id"], status=STATUS_COMPLETED, progress=100, result=result)
        return {"success": True, "task_id": task["task_id"], "result": result}
    except Exception as e:
        update_task(task["task_id"], status=STATUS_FAILED, error=str(e))
        logger.error(f"自動優化失敗: {e}")
        raise HTTPException(500, str(e))


# ====== 調度器 ======

@app.get("/api/scheduler/jobs")
async def list_scheduler_jobs():
    """列出調度任務"""
    from src.core.scheduler import list_jobs
    return {"jobs": list_jobs()}


@app.post("/api/scheduler/enable")
async def enable_scheduler():
    """啟用每日報告"""
    from src.core.scheduler import start_scheduler, enable_daily_report
    start_scheduler()
    enable_daily_report()
    return {"success": True, "message": "每日報告已啟用 (15:30)"}


@app.post("/api/scheduler/disable")
async def disable_scheduler():
    """禁用每日報告"""
    from src.core.scheduler import disable_daily_report
    disable_daily_report()
    return {"success": True, "message": "每日報告已禁用"}


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


# ====== 任務管理 ======

@app.get("/api/tasks")
async def list_tasks_api(task_type: str = None, status: str = None, limit: int = 50):
    """獲取任務列表"""
    from src.core.task_manager import get_tasks, get_task_stats
    tasks = get_tasks(task_type=task_type, status=status, limit=limit)
    stats = get_task_stats()
    return {"tasks": tasks, "stats": stats}


@app.get("/api/tasks/{task_id}")
async def get_task_api(task_id: str):
    """獲取單個任務詳情"""
    from src.core.task_manager import get_task
    task = get_task(task_id)
    if not task:
        raise HTTPException(404, "任務不存在")
    return {"task": task}


@app.post("/api/tasks/{task_id}/cancel")
async def cancel_task_api(task_id: str):
    """取消任務"""
    from src.core.task_manager import cancel_task
    success = cancel_task(task_id)
    if not success:
        raise HTTPException(400, "任務無法取消（可能已完成或不存在）")
    return {"success": True, "message": "任務已取消"}


@app.post("/api/tasks/cleanup")
async def cleanup_tasks_api(timeout_sec: int = 3600):
    """清理超時任務"""
    from src.core.task_manager import cleanup_stale_tasks
    cleaned = cleanup_stale_tasks(timeout_sec)
    return {"success": True, "cleaned": cleaned}


@app.delete("/api/tasks/{task_id}")
async def delete_task_api(task_id: str):
    """刪除已完成/失敗/取消的任務"""
    from src.core.task_manager import delete_task
    ok = delete_task(task_id)
    if not ok:
        raise HTTPException(status_code=404, detail="任務不存在或仍在運行中，請先取消")
    return {"success": True}


@app.get("/api/tasks/{task_id}/full")
async def get_task_full_api(task_id: str):
    """獲取任務完整信息（含 params 和 result）"""
    from src.core.task_manager import get_task_full
    task = get_task_full(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任務不存在")
    # 移除內部字段
    task.pop("last_accessed", None)
    return {"task": task}


# ====== 配置 ======

@app.get("/api/config")
async def get_config():
    """獲取當前配置"""
    return {
        "watchlist": settings.watchlist,
        "poll_interval": settings.poll_interval_sec,
        "alert_cooldown": settings.alert_cooldown_sec,
        "backtest_cash": settings.backtest_cash,
        "backtest_commission": settings.backtest_commission,
        "strategy_params": settings.strategy_params,
        "alert_rules": settings.alert_rules,
        "portfolio_presets": settings.portfolio_presets,
    }


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

    try:
        result = param_heatmap(
            code=code, strategy_name=strategy,
            param_x=param_x, param_y=param_y,
            grid_size=grid_size, objective=objective,
        )
        return {"success": True, "result": result}
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
    defaults = _get_default_params(strategy)
    grid = PARAM_GRIDS.get(strategy, {})

    return {
        "strategy": strategy,
        "params": list(defaults.keys()),
        "defaults": defaults,
        "grid_values": grid,
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

@app.get("/api/signals/current")
async def get_current_signals():
    """獲取所有監控股票的當前信號"""
    from src.core.signals import SignalEngine, compute_and_push_signals

    try:
        engine = SignalEngine()
        engine.update_weights_from_backtest()
        signals_data = compute_and_push_signals(engine, settings.watchlist)
        return {"success": True, "signals": signals_data, "total": len(signals_data)}
    except Exception as e:
        logger.error(f"獲取當前信號失敗: {e}")
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
    from src.core.backtest import STRATEGIES, STRATEGY_NAMES
    from src.core.strategy_base import list_user_strategies

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

    # 用戶策略
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
        }
    except Exception as e:
        logger.error(f"獲取排行榜失敗: {e}")
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


# ====== WebSocket 實時推送 ======

class ConnectionManager:
    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)
        logger.info(f"WebSocket 連接: {len(self.active)} 個客戶端")

    def disconnect(self, ws: WebSocket):
        self.active.remove(ws)
        logger.info(f"WebSocket 斷開: {len(self.active)} 個客戶端")

    async def broadcast(self, data: dict):
        import json
        text = json.dumps(data, ensure_ascii=False)
        for ws in self.active[:]:
            try:
                await ws.send_text(text)
            except Exception:
                self.active.remove(ws)


manager = ConnectionManager()


async def _ws_realtime_push():
    """後台任務: 每隔一段時間向所有 WebSocket 客戶端推送行情 + 信號"""
    import asyncio
    from src.core.realtime import fetch_realtime
    from src.core.signals import SignalEngine, compute_and_push_signals
    signal_engine = SignalEngine()
    # 用最近回測結果更新策略權重
    try:
        signal_engine.update_weights_from_backtest()
    except Exception:
        pass
    signal_push_counter = 0
    signal_push_interval = 6  # 每 6 個 poll 週期推送一次信號（約 60 秒）
    while True:
        await asyncio.sleep(settings.poll_interval_sec)
        if not manager.active:
            continue
        if not _is_trading_time():
            continue
        try:
            df = fetch_realtime(settings.watchlist)
            if not df.empty:
                await manager.broadcast({
                    "type": "quotes",
                    "data": df.to_dict(orient="records"),
                    "timestamp": datetime.now().isoformat(),
                })
        except Exception as e:
            logger.debug(f"WebSocket 推送失敗: {e}")

        # 每隔 signal_push_interval 次推送一次信號
        signal_push_counter += 1
        if signal_push_counter >= signal_push_interval:
            signal_push_counter = 0
            try:
                signals_data = compute_and_push_signals(signal_engine, settings.watchlist)
                if signals_data:
                    await manager.broadcast({
                        "type": "signals",
                        "data": signals_data,
                        "timestamp": datetime.now().isoformat(),
                    })
            except Exception as e:
                logger.debug(f"WebSocket 信號推送失敗: {e}")


def _is_trading_time() -> bool:
    """判斷是否在交易時段"""
    now = datetime.now()
    if now.weekday() >= 5:
        return False
    t = now.hour * 100 + now.minute
    return (915 <= t <= 1130) or (1300 <= t <= 1500)


# WebSocket 推送已在 lifespan 中啟動，此處不再使用已廢棄的 @app.on_event


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket, token: str = None):
    """WebSocket 實時行情推送（支持 ?token=xxx 認證）"""
    # 認證邏輯：ws_auth_required=True 時強制要求 token
    if settings.ws_auth_required:
        if not token:
            await ws.close(code=4001, reason="需要認證：請在 URL 中添加 ?token=xxx")
            logger.warning("WebSocket 連接被拒絕：缺少 token（生產環境強制認證）")
            return
        from src.core.auth import verify_token
        payload = verify_token(token)
        if not payload:
            await ws.close(code=4001, reason="Token 無效或已過期")
            logger.warning("WebSocket 連接被拒絕：token 無效")
            return
    else:
        # 開發環境：可選認證
        if token:
            from src.core.auth import verify_token
            payload = verify_token(token)
            if not payload:
                await ws.close(code=4001, reason="Token 無效或已過期")
                return
    await manager.connect(ws)
    try:
        while True:
            data = await ws.receive_text()
            if data == "ping":
                await ws.send_text('{"type":"pong"}')
    except WebSocketDisconnect:
        manager.disconnect(ws)


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
        return {"sectors": sectors, "total": len(sectors), "type": sector_type}
    except Exception as e:
        logger.error(f"獲取板塊列表失敗: {e}")
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
        flows = get_north_flow(days=days)
        return {"flows": flows, "total": len(flows)}
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
