"""
運維健檢評估 — MCP、REST、CLI 共用邏輯。

對齊 docs/runbooks/README.md：正常 / 需關注 / 異常。
"""

from __future__ import annotations

from typing import Any

VERDICT_OK = "ok"
VERDICT_ATTENTION = "attention"
VERDICT_CRITICAL = "critical"

_VERDICT_ZH = {
    VERDICT_OK: "正常",
    VERDICT_ATTENTION: "需關注",
    VERDICT_CRITICAL: "異常",
}

_EXIT_CODES = {
    VERDICT_OK: 0,
    VERDICT_ATTENTION: 1,
    VERDICT_CRITICAL: 2,
}


def exit_code_for_verdict(verdict: str, *, ci_mode: bool = False) -> int:
    """CLI / HTTP probe / CI 共用退出碼。"""
    if ci_mode and verdict == VERDICT_ATTENTION:
        return 0
    return _EXIT_CODES.get(verdict, 2)


def collect_ops_snapshot() -> dict[str, Any]:
    """收集與日常健檢 SOP 一致的快照（不啟動 HTTP）。"""
    from src.config import settings
    from src.core.data_sources import health_check as ds_health_check
    from src.core.database.index_audit import audit_indexes
    from src.core.db import get_db_stats
    from src.core.pipeline_observability import get_pipeline_metrics

    snapshot: dict[str, Any] = {
        "app": settings.app_name,
        "version": settings.app_version,
    }

    errors: list[str] = []

    try:
        snapshot["database"] = get_db_stats()
    except Exception as e:
        snapshot["database"] = {"error": str(e)}
        errors.append(f"database: {e}")

    try:
        snapshot["pipeline_metrics"] = get_pipeline_metrics()
    except Exception as e:
        snapshot["pipeline_metrics"] = {"error": str(e)}
        errors.append(f"pipeline_metrics: {e}")

    try:
        snapshot["index_audit"] = audit_indexes()
    except Exception as e:
        snapshot["index_audit"] = {"error": str(e)}
        errors.append(f"index_audit: {e}")

    try:
        from src.core.task_manager import get_task_stats

        snapshot["task_queue"] = get_task_stats()
    except Exception as e:
        snapshot["task_queue"] = {"error": str(e)}
        errors.append(f"task_queue: {e}")

    try:
        from src.core.ib_data import ib_status

        # HTTP SOP 禁止 probe=True：連 TWS 會卡住事件迴圈／工作執行緒
        snapshot["ib"] = ib_status(probe=False)
    except Exception as e:
        snapshot["ib"] = {"error": str(e), "enabled": False}

    try:
        raw_ds = ds_health_check()
        degraded = [
            cat for cat, info in raw_ds.items() if info.get("status") == "degraded"
        ]
        snapshot["data_sources"] = {
            "categories": raw_ds,
            "degraded_categories": degraded,
            "total_categories": len(raw_ds),
            "healthy_categories": len(raw_ds) - len(degraded),
        }
    except Exception as e:
        snapshot["data_sources"] = {"error": str(e)}
        errors.append(f"data_sources: {e}")

    if errors:
        snapshot["collect_errors"] = errors

    return snapshot


