"""
統一數據源管理模塊

集中管理所有數據源的配置、健康檢查、自動降級邏輯。
每個數據源統一接口：fetch_quote(symbol) / fetch_history(symbol, start)
"""

import os
import random
import time
from typing import Optional

import requests

from src.utils.logger import logger

# ── UA 池（隨機指紋） ────────────────────────────────────────

_UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0",
]

_ACCEPT_LANGS = [
    "zh-CN,zh;q=0.9,en;q=0.8",
    "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    "en-US,en;q=0.9,zh-CN;q=0.8",
    "en-GB,en;q=0.9",
]

_PROXY_URL = os.environ.get("SQ_PROXY_URL", "").strip()
_PROXY_POOL_URL = os.environ.get("SQ_PROXY_POOL_URL", "").strip()


class DataSource:
    """數據源基類"""

    def __init__(
        self,
        name: str,
        priority: int,
        rate_limit: float = 0.5,
        timeout: int = 10,
        daily_limit: int = 0,
    ):
        self.name = name
        self.priority = priority  # 越小越優先
        self.rate_limit = rate_limit  # 每次請求最小間隔（秒）
        self.timeout = timeout
        self.daily_limit = daily_limit  # 0=無限制
        self._last_request = 0.0
        self._daily_count = 0
        self._daily_reset = 0.0
        self._fail_count = 0
        self._circuit_open_until = 0.0  # 熔斷恢復時間
        # 可用性打分：用於「首次取得數據」時的動態排隊（越高越優先）
        # 以 priority 作為初始偏好，但允許隨成功/404/失敗動態調整。
        self._score = max(0.0, 100.0 - float(priority) * 2.0)
        self._score_updated_at = 0.0

    @property
    def available(self) -> bool:
        """是否可用（未熔斷 + 未超限）"""
        now = time.time()
        # 熔斷中
        if now < self._circuit_open_until:
            return False
        # 每日限額
        if self.daily_limit > 0 and self._daily_count >= self.daily_limit:
            return False
        return True

    @property
    def score(self) -> float:
        return float(self._score or 0.0)

    def _bump_score(self, delta: float) -> None:
        now = time.time()
        self._score = max(0.0, min(200.0, float(self._score or 0.0) + float(delta)))
        self._score_updated_at = now

    def record_success(self):
        """記錄成功，並解除熔斷"""
        self._fail_count = 0
        self._circuit_open_until = 0.0
        self._bump_score(+2.0)

    def record_http_404(self):
        """記錄 404：代表可達但該標的不支援/不存在，應降分但不熔斷。"""
        self._bump_score(-3.0)

    def record_http_client_error(self, status_code: int):
        """記錄 4xx（非 404）：降分，避免過度熔斷。"""
        sc = int(status_code or 400)
        if sc == 404:
            self.record_http_404()
            return
        self._bump_score(-5.0)

    def record_soft_failure(self):
        """記錄軟失敗（例如返回 None）：小幅降分，不立即熔斷。"""
        self._bump_score(-1.0)

    def record_failure(self):
        """記錄失敗，連續 5 次熔斷 5 分鐘"""
        self._fail_count += 1
        self._bump_score(-8.0)
        if self._fail_count >= 5:
            self._circuit_open_until = time.time() + 300
            logger.warning(
                f"數據源 {self.name} 連續失敗 {self._fail_count} 次，熔斷 5 分鐘"
            )

    def throttle(self):
        """限流：確保請求間隔 + 隨機抖動（±30%），降低被封風險"""
        import random

        now = time.time()
        elapsed = now - self._last_request
        jitter = self.rate_limit * random.uniform(-0.3, 0.3)
        target_interval = max(0.1, self.rate_limit + jitter)
        if elapsed < target_interval:
            time.sleep(target_interval - elapsed)
        self._last_request = time.time()
        self._daily_count += 1

    def reset_daily(self):
        """重置每日計數"""
        self._daily_count = 0


