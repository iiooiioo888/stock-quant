"""
統一數據源管理模塊

集中管理所有數據源的配置、健康檢查、自動降級邏輯。
每個數據源統一接口：fetch_quote(symbol) / fetch_history(symbol, start)
"""
import requests
import time
from typing import Optional
from src.utils.logger import logger


class DataSource:
    """數據源基類"""

    def __init__(self, name: str, priority: int, rate_limit: float = 0.5,
                 timeout: int = 10, daily_limit: int = 0):
        self.name = name
        self.priority = priority          # 越小越優先
        self.rate_limit = rate_limit      # 每次請求最小間隔（秒）
        self.timeout = timeout
        self.daily_limit = daily_limit    # 0=無限制
        self._last_request = 0.0
        self._daily_count = 0
        self._daily_reset = 0.0
        self._fail_count = 0
        self._circuit_open_until = 0.0    # 熔斷恢復時間

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

    def record_success(self):
        """記錄成功（含可達但 404 等客戶端錯誤），並解除熔斷"""
        self._fail_count = 0
        self._circuit_open_until = 0.0

    def record_failure(self):
        """記錄失敗，連續 5 次熔斷 5 分鐘"""
        self._fail_count += 1
        if self._fail_count >= 5:
            self._circuit_open_until = time.time() + 300
            logger.warning(f"數據源 {self.name} 連續失敗 {self._fail_count} 次，熔斷 5 分鐘")

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


def _get_session(name: str, headers: dict = None) -> requests.Session:
    """獲取或創建共享 Session"""
    if name not in _session_pool:
        s = requests.Session()
        s.headers.update(headers or {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        })
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
    return [s for s in sources if s.available]


def get_all_sources() -> dict[str, list[dict]]:
    """獲取所有已註冊數據源的狀態"""
    result = {}
    for cat, sources in _registry.items():
        result[cat] = []
        for s in sources:
            result[cat].append({
                "name": s.name,
                "priority": s.priority,
                "available": s.available,
                "fail_count": s._fail_count,
                "daily_count": s._daily_count,
                "daily_limit": s.daily_limit,
                "rate_limit": s.rate_limit,
            })
    return result


# ============================================================
# 通用降級執行器
# ============================================================
def execute_with_fallback(category: str, func_name: str, *args, **kwargs):
    """
    通用降級執行器：按優先級嘗試數據源。

    每個數據源對象必須有對應的 func_name 方法。
    返回第一個成功的結果。
    """
    sources = get_sources(category)
    if not sources:
        logger.error(f"無可用數據源: {category}")
        return None

    last_error = None
    for source in sources:
        func = getattr(source, func_name, None)
        if not func:
            continue
        try:
            source.throttle()
            result = func(*args, **kwargs)
            if result is not None:
                source.record_success()
                return result
        except Exception as e:
            source.record_failure()
            last_error = e
            logger.debug(f"{source.name}.{func_name} 失敗: {e}")

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
    return result


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
register("a_share_realtime", DataSource("東財全量", priority=3, rate_limit=0.5, daily_limit=5000))
register("a_share_realtime", DataSource("新浪", priority=4, rate_limit=0.2))
register("a_share_realtime", DataSource("騰訊", priority=5, rate_limit=0.2))

# --- 全球行情 ---
register("global_realtime", DataSource("Yahoo Finance", priority=1, rate_limit=0.3))
register("global_realtime", DataSource("新浪全球", priority=2, rate_limit=0.2))
register("global_realtime", DataSource("東財全球", priority=3, rate_limit=0.3))
register("global_realtime", DataSource("Twelve Data", priority=4, rate_limit=8.0, daily_limit=800))

# --- 全球歷史 ---
register("global_history", DataSource("Yahoo Finance", priority=1, rate_limit=0.5))
register("global_history", DataSource("Twelve Data", priority=2, rate_limit=8.0, daily_limit=800))
register("global_history", DataSource("TradingView", priority=3, rate_limit=1.0))

# --- 儀表盤專用（TradingView Scanner + IB TWS） ---
register("dashboard_quote", DataSource("Interactive Brokers", priority=1, rate_limit=0.5))
register("dashboard_quote", DataSource("TradingView", priority=2, rate_limit=0.8))
register("dashboard_quote", DataSource("Yahoo Finance", priority=3, rate_limit=0.5))

# --- 外匯 ---
register("forex_realtime", DataSource("Frankfurter", priority=1, rate_limit=0.5))
register("forex_realtime", DataSource("新浪外匯", priority=2, rate_limit=0.2))
register("forex_realtime", DataSource("東財外匯", priority=3, rate_limit=0.3))

# --- 外匯歷史 ---
register("forex_history", DataSource("Frankfurter", priority=1, rate_limit=0.5))
register("forex_history", DataSource("Twelve Data", priority=2, rate_limit=8.0, daily_limit=800))

# --- 加密貨幣 ---
register("crypto_realtime", DataSource("Binance", priority=1, rate_limit=0.2))
register("crypto_realtime", DataSource("CoinGecko", priority=2, rate_limit=1.0))
register("crypto_realtime", DataSource("Twelve Data", priority=3, rate_limit=8.0, daily_limit=800))

register("crypto_history", DataSource("Binance", priority=1, rate_limit=0.5))
register("crypto_history", DataSource("CoinGecko", priority=2, rate_limit=1.0))
register("crypto_history", DataSource("Twelve Data", priority=3, rate_limit=8.0, daily_limit=800))

logger.info(f"📊 數據源管理器已初始化: {sum(len(v) for v in _registry.values())} 個數據源, {len(_registry)} 個類別")
