"""
板塊數據模塊 — 行業板塊 + 概念板塊
使用 AKShare 接口獲取板塊列表、成分股、板塊漲跌排行
新增：快照存儲、板塊輪動、趨勢分析、資金流向、全景數據
"""
import akshare as ak
import pandas as pd
import time
import sqlite3
from datetime import datetime, timedelta
from src.core.db import get_conn
from src.utils.logger import logger

# 請求間隔（秒），防止被封
_RATE_LIMIT = 0.5
# 板塊列表內存緩存（秒），避免儀表盤輪詢反覆打東財
_SECTOR_LIST_CACHE_TTL = 300
_sector_list_cache: dict[str, tuple[float, list[dict]]] = {}
# 連線失敗日誌節流（秒）
_SECTOR_FAIL_LOG_INTERVAL = 120
_last_sector_fail_log: dict[str, float] = {}


def _rate_sleep():
    """限速等待"""
    time.sleep(_RATE_LIMIT)


def _is_connection_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    needles = (
        "connection aborted",
        "remotedisconnected",
        "remote end closed",
        "connection reset",
        "timed out",
        "timeout",
        "connection refused",
    )
    return any(n in msg for n in needles)


def _log_sector_fail(sector_type: str, message: str, level: str = "warning") -> None:
    """同一類型板塊在短時間內只打一次 WARN，避免日誌刷屏"""
    now = time.time()
    last = _last_sector_fail_log.get(sector_type, 0)
    if level == "warning" and now - last < _SECTOR_FAIL_LOG_INTERVAL:
        logger.debug(message)
        return
    if level == "warning":
        _last_sector_fail_log[sector_type] = now
    getattr(logger, level)(message)


def _cache_get_sector_list(sector_type: str) -> list[dict] | None:
    hit = _sector_list_cache.get(sector_type)
    if not hit:
        return None
    ts, data = hit
    if time.time() - ts > _SECTOR_LIST_CACHE_TTL:
        _sector_list_cache.pop(sector_type, None)
        return None
    return data


def _cache_set_sector_list(sector_type: str, sectors: list[dict]) -> None:
    if sectors:
        _sector_list_cache[sector_type] = (time.time(), sectors)


def _requests_session():
    """帶重試的 HTTP Session（東財直連用）"""
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry

    session = requests.Session()
    retry = Retry(
        total=2,
        connect=2,
        read=2,
        backoff_factor=0.8,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET"]),
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=4, pool_maxsize=4)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


# ============================================================
# 數據庫表定義
# ============================================================

DDL_SECTOR = """
CREATE TABLE IF NOT EXISTS sector_data (
    sector_name TEXT NOT NULL,
    sector_type TEXT NOT NULL,  -- 'industry' 或 'concept'
    code        TEXT NOT NULL,
    stock_name  TEXT,
    update_date TEXT,
    PRIMARY KEY (sector_name, sector_type, code)
)
"""

DDL_SECTOR_SNAPSHOT = """
CREATE TABLE IF NOT EXISTS sector_snapshot (
    sector_name      TEXT NOT NULL,
    sector_type      TEXT NOT NULL,
    change_pct       REAL,
    amount           REAL,
    rise_count       INTEGER,
    fall_count       INTEGER,
    leader           TEXT,
    leader_change_pct REAL,
    snapshot_date    TEXT NOT NULL,
    PRIMARY KEY (sector_name, sector_type, snapshot_date)
)
"""


_sector_tables_ready = False


def init_sector_table():
    """初始化板塊數據表 + 快照表"""
    global _sector_tables_ready
    with get_conn() as conn:
        conn.execute(DDL_SECTOR)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sector_name ON sector_data(sector_name)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sector_code ON sector_data(code)")
        conn.execute(DDL_SECTOR_SNAPSHOT)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_snapshot_date ON sector_snapshot(snapshot_date)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_snapshot_type ON sector_snapshot(sector_type)")
        conn.commit()
    if not _sector_tables_ready:
        logger.debug("板塊數據表 + 快照表就緒")
        _sector_tables_ready = True


# ============================================================
# 行業板塊（原有）
# ============================================================

