"""
對外接口檢查 API — 探活目錄、註冊表快照、全量探測。
"""

from fastapi import APIRouter, Depends, HTTPException, Query

from src.core.auth import require_auth
from src.core.external_probe import (
    PROBE_CATALOG,
    get_last_probe_result,
    get_registry_only,
    run_all_probes,
)

router = APIRouter(tags=["external"])


@router.get("/api/external/check/catalog")
async def external_check_catalog():
    """探針目錄（靜態）。"""
    return {"catalog": PROBE_CATALOG, "total": len(PROBE_CATALOG)}


@router.get("/api/external/check/registry")
async def external_check_registry():
    """數據源註冊表快照（無外網探測）。"""
    return get_registry_only()


@router.get("/api/external/check")
async def external_check_last():
    """最近一次全量探測結果；若尚未執行則僅返回註冊表。"""
    last = get_last_probe_result()
    if last:
        return last
    reg = get_registry_only()
    return {
        "status": "unknown",
        "message": "尚未執行全量探測，請點擊「立即檢測」",
        "registry": reg.get("registry"),
        "catalog": reg.get("catalog"),
    }


@router.post("/api/external/check/run")
async def external_check_run(
    probes: str = Query(None, description="逗號分隔探針 id，空=全部"),
    user=Depends(require_auth),
):
    """執行對外接口全量/部分探測（可能耗時 10–30 秒）。"""
    ids = None
    if probes:
        ids = [p.strip() for p in probes.split(",") if p.strip()]
    try:
        return run_all_probes(probe_ids=ids)
    except Exception as e:
        raise HTTPException(500, f"探測失敗: {e}")
