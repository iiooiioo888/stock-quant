"""
對外接口探活 — 主動 HTTP/業務探測 + 數據源註冊表快照。

供「接口檢查」頁與 /api/external/check 使用。
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Callable, Optional

import requests

from src.core.data_sources import get_all_sources, health_check

PROBE_TIMEOUT = 12
_last_result: Optional[dict] = None


def _now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _probe_row(
    probe_id: str,
    name: str,
    category: str,
    ok: bool,
    latency_ms: float,
    message: str,
    *,
    status_code: int = None,
    endpoint: str = "",
    detail: dict = None,
) -> dict:
    return {
        "id": probe_id,
        "name": name,
        "category": category,
        "ok": ok,
        "latency_ms": round(latency_ms, 1),
        "status_code": status_code,
        "message": message,
        "endpoint": endpoint,
        "detail": detail or {},
        "checked_at": _now_iso(),
    }


def _http_get_probe(
    probe_id: str,
    name: str,
    category: str,
    url: str,
    *,
    expect_json: bool = True,
    ok_status: tuple[int, ...] = (200,),
) -> dict:
    t0 = time.perf_counter()
    try:
        resp = requests.get(
            url,
            timeout=PROBE_TIMEOUT,
            headers={
                "User-Agent": "stock-quant/external-probe",
                "Accept": "application/json" if expect_json else "*/*",
            },
        )
        elapsed = (time.perf_counter() - t0) * 1000
        ok = resp.status_code in ok_status
        msg = "OK" if ok else f"HTTP {resp.status_code}"
        if ok and expect_json:
            try:
                resp.json()
            except Exception:
                ok = False
                msg = "響應非 JSON"
        return _probe_row(
            probe_id,
            name,
            category,
            ok,
            elapsed,
            msg,
            status_code=resp.status_code,
            endpoint=url,
        )
    except Exception as e:
        elapsed = (time.perf_counter() - t0) * 1000
        return _probe_row(
            probe_id, name, category, False, elapsed, str(e)[:300], endpoint=url
        )


def probe_registry() -> dict:
    """數據源註冊表（無外網請求）。"""
    t0 = time.perf_counter()
    reg = health_check()
    all_src = get_all_sources()
    cats_ok = sum(1 for v in reg.values() if v.get("status") == "ok")
    cats_total = len(reg)
    elapsed = (time.perf_counter() - t0) * 1000
    ok = cats_ok > 0
    return _probe_row(
        "registry",
        "數據源註冊表",
        "system",
        ok,
        elapsed,
        f"{cats_ok}/{cats_total} 類別可用",
        detail={"health": reg, "sources": all_src},
    )


# ====== 目錄（供前端展示） ======
PROBE_CATALOG: list[dict] = [
    {"id": "registry", "name": "數據源註冊表", "category": "system", "active": True},
    {
        "id": "eastmoney_sector",
        "name": "東財板塊列表",
        "category": "a_share",
        "active": True,
    },
    {
        "id": "yahoo_a_share",
        "name": "Yahoo A股行情",
        "category": "a_share",
        "active": True,
    },
    {
        "id": "binance_ping",
        "name": "Binance Ping",
        "category": "crypto",
        "active": True,
    },
    {
        "id": "frankfurter",
        "name": "Frankfurter 匯率",
        "category": "forex",
        "active": True,
    },
    {
        "id": "ib_tws",
        "name": "Interactive Brokers",
        "category": "system",
        "active": True,
    },
    # 官方/持牌/權威渠道（以可達性探測為主，不抓取/解析行情）
    {"id": "sse_home", "name": "上交所 SSE", "category": "exchange", "active": True},
    {"id": "szse_home", "name": "深交所 SZSE", "category": "exchange", "active": True},
    {"id": "bse_home", "name": "北交所 BSE", "category": "exchange", "active": True},
    {
        "id": "chinamoney_home",
        "name": "中國貨幣網",
        "category": "bond_fx",
        "active": True,
    },
    {
        "id": "chinabond_home",
        "name": "中國債券信息網",
        "category": "bond_fx",
        "active": True,
    },
    {
        "id": "chinawealth_home",
        "name": "中國理財網",
        "category": "wealth",
        "active": True,
    },
    {"id": "amac_home", "name": "基金業協會 AMAC", "category": "fund", "active": True},
    {
        "id": "iachina_home",
        "name": "保險行業協會",
        "category": "insurance",
        "active": True,
    },
    {"id": "sge_home", "name": "上金所 SGE", "category": "metals", "active": True},
    {"id": "shfe_home", "name": "上期所 SHFE", "category": "futures", "active": True},
]


def probe_eastmoney_sector() -> dict:
    t0 = time.perf_counter()
    try:
        from src.core.sector import get_sector_list

        rows = get_sector_list("industry") or []
        elapsed = (time.perf_counter() - t0) * 1000
        ok = len(rows) > 0
        return _probe_row(
            "eastmoney_sector",
            "東財板塊列表",
            "a_share",
            ok,
            elapsed,
            f"{len(rows)} 條" if ok else "無數據",
        )
    except Exception as e:
        elapsed = (time.perf_counter() - t0) * 1000
        return _probe_row(
            "eastmoney_sector", "東財板塊列表", "a_share", False, elapsed, str(e)[:300]
        )


def probe_yahoo_a_share() -> dict:
    t0 = time.perf_counter()
    try:
        from src.core.yahoo_finance import fetch_a_share_realtime

        row = fetch_a_share_realtime("000001")
        elapsed = (time.perf_counter() - t0) * 1000
        ok = bool(row and row.get("price"))
        return _probe_row(
            "yahoo_a_share",
            "Yahoo A股行情",
            "a_share",
            ok,
            elapsed,
            f"000001 現價 {row.get('price')}" if ok else "無報價",
        )
    except Exception as e:
        elapsed = (time.perf_counter() - t0) * 1000
        return _probe_row(
            "yahoo_a_share", "Yahoo A股行情", "a_share", False, elapsed, str(e)[:300]
        )


def probe_binance_ping() -> dict:
    return _http_get_probe(
        "binance_ping",
        "Binance Ping",
        "crypto",
        "https://api.binance.com/api/v3/ping",
    )


def probe_frankfurter() -> dict:
    return _http_get_probe(
        "frankfurter",
        "Frankfurter 匯率",
        "forex",
        "https://api.frankfurter.app/latest",
    )


def _site_probe(probe_id: str, name: str, category: str, url: str) -> dict:
    return _http_get_probe(
        probe_id,
        name,
        category,
        url,
        expect_json=False,
        ok_status=(200, 301, 302, 303, 307, 308),
    )


def probe_sse_home() -> dict:
    return _site_probe("sse_home", "上交所 SSE", "exchange", "https://www.sse.com.cn/")


def probe_szse_home() -> dict:
    return _site_probe("szse_home", "深交所 SZSE", "exchange", "https://www.szse.cn/")


def probe_bse_home() -> dict:
    return _site_probe("bse_home", "北交所 BSE", "exchange", "https://www.bse.cn/")


def probe_chinamoney_home() -> dict:
    return _site_probe(
        "chinamoney_home", "中國貨幣網", "bond_fx", "https://www.chinamoney.com.cn/"
    )


def probe_chinabond_home() -> dict:
    return _site_probe(
        "chinabond_home", "中國債券信息網", "bond_fx", "https://www.chinabond.com.cn/"
    )


def probe_chinawealth_home() -> dict:
    return _site_probe(
        "chinawealth_home", "中國理財網", "wealth", "https://www.chinawealth.com.cn/"
    )


def probe_amac_home() -> dict:
    return _site_probe(
        "amac_home", "基金業協會 AMAC", "fund", "https://www.amac.org.cn/"
    )


def probe_iachina_home() -> dict:
    return _site_probe(
        "iachina_home", "保險行業協會", "insurance", "https://www.iachina.cn/"
    )


def probe_sge_home() -> dict:
    return _site_probe("sge_home", "上金所 SGE", "metals", "https://www.sge.com.cn/")


def probe_shfe_home() -> dict:
    return _site_probe(
        "shfe_home", "上期所 SHFE", "futures", "https://www.shfe.com.cn/"
    )


def probe_ib_tws() -> dict:
    """IB TWS / Gateway（需 SQ_IB_ENABLED + ib_insync + 本地 TWS）。"""
    t0 = time.perf_counter()
    try:
        from src.core.ib_data import ib_status

        st = ib_status(probe=True)
        elapsed = (time.perf_counter() - t0) * 1000
        ok = bool(st.get("connected"))
        if not st.get("enabled"):
            msg = "未啟用（設 SQ_IB_ENABLED=true）"
        elif not st.get("library"):
            msg = "缺少 ib_insync（pip install -r requirements-ib.txt）"
        elif ok:
            msg = f"已連接 {st.get('host')}:{st.get('port')}"
        else:
            msg = "未連接 TWS/Gateway"
        return _probe_row(
            "ib_tws",
            "Interactive Brokers",
            "system",
            ok,
            elapsed,
            msg,
            detail=st,
        )
    except Exception as e:
        elapsed = (time.perf_counter() - t0) * 1000
        return _probe_row(
            "ib_tws", "Interactive Brokers", "system", False, elapsed, str(e)[:300]
        )


_PROBE_FUNCS: dict[str, Callable[[], dict]] = {
    "registry": probe_registry,
    "eastmoney_sector": probe_eastmoney_sector,
    "yahoo_a_share": probe_yahoo_a_share,
    "binance_ping": probe_binance_ping,
    "frankfurter": probe_frankfurter,
    "ib_tws": probe_ib_tws,
    "sse_home": probe_sse_home,
    "szse_home": probe_szse_home,
    "bse_home": probe_bse_home,
    "chinamoney_home": probe_chinamoney_home,
    "chinabond_home": probe_chinabond_home,
    "chinawealth_home": probe_chinawealth_home,
    "amac_home": probe_amac_home,
    "iachina_home": probe_iachina_home,
    "sge_home": probe_sge_home,
    "shfe_home": probe_shfe_home,
}


def get_registry_only() -> dict:
    """只返回註冊表快照（無外網）。"""
    row = probe_registry()
    return {
        "status": "ok" if row.get("ok") else "degraded",
        "checked_at": row.get("checked_at"),
        "registry": row.get("detail", {}).get("health", {}),
        "sources": row.get("detail", {}).get("sources", {}),
        "catalog": PROBE_CATALOG,
    }


def run_all_probes(*, probe_ids: list[str] | None = None, max_workers: int = 6) -> dict:
    """執行全量/部分探測。"""
    global _last_result

    ids = probe_ids or [p["id"] for p in PROBE_CATALOG if p.get("active")]
    funcs: list[tuple[str, Callable[[], dict]]] = []
    for pid in ids:
        fn = _PROBE_FUNCS.get(pid)
        if fn:
            funcs.append((pid, fn))

    t0 = time.perf_counter()
    rows: list[dict] = []

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = {ex.submit(fn): pid for pid, fn in funcs}
        for fut in as_completed(futs):
            pid = futs[fut]
            try:
                row = fut.result()
                if isinstance(row, dict):
                    rows.append(row)
                else:
                    rows.append(_probe_row(pid, pid, "error", False, 0, "返回非 dict"))
            except Exception as e:
                rows.append(_probe_row(pid, pid, "error", False, 0, str(e)[:300]))

    elapsed_ms = (time.perf_counter() - t0) * 1000
    ok = sum(1 for r in rows if r.get("ok"))
    total = len(rows)
    fail = total - ok

    result = {
        "status": "ok" if fail == 0 else ("degraded" if ok > 0 else "fail"),
        "checked_at": _now_iso(),
        "duration_ms": round(elapsed_ms, 1),
        "summary": {"total": total, "ok": ok, "fail": fail},
        "probes": sorted(
            rows, key=lambda r: (str(r.get("category")), str(r.get("id")))
        ),
        "registry": get_registry_only().get("registry"),
        "catalog": PROBE_CATALOG,
    }
    _last_result = result
    return result


def get_last_probe_result() -> Optional[dict]:
    return _last_result
