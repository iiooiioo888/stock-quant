"""
Polymarket HTTP 客戶端 — Gamma（元數據）與 CLOB（訂單簿/價格歷史）

特性：共享 Session、可配置限流、簡單重試、與 data_sources 熔斷聯動。
僅只讀，不涉及交易簽名。
"""
import time
from typing import Any, Optional

import requests

from src.config import settings
from src.core.data_sources import get_sources
from src.utils.logger import logger

MAX_RETRIES = 3
RETRY_DELAY = 1.5

# 客戶端錯誤（無效 token、無訂單簿）不計入熔斷
_CLIENT_ERROR_STATUSES = frozenset({400, 404, 422})

_HEADERS = {
    "User-Agent": "stock-quant/1.0 (polymarket-readonly)",
    "Accept": "application/json",
}


class PolymarketHttpError(RuntimeError):
    """Polymarket HTTP 錯誤（含 status_code）。"""

    def __init__(self, status_code: int, path: str, message: str):
        self.status_code = status_code
        self.path = path
        super().__init__(message)


class PolymarketNotFoundError(PolymarketHttpError):
    """資源不存在或該 token 無活躍訂單簿（CLOB 常回 404）。"""


class _BasePolymarketClient:
    """Polymarket 客戶端基類：限流 + 重試 + 熔斷記錄。"""

    def __init__(self, base_url: str, registry_key: str, source_name: str):
        self.base_url = base_url.rstrip("/")
        self.registry_key = registry_key
        self.source_name = source_name
        self._session = requests.Session()
        self._session.headers.update(_HEADERS)
        self._last_request = 0.0

    def _throttle(self) -> None:
        """請求間隔，避免觸發 Polymarket 限流。"""
        import random

        interval = settings.polymarket_rate_limit_sec
        jitter = interval * random.uniform(-0.2, 0.2)
        target = max(0.1, interval + jitter)
        elapsed = time.time() - self._last_request
        if elapsed < target:
            time.sleep(target - elapsed)
        self._last_request = time.time()

    def _pick_source(self) -> Optional[Any]:
        """從 data_sources 註冊表取可用源（目前每類僅一個）。"""
        sources = get_sources(self.registry_key)
        return sources[0] if sources else None

    def get_json(self, path: str, params: dict = None) -> Any:
        """
        GET JSON；失敗時記錄熔斷並拋出異常供 service 層處理。

        path: 以 / 開頭的相對路徑。
        """
        ds = self._pick_source()
        if ds is None:
            raise RuntimeError(f"Polymarket 數據源 {self.source_name} 不可用（熔斷或已禁用）")

        url = f"{self.base_url}{path}"
        last_err = None

        for attempt in range(MAX_RETRIES):
            self._throttle()
            try:
                resp = self._session.get(url, params=params or {}, timeout=15)
                if resp.status_code == 429:
                    time.sleep(RETRY_DELAY * (attempt + 1))
                    continue
                if resp.status_code in _CLIENT_ERROR_STATUSES:
                    # API 可達，僅該 token/參數無數據 — 不觸發熔斷
                    ds.record_success()
                    detail = ""
                    try:
                        body = resp.json()
                        if isinstance(body, dict):
                            detail = str(body.get("error") or body.get("message") or "")
                    except Exception:
                        detail = (resp.text or "")[:200]
                    msg = detail or f"HTTP {resp.status_code}"
                    if resp.status_code == 404:
                        raise PolymarketNotFoundError(404, path, msg)
                    raise PolymarketHttpError(resp.status_code, path, msg)
                resp.raise_for_status()
                data = resp.json()
                ds.record_success()
                return data
            except (PolymarketNotFoundError, PolymarketHttpError):
                raise
            except Exception as e:
                last_err = e
                ds.record_failure()
                logger.debug(f"Polymarket {self.source_name} {path} 失敗 ({attempt + 1}): {e}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY)

        raise RuntimeError(f"Polymarket 請求失敗: {path} — {last_err}")


class GammaClient(_BasePolymarketClient):
    """Gamma API — 市場/事件/標籤/搜尋。"""

    def __init__(self):
        super().__init__(
            settings.polymarket_gamma_base,
            "polymarket_gamma",
            "Polymarket Gamma",
        )

    def list_markets(
        self,
        limit: int = 50,
        offset: int = 0,
        active: bool = True,
        closed: bool = False,
        tag: str = None,
        order: str = "volume24hr",
        ascending: bool = False,
    ) -> list:
        """GET /markets — 市場列表。"""
        params = {
            "limit": limit,
            "offset": offset,
            "active": str(active).lower(),
            "closed": str(closed).lower(),
            "order": order,
            "ascending": str(ascending).lower(),
        }
        if tag:
            params["tag_slug"] = tag
        data = self.get_json("/markets", params)
        if isinstance(data, list):
            return data
        return data.get("markets") or data.get("data") or []

    def get_market_by_id(self, market_id: str) -> dict:
        """按 condition_id 或數字 id 查市場。"""
        return self.get_json(f"/markets/{market_id}")

    def get_market_by_slug(self, slug: str) -> dict:
        """按 slug 查市場。"""
        return self.get_json(f"/markets/slug/{slug}")

    def list_events(self, limit: int = 50, offset: int = 0, active: bool = True) -> list:
        """GET /events。"""
        params = {
            "limit": limit,
            "offset": offset,
            "active": str(active).lower(),
        }
        data = self.get_json("/events", params)
        if isinstance(data, list):
            return data
        return data.get("events") or data.get("data") or []

    def list_tags(self) -> list:
        """GET /tags。"""
        data = self.get_json("/tags")
        if isinstance(data, list):
            return data
        return data.get("tags") or data.get("data") or []

    def search(self, query: str, limit: int = 20) -> list:
        """GET /public-search — 關鍵字搜尋。"""
        params = {"q": query, "limit": limit}
        data = self.get_json("/public-search", params)
        if isinstance(data, list):
            return data
        # 響應可能嵌套 events / markets
        hits = []
        for key in ("markets", "events", "data", "results"):
            block = data.get(key)
            if isinstance(block, list):
                hits.extend(block)
        return hits or []


class ClobClient(_BasePolymarketClient):
    """CLOB API — 訂單簿與價格歷史（只讀）。"""

    def __init__(self):
        super().__init__(
            settings.polymarket_clob_base,
            "polymarket_clob",
            "Polymarket CLOB",
        )

    def get_orderbook(self, token_id: str) -> dict:
        """GET /book?token_id= — 單側 token 訂單簿。"""
        return self.get_json("/book", {"token_id": token_id})

    def get_price_history(
        self,
        token_id: str,
        interval: str = "1d",
        fidelity: int = 60,
        start_ts: int = None,
        end_ts: int = None,
    ) -> list:
        """
        GET /prices-history — 價格時間序列。

        interval: 如 1m, 1h, 1d；fidelity: 採樣粒度（分鐘）。
        """
        params = {
            "market": token_id,
            "interval": interval,
            "fidelity": fidelity,
        }
        if start_ts is not None:
            params["startTs"] = start_ts
        if end_ts is not None:
            params["endTs"] = end_ts
        data = self.get_json("/prices-history", params)
        if isinstance(data, list):
            return data
        return data.get("history") or data.get("data") or []

    def get_midpoint(self, token_id: str) -> float:
        """GET /midpoint?token_id= — 可選快捷中間價。"""
        try:
            data = self.get_json("/midpoint", {"token_id": token_id})
            if isinstance(data, dict):
                return float(data.get("mid") or data.get("price") or 0)
            return float(data)
        except Exception:
            return 0.0