def _load_sectors_from_snapshot(sector_type: str = "industry") -> list[dict]:
    """AKShare 不可用時，從本地快照讀取最近一次板塊數據"""
    init_sector_table()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT snapshot_date FROM sector_snapshot WHERE sector_type = ? "
            "ORDER BY snapshot_date DESC LIMIT 1",
            (sector_type,),
        ).fetchone()
        if not row:
            return []
        snap_date = row[0]
        rows = conn.execute(
            """SELECT sector_name, change_pct, amount, rise_count, fall_count,
                      leader, leader_change_pct
               FROM sector_snapshot
               WHERE sector_type = ? AND snapshot_date = ?""",
            (sector_type, snap_date),
        ).fetchall()

    result = []
    for r in rows:
        result.append({
            "name": r[0],
            "code": "",
            "change_pct": float(r[1] or 0),
            "turnover": 0,
            "amount": float(r[2] or 0),
            "stock_count": int((r[3] or 0) + (r[4] or 0)),
            "rise_count": int(r[3] or 0),
            "fall_count": int(r[4] or 0),
            "leader": str(r[5] or ""),
            "leader_change_pct": float(r[6] or 0),
            "type": sector_type,
            "from_snapshot": True,
            "snapshot_date": snap_date,
        })
    return result


_EM_HOSTS = (
    "17.push2.eastmoney.com",
    "63.push2.eastmoney.com",
    "82.push2.eastmoney.com",
    "push2.eastmoney.com",
)


def _fetch_sector_list_em_http(sector_type: str = "industry") -> list[dict]:
    """東財 push2 直連（AKShare 斷線時的備選，多節點重試）"""
    try:
        session = _requests_session()
    except ImportError:
        return []

    fs = "m:90+t:3" if sector_type == "concept" else "m:90+t:2"
    params = {
        "pn": "1",
        "pz": "500",
        "po": "1",
        "np": "1",
        "ut": "bd1d9ddb04089700cf9c27f6c7b1b98",
        "fltt": "2",
        "invt": "2",
        "fid": "f3",
        "fs": fs,
        "fields": "f12,f14,f3,f8,f20,f104,f105,f128,f136,f140",
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://quote.eastmoney.com/",
    }

    last_err = None
    for host in _EM_HOSTS:
        url = f"https://{host}/api/qt/clist/get"
        try:
            resp = session.get(url, params=params, headers=headers, timeout=(8, 25))
            resp.raise_for_status()
            payload = resp.json()
            diff = (payload.get("data") or {}).get("diff") or []
            if not diff:
                continue

            result = []
            for item in diff:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("f14") or "").strip()
                if not name:
                    continue
                change_raw = item.get("f3")
                change_pct = float(change_raw) / 100.0 if change_raw is not None else 0.0
                result.append({
                    "name": name,
                    "code": str(item.get("f12") or ""),
                    "change_pct": change_pct,
                    "turnover": float(item.get("f8") or 0),
                    "amount": float(item.get("f20") or 0),
                    "stock_count": int((item.get("f104") or 0) + (item.get("f105") or 0)),
                    "rise_count": int(item.get("f104") or 0),
                    "fall_count": int(item.get("f105") or 0),
                    "leader": str(item.get("f128") or item.get("f140") or ""),
                    "leader_change_pct": float(item.get("f136") or 0) / 100.0,
                    "type": sector_type,
                    "source": "eastmoney_http",
                })

            _rate_sleep()
            logger.info(f"東財 HTTP({host}) 獲取{sector_type}板塊: {len(result)} 條")
            return result
        except Exception as e:
            last_err = e
            logger.debug(f"東財 {host} 獲取{sector_type}板塊失敗: {e}")

    if last_err:
        _log_sector_fail(sector_type, f"東財 HTTP 獲取{sector_type}板塊失敗: {last_err}")
    return []


def _load_sectors_from_local_kline(sector_type: str = "industry") -> list[dict]:
    """用 sector_data 成分股 + 本地最近兩日 K 線估算板塊漲跌（完全離線兜底）"""
    from src.core.db import load_daily_kline

    init_sector_table()
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT DISTINCT sector_name FROM sector_data WHERE sector_type = ?",
            (sector_type,),
        ).fetchall()
    if not rows:
        return []

    result = []
    for (sector_name,) in rows:
        codes = get_cached_sector_stocks(sector_name)
        if not codes:
            continue
        changes = []
        leader_code, leader_chg = "", 0.0
        for code in codes[:80]:
            df = load_daily_kline(code)
            if df is None or len(df) < 2:
                continue
            c0, c1 = float(df.iloc[-2]["close"]), float(df.iloc[-1]["close"])
            if c0 <= 0:
                continue
            chg = (c1 / c0 - 1) * 100
            changes.append(chg)
            if chg > leader_chg:
                leader_chg = chg
                leader_code = code
        if not changes:
            continue
        avg = sum(changes) / len(changes)
        rise = sum(1 for c in changes if c > 0)
        fall = sum(1 for c in changes if c <= 0)
        result.append({
            "name": sector_name,
            "code": "",
            "change_pct": round(avg, 2),
            "turnover": 0,
            "amount": 0,
            "stock_count": len(changes),
            "rise_count": rise,
            "fall_count": fall,
            "leader": leader_code,
            "leader_change_pct": round(leader_chg, 2),
            "type": sector_type,
            "from_local_kline": True,
            "source": "local_kline",
        })

    result.sort(key=lambda x: x.get("change_pct", 0), reverse=True)
    if result:
        logger.info(f"本地 K 線估算{sector_type}板塊: {len(result)} 條")
    return result


