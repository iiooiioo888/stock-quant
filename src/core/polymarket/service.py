"""
Polymarket 業務服務層 — REST 與 MCP 共用入口。

職責：開關校驗、api_cache、調用 Gamma/CLOB、正規化、可選本地快照。
"""
from typing import Optional

from src.config import settings
from src.core import api_cache
from src.core.polymarket.client import ClobClient, GammaClient
from src.core.polymarket.normalize import (
    normalize_event,
    normalize_market,
    normalize_orderbook,
    normalize_price_point,
    normalize_search_hit,
    normalize_tag,
)
from src.core.polymarket.store import (
    init_polymarket_tables,
    load_market_snapshots,
    upsert_market_snapshots,
    upsert_price_points,
)
from src.utils.logger import logger

_service_instance: Optional["PolymarketService"] = None


class PolymarketDisabledError(RuntimeError):
    """功能關閉時拋出。"""


class PolymarketService:
    """
    Polymarket 只讀數據服務。

    所有對外查詢應經此類，以便 MCP tools 與 FastAPI 行為一致。
    """

    def __init__(self):
        self._gamma = GammaClient()
        self._clob = ClobClient()

    def _ensure_enabled(self) -> None:
        """檢查總開關。"""
        if not settings.polymarket_enabled:
            raise PolymarketDisabledError("Polymarket 功能已關閉（SQ_POLYMARKET_ENABLED=false）")

    def list_markets(
        self,
        limit: int = None,
        offset: int = 0,
        active: bool = True,
        tag: str = None,
        order: str = "volume",
        use_cache: bool = True,
    ) -> dict:
        """
        市場列表。

        返回：{ markets, total, limit, offset, source }
        """
        self._ensure_enabled()
        limit = limit or settings.polymarket_default_limit
        cache_key = f"pm:markets:{limit}:{offset}:{active}:{tag}:{order}"

        def _build():
            raw_list = self._gamma.list_markets(
                limit=limit, offset=offset, active=active, tag=tag, order=order,
            )
            markets = [normalize_market(r) for r in raw_list if isinstance(r, dict)]
            return {
                "markets": markets,
                "total": len(markets),
                "limit": limit,
                "offset": offset,
                "source": "gamma",
            }

        if use_cache:
            return api_cache.cached_response(
                cache_key, settings.polymarket_cache_ttl_list, _build,
            )
        return _build()

    def get_market(self, market_id_or_slug: str) -> dict:
        """
        市場詳情。支持 slug 或 id/condition_id。

        slug 含 '-' 且非純數字時走 /markets/slug/{slug}。
        """
        self._ensure_enabled()
        key = market_id_or_slug.strip()
        cache_key = f"pm:market:{key}"

        def _build():
            try:
                if key.replace("-", "").isalnum() and "-" in key and not key.isdigit():
                    raw = self._gamma.get_market_by_slug(key)
                else:
                    raw = self._gamma.get_market_by_id(key)
            except Exception:
                # 回退：slug 路徑失敗則當 id 再試
                raw = self._gamma.get_market_by_id(key)
            if isinstance(raw, list) and raw:
                raw = raw[0]
            detail = normalize_market(raw if isinstance(raw, dict) else {})
            detail["detail"] = True
            return detail

        return api_cache.cached_response(
            cache_key, settings.polymarket_cache_ttl_detail, _build,
        )

    def list_events(self, limit: int = 50, offset: int = 0, active: bool = True) -> dict:
        """事件列表。"""
        self._ensure_enabled()
        cache_key = f"pm:events:{limit}:{offset}:{active}"

        def _build():
            raw = self._gamma.list_events(limit=limit, offset=offset, active=active)
            events = [normalize_event(r) for r in raw if isinstance(r, dict)]
            return {"events": events, "total": len(events), "limit": limit, "offset": offset}

        return api_cache.cached_response(cache_key, settings.polymarket_cache_ttl_list, _build)

    def list_tags(self) -> dict:
        """標籤列表。"""
        self._ensure_enabled()

        def _build():
            raw = self._gamma.list_tags()
            tags = [normalize_tag(r) for r in raw]
            return {"tags": tags, "total": len(tags)}

        return api_cache.cached_response("pm:tags", settings.polymarket_cache_ttl_list, _build)

    def search(self, query: str, limit: int = 20) -> dict:
        """關鍵字搜尋市場/事件。"""
        self._ensure_enabled()
        q = (query or "").strip()
        if not q:
            return {"results": [], "query": q, "total": 0}

        cache_key = f"pm:search:{q}:{limit}"

        def _build():
            raw = self._gamma.search(q, limit=limit)
            results = [normalize_search_hit(r) for r in raw if isinstance(r, dict)]
            return {"results": results, "query": q, "total": len(results)}

        return api_cache.cached_response(cache_key, settings.polymarket_cache_ttl_list, _build)

    def get_orderbook(self, token_id: str) -> dict:
        """單 token 訂單簿（Yes 或 No 側）。"""
        self._ensure_enabled()
        tid = (token_id or "").strip()
        if not tid:
            raise ValueError("token_id 不能為空")
        depth = settings.polymarket_orderbook_depth
        cache_key = f"pm:book:{tid}:{depth}"

        def _build():
            raw = self._clob.get_orderbook(tid)
            return normalize_orderbook(raw, tid, depth=depth)

        return api_cache.cached_response(
            cache_key, settings.polymarket_cache_ttl_orderbook, _build,
        )

    def get_price_history(
        self,
        token_id: str,
        interval: str = "1d",
        fidelity: int = 60,
        start_ts: int = None,
        end_ts: int = None,
        persist: bool = False,
    ) -> dict:
        """價格歷史序列；persist=True 時寫入 SQLite。"""
        self._ensure_enabled()
        tid = (token_id or "").strip()
        if not tid:
            raise ValueError("token_id 不能為空")

        cache_key = f"pm:hist:{tid}:{interval}:{fidelity}:{start_ts}:{end_ts}"

        def _build():
            raw = self._clob.get_price_history(
                tid, interval=interval, fidelity=fidelity,
                start_ts=start_ts, end_ts=end_ts,
            )
            points = []
            for row in raw:
                if not isinstance(row, dict):
                    continue
                p = normalize_price_point(row)
                if p:
                    points.append(p)
            points.sort(key=lambda x: x["ts"])
            if persist and points:
                upsert_price_points(tid, points, interval=interval)
            return {
                "token_id": tid,
                "interval": interval,
                "points": points,
                "total": len(points),
                "source": "clob",
            }

        return api_cache.cached_response(
            cache_key, settings.polymarket_cache_ttl_detail, _build,
        )

    def sync_snapshots(self, limit: int = None) -> dict:
        """
        拉取熱門市場並寫入本地快照表（供定時任務或手動 sync 調用）。
        """
        self._ensure_enabled()
        init_polymarket_tables()
        limit = limit or settings.polymarket_default_limit
        payload = self.list_markets(limit=limit, use_cache=False)
        markets = payload.get("markets") or []
        # 額外拉取 watchlist slugs
        for slug in settings.polymarket_watchlist_slugs or []:
            try:
                m = self.get_market(slug)
                if m.get("market_id"):
                    markets.append(m)
            except Exception as e:
                logger.debug(f"watchlist slug {slug} 跳過: {e}")
        n = upsert_market_snapshots(markets)
        return {"synced": n, "markets": markets[:limit]}

    def list_snapshots(self, limit: int = 50) -> dict:
        """僅讀本地快照（網路不可用時降級）。"""
        init_polymarket_tables()
        markets = load_market_snapshots(limit=limit)
        return {"markets": markets, "total": len(markets), "source": "local_snapshot"}


def get_polymarket_service() -> PolymarketService:
    """單例服務（進程內復用 HTTP Session）。"""
    global _service_instance
    if _service_instance is None:
        _service_instance = PolymarketService()
    return _service_instance