# ============================================================
# 全局 HTTP Session 池
# ============================================================
_session_pool: dict[str, requests.Session] = {}


def _apply_proxy(session: requests.Session) -> None:
    """為 Session 配置代理（單 proxy 或 proxy pool）。"""
    if _PROXY_URL:
        session.proxies = {"http": _PROXY_URL, "https": _PROXY_URL}
        return
    if _PROXY_POOL_URL:
        try:
            resp = requests.get(_PROXY_POOL_URL, timeout=5)
            resp.raise_for_status()
            proxy = resp.text.strip()
            if proxy:
                session.proxies = {"http": proxy, "https": proxy}
        except Exception as e:
            logger.debug(f"代理池 { _PROXY_POOL_URL} 獲取失敗: {e}")


def _get_session(name: str, headers: dict = None) -> requests.Session:
    """獲取或創建共享 Session（隨機 UA + 可選代理）。"""
    if name not in _session_pool:
        s = requests.Session()
        s.headers.update(
            headers
            or {
                "User-Agent": random.choice(_UA_POOL),
                "Accept-Language": random.choice(_ACCEPT_LANGS),
            }
        )
        _apply_proxy(s)
        _session_pool[name] = s
    return _session_pool[name]


def get_session(name: str = "default") -> requests.Session:
    """公開接口：獲取共享 Session"""
    return _get_session(name)


# ============================================================
# 數據源註冊表
# ============================================================
_registry: dict[str, list[DataSource]] = {}


def register(category: str, source: DataSource):
    """註冊數據源到指定類別"""
    if category not in _registry:
        _registry[category] = []
    _registry[category].append(source)
    _registry[category].sort(key=lambda s: s.priority)


def get_sources(category: str) -> list[DataSource]:
    """獲取指定類別的所有可用數據源（按優先級排序）"""
    sources = _registry.get(category, [])
    available = [s for s in sources if s.available]
    # 動態排隊：分數高者優先；同分時按 priority（越小越前）
    available.sort(key=lambda s: (-float(getattr(s, "score", 0.0)), s.priority))
    return available


def _find_source(category: str, name: str) -> Optional[DataSource]:
    nm = str(name or "").strip()
    if not nm:
        return None
    for s in _registry.get(category, []) or []:
        if s.name == nm:
            return s
    return None


def record_outcome(
    category: str, source_name: str, *, ok: bool, status_code: int | None = None
) -> None:
    """
    供非 execute_with_fallback 路徑回報結果：
    - ok=True：加分
    - status_code=404：減分（不熔斷）
    - 其餘 ok=False：減分 + 記一次失敗（可能熔斷）
    """
    s = _find_source(category, source_name)
    if not s:
        return
    if ok:
        s.record_success()
        return
    sc = int(status_code or 0)
    if sc == 404:
        s.record_http_404()
        return
    if 400 <= sc < 500:
        s.record_http_client_error(sc)
        return
    s.record_failure()


def get_all_sources() -> dict[str, list[dict]]:
    """獲取所有已註冊數據源的狀態"""
    result = {}
    for cat, sources in _registry.items():
        result[cat] = []
        for s in sources:
            result[cat].append(
                {
                    "name": s.name,
                    "priority": s.priority,
                    "available": s.available,
                    "score": getattr(s, "score", 0.0),
                    "fail_count": s._fail_count,
                    "daily_count": s._daily_count,
                    "daily_limit": s.daily_limit,
                    "rate_limit": s.rate_limit,
                }
            )
    return result


# ============================================================
# 通用降級執行器
# ============================================================
_FETCH_HANDLERS: dict[str, dict[str, object]] = {}
_last_fetch_source: str = ""


def register_fetch_handler(category: str, source_name: str, handler: object) -> None:
    """為指定類別的數據源綁定 fetch 適配器（需實作 fetch_history 等方法）。"""
    _FETCH_HANDLERS.setdefault(category, {})[source_name] = handler