def _fetch_sector_list_live(sector_type: str, retries: int = 2) -> list[dict]:
    last_err = None
    for attempt in range(retries):
        try:
            if sector_type == "concept":
                df = ak.stock_board_concept_name_em()
            else:
                df = ak.stock_board_industry_name_em()

            if df.empty:
                logger.warning(f"獲取{sector_type}板塊列表為空")
                return []

            result = []
            for _, row in df.iterrows():
                result.append({
                    "name": str(row.get("板块名称", row.get("板块名称", ""))),
                    "code": str(row.get("板块代码", row.get("板块代码", ""))),
                    "change_pct": float(row.get("涨跌幅", 0) or 0),
                    "turnover": float(row.get("换手率", 0) or 0),
                    "amount": float(row.get("总成交额", 0) or 0),
                    "stock_count": int(row.get("上涨家数", 0) or 0),
                    "rise_count": int(row.get("上涨家数", 0) or 0),
                    "fall_count": int(row.get("下跌家数", 0) or 0),
                    "leader": str(row.get("领涨股票", "")),
                    "leader_change_pct": float(row.get("领涨股票-涨跌幅", 0) or 0),
                    "type": sector_type,
                    "source": "akshare",
                })

            _rate_sleep()
            return result
        except Exception as e:
            last_err = e
            logger.debug(f"AKShare 獲取{sector_type}板塊失敗 ({attempt + 1}/{retries}): {e}")
            if _is_connection_error(e):
                break
            time.sleep(0.8 + attempt * 0.5)

    if last_err:
        _log_sector_fail(sector_type, f"AKShare 獲取{sector_type}板塊列表失敗: {last_err}")
    return []


def get_sector_list(sector_type: str = "industry") -> list[dict]:
    """
    獲取所有板塊列表
    
    Args:
        sector_type: 'industry' 行業板塊, 'concept' 概念板塊
    
    Returns:
        [{"name": "銀行", "code": "BK0475", ...}, ...]
    """
    cached = _cache_get_sector_list(sector_type)
    if cached is not None:
        return cached

    # 東財直連通常比 AKShare 包裝層更穩；連線錯誤時優先 HTTP
    sectors = _fetch_sector_list_em_http(sector_type)
    if not sectors:
        sectors = _fetch_sector_list_live(sector_type)
    if sectors:
        _cache_set_sector_list(sector_type, sectors)
        return sectors

    cached = _load_sectors_from_snapshot(sector_type)
    if cached:
        logger.info(
            f"使用板塊快照緩存: {sector_type}, {len(cached)} 條, "
            f"日期={cached[0].get('snapshot_date')}"
        )
        _cache_set_sector_list(sector_type, cached)
        return cached

    local = _load_sectors_from_local_kline(sector_type)
    if local:
        _cache_set_sector_list(sector_type, local)
    else:
        _log_sector_fail(
            sector_type,
            f"{sector_type}板塊實時與快照均不可用，請檢查網絡或稍後重試",
        )
    return local


def get_sector_stocks(sector_name: str, sector_type: str = "industry") -> list[dict]:
    """
    獲取指定板塊的成分股
    
    Args:
        sector_name: 板塊名稱，如 "銀行"
        sector_type: 'industry' 或 'concept'
    
    Returns:
        [{"code": "000001", "name": "平安銀行", ...}, ...]
    """
    try:
        if sector_type == "concept":
            df = ak.stock_board_concept_cons_em(symbol=sector_name)
        else:
            df = ak.stock_board_industry_cons_em(symbol=sector_name)
        
        if df.empty:
            logger.warning(f"板塊 {sector_name} 無成分股數據")
            return []
        
        result = []
        for _, row in df.iterrows():
            result.append({
                "code": str(row.get("代码", "")),
                "name": str(row.get("名称", "")),
                "price": float(row.get("最新价", 0) or 0),
                "change_pct": float(row.get("涨跌幅", 0) or 0),
                "volume": float(row.get("成交量", 0) or 0),
                "amount": float(row.get("成交额", 0) or 0),
                "turnover": float(row.get("换手率", 0) or 0),
            })
        
        # 存入數據庫
        _save_sector_stocks(sector_name, sector_type, result)
        _rate_sleep()
        return result
        
    except Exception as e:
        logger.error(f"獲取板塊 {sector_name} 成分股失敗: {e}")
        return []