def evaluate_ops_health(
    snapshot: dict[str, Any] | None = None,
    *,
    ci_mode: bool = False,
) -> dict[str, Any]:
    """
    依 SOP 規則產出評估結果。

    ci_mode: True 時僅 critical 產生非零 exit_code（供 GitHub Actions）。

    Returns:
        verdict: ok | attention | critical
        verdict_zh, exit_code, checks, recommendations, snapshot
    """
    snap = snapshot if snapshot is not None else collect_ops_snapshot()
    checks: list[dict[str, Any]] = []
    recommendations: list[str] = []
    worst = VERDICT_OK

    def _bump(level: str) -> None:
        nonlocal worst
        order = {VERDICT_OK: 0, VERDICT_ATTENTION: 1, VERDICT_CRITICAL: 2}
        if order.get(level, 0) > order.get(worst, 0):
            worst = level

    if snap.get("collect_errors"):
        checks.append(
            {
                "id": "collect",
                "name": "快照收集",
                "level": VERDICT_CRITICAL,
                "ok": False,
                "detail": "; ".join(snap["collect_errors"]),
            }
        )
        _bump(VERDICT_CRITICAL)
        recommendations.append(
            "修復資料庫/模組載入錯誤後重跑：python main.py ops check"
        )

    db = snap.get("database") or {}
    if db.get("error"):
        checks.append(
            {
                "id": "database",
                "name": "資料庫",
                "level": VERDICT_CRITICAL,
                "ok": False,
                "detail": db["error"],
            }
        )
        _bump(VERDICT_CRITICAL)
        recommendations.append("檢查 data/stock.db 權限與路徑（SQ_DB_PATH）")
    else:
        stocks = int(db.get("total_stocks") or 0)
        checks.append(
            {
                "id": "database",
                "name": "資料庫",
                "level": VERDICT_OK,
                "ok": True,
                "detail": (
                    f"股票 {stocks} 筆，" f"庫大小 {db.get('db_size_mb', '?')} MB"
                ),
            }
        )
        if stocks == 0:
            checks.append(
                {
                    "id": "data_ready",
                    "name": "數據就緒",
                    "level": VERDICT_ATTENTION,
                    "ok": False,
                    "detail": "股票池為空，尚未下載數據",
                }
            )
            _bump(VERDICT_ATTENTION)
            recommendations.append("執行：python main.py download 或 seed")

    pipe = snap.get("pipeline_metrics") or {}
    if pipe.get("error"):
        checks.append(
            {
                "id": "pipeline",
                "name": "數據管線",
                "level": VERDICT_CRITICAL,
                "ok": False,
                "detail": pipe["error"],
            }
        )
        _bump(VERDICT_CRITICAL)
    else:
        pending = int((pipe.get("cache") or {}).get("pending_deferred") or 0)
        if pending > 0:
            level = VERDICT_ATTENTION if pending < 50 else VERDICT_CRITICAL
            checks.append(
                {
                    "id": "cache_deferred",
                    "name": "快取延遲清理",
                    "level": level,
                    "ok": False,
                    "detail": f"pending_deferred={pending}",
                }
            )
            _bump(level)
            recommendations.append(
                "確認批量任務已結束並 flush；見 docs/runbooks/data-pipeline.md §1"
            )
        else:
            checks.append(
                {
                    "id": "cache_deferred",
                    "name": "快取延遲清理",
                    "level": VERDICT_OK,
                    "ok": True,
                    "detail": "pending_deferred=0",
                }
            )

    audit = snap.get("index_audit") or {}
    if audit.get("error"):
        checks.append(
            {
                "id": "indexes",
                "name": "索引健檢",
                "level": VERDICT_CRITICAL,
                "ok": False,
                "detail": audit["error"],
            }
        )
        _bump(VERDICT_CRITICAL)
    else:
        missing = audit.get("missing") or []
        if missing:
            checks.append(
                {
                    "id": "indexes",
                    "name": "索引健檢",
                    "level": VERDICT_ATTENTION,
                    "ok": False,
                    "detail": f"缺失 {len(missing)} 個：{', '.join(missing[:5])}"
                    + ("…" if len(missing) > 5 else ""),
                }
            )
            _bump(VERDICT_ATTENTION)
            recommendations.append(
                "MCP sq_db_index_audit(apply_missing=true) 或重啟觸發遷移；生產先備份"
            )
        else:
            checks.append(
                {
                    "id": "indexes",
                    "name": "索引健檢",
                    "level": VERDICT_OK,
                    "ok": True,
                    "detail": (
                        f"present {audit.get('present_count')}/"
                        f"{audit.get('expected_count')}"
                    ),
                }
            )

    tq = snap.get("task_queue") or {}
    if tq.get("error"):
        checks.append(
            {
                "id": "task_queue",
                "name": "任務佇列",
                "level": VERDICT_ATTENTION,
                "ok": False,
                "detail": tq["error"],
            }
        )
        _bump(VERDICT_ATTENTION)
    else:
        pending = int(tq.get("pending") or 0)
        running = int(tq.get("running") or 0)
        retrying = int(tq.get("retrying") or 0)
        in_flight = int(tq.get("in_flight") or 0)
        detail = (
            f"pending={pending} running={running} retrying={retrying} "
            f"in_flight={in_flight}"
        )
        if pending >= 100:
            checks.append(
                {
                    "id": "task_queue",
                    "name": "任務佇列",
                    "level": VERDICT_CRITICAL,
                    "ok": False,
                    "detail": detail,
                }
            )
            _bump(VERDICT_CRITICAL)
            recommendations.append("任務中心積壓過多：檢查 Worker / 取消無效 pending")
        elif pending >= 20:
            checks.append(
                {
                    "id": "task_queue",
                    "name": "任務佇列",
                    "level": VERDICT_ATTENTION,
                    "ok": False,
                    "detail": detail,
                }
            )
            _bump(VERDICT_ATTENTION)
            recommendations.append(
                "見 TROUBLESHOOTING § 任務佇列；必要時 POST /api/tasks/cancel-pending"
            )
        else:
            checks.append(
                {
                    "id": "task_queue",
                    "name": "任務佇列",
                    "level": VERDICT_OK,
                    "ok": True,
                    "detail": detail,
                }
            )

    ds = snap.get("data_sources") or {}
    if ds.get("error"):
        checks.append(
            {
                "id": "data_sources",
                "name": "數據源",
                "level": VERDICT_CRITICAL,
                "ok": False,
                "detail": ds["error"],
            }
        )
        _bump(VERDICT_CRITICAL)
    else:
        degraded = ds.get("degraded_categories") or []
        total = int(ds.get("total_categories") or 0)
        if total > 0 and len(degraded) >= total:
            checks.append(
                {
                    "id": "data_sources",
                    "name": "數據源",
                    "level": VERDICT_CRITICAL,
                    "ok": False,
                    "detail": f"全部 {total} 類別熔斷",
                }
            )
            _bump(VERDICT_CRITICAL)
            recommendations.append("見 TROUBLESHOOTING § 數據源；檢查網路與 SQ_* 開關")
        elif degraded:
            checks.append(
                {
                    "id": "data_sources",
                    "name": "數據源",
                    "level": VERDICT_ATTENTION,
                    "ok": False,
                    "detail": f"降級類別：{', '.join(degraded)}",
                }
            )
            _bump(VERDICT_ATTENTION)
            recommendations.append(
                "curl /api/data-sources/health 或 MCP sq_data_sources"
            )
        else:
            checks.append(
                {
                    "id": "data_sources",
                    "name": "數據源",
                    "level": VERDICT_OK,
                    "ok": True,
                    "detail": f"健康 {ds.get('healthy_categories')}/{total} 類別",
                }
            )

    ib = snap.get("ib") if isinstance(snap.get("ib"), dict) else {}
    if ib.get("enabled") and not ib.get("connected") and not ib.get("error"):
        checks.append(
            {
                "id": "ib_tws",
                "name": "Interactive Brokers",
                "level": VERDICT_ATTENTION,
                "ok": False,
                "detail": (
                    f"已啟用但未連上 TWS/Gateway "
                    f"({ib.get('host')}:{ib.get('port')})"
                ),
            }
        )
        _bump(VERDICT_ATTENTION)
        recommendations.append(
            "啟動 TWS/IB Gateway 並開 API 端口，或將 .env 的 SQ_IB_ENABLED 設為 false"
        )

    if worst == VERDICT_OK and not recommendations:
        recommendations.append("無需立即處置")

    # 去重建議
    seen: set[str] = set()
    unique_recs: list[str] = []
    for r in recommendations:
        if r not in seen:
            seen.add(r)
            unique_recs.append(r)

    exit_code = exit_code_for_verdict(worst, ci_mode=ci_mode)

    return {
        "verdict": worst,
        "verdict_zh": _VERDICT_ZH[worst],
        "exit_code": exit_code,
        "ci_mode": ci_mode,
        "checks": checks,
        "recommendations": unique_recs,
        "snapshot": snap,
    }