def get_last_fetch_source() -> str:
    """execute_with_fallback 最近一次成功命中的 source slug（由適配器設定）。"""
    return _last_fetch_source


def execute_with_fallback(category: str, func_name: str, *args, **kwargs):
    """
    通用降級執行器：按優先級嘗試數據源。

    優先使用 register_fetch_handler 綁定的適配器，否則回退到 DataSource 自身方法。
    返回第一個成功的結果。
    """
    global _last_fetch_source
    sources = get_sources(category)
    if not sources:
        logger.error(f"無可用數據源: {category}")
        return None

    last_error = None
    for source in sources:
        handler = _FETCH_HANDLERS.get(category, {}).get(source.name, source)
        func = getattr(handler, func_name, None)
        if not func:
            continue
        try:
            source.throttle()
            t0 = time.time()
            result = func(*args, **kwargs)
            elapsed_ms = (time.time() - t0) * 1000.0
            try:
                from src.core.auto_kline_fetch import source_slug
                from src.core.pipeline_observability import record_fetch_latency

                record_fetch_latency(source_slug(source.name), elapsed_ms)
            except Exception:
                pass
            if result is not None:
                source.record_success()
                try:
                    from src.core.auto_kline_fetch import source_slug

                    _last_fetch_source = source_slug(source.name)
                except Exception:
                    _last_fetch_source = source.name
                return result
            source.record_soft_failure()
        except Exception as e:
            # requests 的 HTTPError：可根據 status code 做更細緻打分（404 只降分不熔斷）
            if isinstance(e, requests.HTTPError) and getattr(e, "response", None) is not None:
                try:
                    sc = int(e.response.status_code)
                except Exception:
                    sc = 0
                if sc == 404:
                    source.record_http_404()
                    last_error = e
                    logger.debug(f"{source.name}.{func_name} 404: {e}")
                    continue
                if 400 <= sc < 500:
                    source.record_http_client_error(sc)
                    last_error = e
                    logger.debug(f"{source.name}.{func_name} HTTP {sc}: {e}")
                    continue
                source.record_failure()
            else:
                source.record_failure()
            last_error = e
            logger.debug(f"{source.name}.{func_name} 失敗: {e}")

    _last_fetch_source = ""
    if last_error:
        logger.warning(f"所有 {category} 數據源均失敗: {last_error}")
    return None


# ============================================================
# 健康檢查
# ============================================================
def health_check() -> dict:
    """檢查所有數據源健康狀態"""
    result = {}
    for cat, sources in _registry.items():
        available = sum(1 for s in sources if s.available)
        total = len(sources)
        result[cat] = {
            "available": available,
            "total": total,
            "status": "ok" if available > 0 else "degraded",
            "sources": [
                {
                    "name": s.name,
                    "ok": s.available,
                    "fails": s._fail_count,
                    "calls_today": s._daily_count,
                }
                for s in sources
            ],
        }
    _enrich_ib_health(result)
    return result


def _enrich_ib_health(result: dict) -> None:
    """將 dashboard_quote 中的 IB 與實際 TWS 連線狀態對齊。"""
    try:
        from src.core.ib_data import ib_status

        ib = ib_status(probe=False)
    except Exception:
        return

    cat = result.get("dashboard_quote")
    if not cat:
        return

    for row in cat.get("sources", []):
        if row.get("name") != "Interactive Brokers":
            continue
        if not ib.get("enabled"):
            row["ok"] = False
            row["ib"] = ib
            continue
        if not ib.get("library"):
            row["ok"] = False
            row["ib"] = ib
            continue
        row["ok"] = bool(ib.get("connected"))
        row["ib"] = ib

    connected = bool(ib.get("connected"))
    enabled = bool(ib.get("enabled"))
    if enabled:
        cat["ib"] = ib
        if connected:
            cat["available"] = max(cat.get("available", 0), 1)
            cat["status"] = "ok"
        elif cat.get("available", 0) <= 0:
            cat["status"] = "degraded"