def _save_sector_stocks(sector_name: str, sector_type: str, stocks: list[dict]):
    """保存板塊成分股到數據庫"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    records = []
    for s in stocks:
        records.append((
            sector_name,
            sector_type,
            s.get("code", ""),
            s.get("name", ""),
            now,
        ))
    
    if not records:
        return
    
    with get_conn() as conn:
        conn.executemany(
            """INSERT OR REPLACE INTO sector_data
               (sector_name, sector_type, code, stock_name, update_date)
               VALUES (?, ?, ?, ?, ?)""",
            records
        )
    logger.debug(f"保存板塊 {sector_name} 成分股: {len(records)} 只")


def get_sector_performance(sector_type: str = "industry", top_n: int = 20) -> list[dict]:
    """
    獲取板塊漲跌排行
    
    Args:
        sector_type: 'industry' 或 'concept'
        top_n: 返回前 N 個板塊
    
    Returns:
        按漲跌幅排序的板塊列表
    """
    sectors = get_sector_list(sector_type)
    if not sectors:
        return []
    
    # 按漲跌幅排序
    sectors.sort(key=lambda x: x.get("change_pct", 0), reverse=True)
    return sectors[:top_n]


def get_cached_sector_stocks(sector_name: str) -> list[str]:
    """從數據庫讀取板塊成分股代碼（緩存）"""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT DISTINCT code FROM sector_data WHERE sector_name = ?",
            (sector_name,)
        ).fetchall()
    return [r[0] for r in rows]


# ============================================================
# 板塊快照 — 每日存儲板塊漲跌數據
# ============================================================

def save_sector_snapshot(sector_type: str = "industry") -> int:
    """
    保存當日板塊快照到 sector_snapshot 表。
    同一天同一板塊只存一條（REPLACE）。
    
    Args:
        sector_type: 'industry' 或 'concept'
    
    Returns:
        保存的記錄數
    """
    sectors = get_sector_list(sector_type)
    if not sectors:
        logger.warning(f"save_sector_snapshot: {sector_type} 無數據")
        return 0

    today = datetime.now().strftime("%Y-%m-%d")
    records = []
    for s in sectors:
        records.append((
            s.get("name", ""),
            sector_type,
            s.get("change_pct", 0),
            s.get("amount", 0),
            s.get("rise_count", 0),
            s.get("fall_count", 0),
            s.get("leader", ""),
            s.get("leader_change_pct", 0),
            today,
        ))

    with get_conn() as conn:
        conn.executemany(
            """INSERT OR REPLACE INTO sector_snapshot
               (sector_name, sector_type, change_pct, amount, rise_count, fall_count,
                leader, leader_change_pct, snapshot_date)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            records,
        )
        conn.commit()

    logger.info(f"保存 {sector_type} 板塊快照: {len(records)} 個板塊, 日期={today}")
    return len(records)


# ============================================================
# 板塊輪動分析
# ============================================================

def get_sector_rotation(days: int = 10) -> list[dict]:
    """
    板塊輪動分析：比較今天和 N 天前的排名變化。
    返回排名上升最多（新興熱點）和下降最多（退潮）的板塊。
    """
    with get_conn() as conn:
        # 獲取最近有數據的不同日期（降序）
        rows = conn.execute(
            "SELECT DISTINCT snapshot_date FROM sector_snapshot ORDER BY snapshot_date DESC LIMIT ?",
            (days + 1,)
        ).fetchall()

    dates = [r[0] for r in rows]
    if len(dates) < 2:
        logger.warning("板塊輪動：需要至少 2 天數據")
        return []

    latest_date = dates[0]
    # 取 days 天前的數據，如果不足則取最早的一天
    prev_date = dates[min(days, len(dates) - 1)]

    with get_conn() as conn:
        # 今日數據
        today_rows = conn.execute(
            "SELECT sector_name, change_pct, amount FROM sector_snapshot WHERE snapshot_date = ? ORDER BY change_pct DESC",
            (latest_date,),
        ).fetchall()
        # 歷史數據
        prev_rows = conn.execute(
            "SELECT sector_name, change_pct, amount FROM sector_snapshot WHERE snapshot_date = ? ORDER BY change_pct DESC",
            (prev_date,),
        ).fetchall()

    # 建立排名映射
    today_ranks = {r[0]: (i + 1, r[1], r[2]) for i, r in enumerate(today_rows)}
    prev_ranks = {r[0]: (i + 1, r[1], r[2]) for i, r in enumerate(prev_rows)}

    result = []
    for name, (cur_rank, cur_change, cur_amount) in today_ranks.items():
        if name in prev_ranks:
            prev_rank = prev_ranks[name][0]
            rank_change = prev_rank - cur_rank  # 正數=排名上升
            avg_change = round((cur_change + prev_ranks[name][1]) / 2, 2)
            result.append({
                "name": name,
                "rank_change": rank_change,
                "current_rank": cur_rank,
                "prev_rank": prev_rank,
                "avg_change_pct": avg_change,
                "amount": cur_amount,
            })

    # 按排名變化排序
    result.sort(key=lambda x: x["rank_change"], reverse=True)
    return result