def build_health_sop_payload(
    *,
    ci_mode: bool = False,
    snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """REST /api/health/sop 與 status / detailed / MCP 共用。"""
    import time

    snap = snapshot if snapshot is not None else collect_ops_snapshot()
    ev = evaluate_ops_health(snap, ci_mode=ci_mode)
    status = "ok" if ev["verdict"] == "ok" else "degraded"
    if ev["verdict"] == VERDICT_CRITICAL:
        status = "degraded"
    ia = snap.get("index_audit") if isinstance(snap.get("index_audit"), dict) else {}
    ds = snap.get("data_sources") if isinstance(snap.get("data_sources"), dict) else {}
    return {
        "status": status,
        "checked_at": time.time(),
        "sop": {
            "verdict": ev["verdict"],
            "verdict_zh": ev["verdict_zh"],
            "exit_code": ev["exit_code"],
            "checks": ev["checks"],
            "recommendations": ev["recommendations"],
        },
        "pipeline_metrics": snap.get("pipeline_metrics"),
        "index_audit": {
            "ok": ia.get("ok"),
            "missing_count": len(ia.get("missing") or []),
            "present_count": ia.get("present_count"),
            "expected_count": ia.get("expected_count"),
        },
        "data_sources": {
            "degraded_categories": ds.get("degraded_categories") or [],
            "healthy_categories": ds.get("healthy_categories"),
            "total_categories": ds.get("total_categories"),
        },
        "task_queue": snap.get("task_queue"),
    }


def format_ops_report(evaluation: dict[str, Any], *, verbose: bool = False) -> str:
    """繁體中文文字報告（CLI / 日誌）。"""
    lines = [
        f"【總覽】{evaluation['verdict_zh']}（{evaluation['verdict']}）",
        "",
        "【各項】",
    ]
    for c in evaluation.get("checks") or []:
        mark = "✓" if c.get("ok") else "!"
        lines.append(f"  {mark} {c.get('name')}: {c.get('detail')}")
    lines.append("")
    lines.append("【建議】")
    for r in evaluation.get("recommendations") or []:
        lines.append(f"  - {r}")
    if verbose:
        snap = evaluation.get("snapshot") or {}
        lines.append("")
        lines.append("【快照】")
        import json

        lines.append(json.dumps(snap, ensure_ascii=False, indent=2))
    return "\n".join(lines)