# ============================================================
# 預定義數據源實例
# ============================================================

# --- A 股歷史 ---
register("a_share_history", DataSource("Yahoo Finance", priority=1, rate_limit=0.5))
register("a_share_history", DataSource("東方財富", priority=2, rate_limit=1.0))
register("a_share_history", DataSource("新浪", priority=3, rate_limit=1.0))
register("a_share_history", DataSource("網易", priority=4, rate_limit=1.0))
register("a_share_history", DataSource("騰訊", priority=5, rate_limit=1.0))
register("a_share_history", DataSource("HTTP直連", priority=6, rate_limit=0.5))

# --- A 股實時 ---
register("a_share_realtime", DataSource("Yahoo Finance", priority=1, rate_limit=0.3))
register("a_share_realtime", DataSource("東財盤口", priority=2, rate_limit=0.3))
register(
    "a_share_realtime",
    DataSource("東財全量", priority=3, rate_limit=0.5, daily_limit=5000),
)
register("a_share_realtime", DataSource("新浪", priority=4, rate_limit=0.2))
register("a_share_realtime", DataSource("騰訊", priority=5, rate_limit=0.2))

# --- 全球行情 ---
register("global_realtime", DataSource("Yahoo Finance", priority=1, rate_limit=0.3))
register("global_realtime", DataSource("新浪全球", priority=2, rate_limit=0.2))
register("global_realtime", DataSource("東財全球", priority=3, rate_limit=0.3))
register(
    "global_realtime",
    DataSource("Twelve Data", priority=4, rate_limit=8.0, daily_limit=800),
)

# --- 全球歷史 ---
register(
    "global_history", DataSource("Interactive Brokers", priority=0, rate_limit=0.5)
)
register("global_history", DataSource("Yahoo Finance", priority=1, rate_limit=0.5))
register(
    "global_history",
    DataSource("Twelve Data", priority=2, rate_limit=8.0, daily_limit=800),
)
register("global_history", DataSource("TradingView", priority=3, rate_limit=1.0))

# --- 儀表盤專用（TradingView Scanner + IB TWS） ---
register(
    "dashboard_quote", DataSource("Interactive Brokers", priority=1, rate_limit=0.5)
)
register("dashboard_quote", DataSource("TradingView", priority=2, rate_limit=0.8))
register("dashboard_quote", DataSource("Yahoo Finance", priority=3, rate_limit=0.5))

# --- 外匯 ---
register("forex_realtime", DataSource("Frankfurter", priority=1, rate_limit=0.5))
register("forex_realtime", DataSource("新浪外匯", priority=2, rate_limit=0.2))
register("forex_realtime", DataSource("東財外匯", priority=3, rate_limit=0.3))

# --- 外匯歷史 ---
register("forex_history", DataSource("Frankfurter", priority=1, rate_limit=0.5))
register(
    "forex_history",
    DataSource("Twelve Data", priority=2, rate_limit=8.0, daily_limit=800),
)

# --- 加密貨幣 ---
register("crypto_realtime", DataSource("Binance", priority=1, rate_limit=0.2))
register("crypto_realtime", DataSource("CoinGecko", priority=2, rate_limit=1.0))
register(
    "crypto_realtime",
    DataSource("Twelve Data", priority=3, rate_limit=8.0, daily_limit=800),
)

register("crypto_history", DataSource("Binance", priority=1, rate_limit=0.5))
register("crypto_history", DataSource("CoinGecko", priority=2, rate_limit=1.0))
register(
    "crypto_history",
    DataSource("Twelve Data", priority=3, rate_limit=8.0, daily_limit=800),
)

logger.info(
    f"📊 數據源管理器已初始化: {sum(len(v) for v in _registry.values())} 個數據源, {len(_registry)} 個類別"
)