# ============================================================
# 板塊歷史趨勢
# ============================================================

def get_sector_trend(sector_name: str, days: int = 20) -> list[dict]:
    """
    從 sector_snapshot 讀取指定板塊最近 N 天的漲跌數據。
    """
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT snapshot_date, change_pct FROM sector_snapshot
               WHERE sector_name = ?
               ORDER BY snapshot_date DESC LIMIT ?""",
            (sector_name, days),
        ).fetchall()

    if not rows:
        return []

    # 反轉為時間正序
    rows = rows[::-1]

    # 計算每天的排名
    dates = [r[0] for r in rows]
    result = []
    for date, change_pct in rows:
        # 查該天所有板塊排名
        with get_conn() as conn:
            all_sectors = conn.execute(
                "SELECT sector_name, change_pct FROM sector_snapshot WHERE snapshot_date = ? ORDER BY change_pct DESC",
                (date,),
            ).fetchall()
        rank_map = {s[0]: i + 1 for i, s in enumerate(all_sectors)}
        result.append({
            "date": date,
            "change_pct": round(change_pct, 2) if change_pct else 0,
            "rank": rank_map.get(sector_name, 0),
        })

    return result


# ============================================================
# 板塊資金流向
# ============================================================

def get_sector_capital_flow(sector_name: str = None) -> list[dict]:
    """
    板塊資金流向 — 使用 AKShare 獲取板塊資金流向排名。
    如果指定 sector_name，只返回該板塊的數據。
    """
    try:
        df = ak.stock_sector_fund_flow_rank(indicator="今日")
        if df is None or df.empty:
            logger.warning("板塊資金流向數據為空")
            return []

        result = []
        for _, row in df.iterrows():
            item = {
                "name": str(row.get("名称", "")),
                "change_pct": float(row.get("今日涨跌幅", 0) or 0),
                "main_net": float(row.get("主力净流入-净额", 0) or 0),
                "main_net_pct": float(row.get("主力净流入-净占比", 0) or 0),
                "super_large_net": float(row.get("超大单净流入-净额", 0) or 0),
                "large_net": float(row.get("大单净流入-净额", 0) or 0),
                "medium_net": float(row.get("中单净流入-净额", 0) or 0),
                "small_net": float(row.get("小单净流入-净額", 0) or 0),
            }
            if sector_name and item["name"] != sector_name:
                continue
            result.append(item)

        _rate_sleep()
        return result

    except Exception as e:
        logger.error(f"獲取板塊資金流向失敗: {e}")
        return []


# ============================================================
# 板塊全景數據（熱力圖）
# ============================================================

def get_sector_heatmap_data(sector_type: str = "industry") -> list[dict]:
    """
    返回所有板塊的漲跌幅和成交額，用於前端矩陣圖。
    格式：[{"name": "銀行", "change_pct": 1.2, "amount": 5.6e9, "stock_count": 42}, ...]
    """
    sectors = get_sector_list(sector_type)
    if not sectors:
        return []

    result = []
    for s in sectors:
        result.append({
            "name": s.get("name", ""),
            "change_pct": s.get("change_pct", 0),
            "amount": s.get("amount", 0),
            "stock_count": s.get("rise_count", 0) + s.get("fall_count", 0),
            "rise_count": s.get("rise_count", 0),
            "fall_count": s.get("fall_count", 0),
            "leader": s.get("leader", ""),
            "leader_change_pct": s.get("leader_change_pct", 0),
        })

    return result
