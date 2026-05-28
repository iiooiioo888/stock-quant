"""
用戶個人資產配置 — 持久化於 users.settings.holdings（與多幣種結算共用）。

每筆持倉：
  code, quantity, currency?, cost?, name?, weight_pct?（僅展示用，結算以 quantity×現價）
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any, Optional

from src.core.db import get_conn
from src.core.portfolio_currency import infer_currency
from src.utils.logger import logger


def _normalize_code(code: str) -> str:
    code = str(code or "").strip().upper()
    if code.isdigit() and len(code) < 6:
        return code.zfill(6)
    return code


def _normalize_position(raw: dict) -> Optional[dict]:
    if not isinstance(raw, dict):
        return None
    code = _normalize_code(raw.get("code") or raw.get("symbol") or "")
    if not code:
        return None
    try:
        qty = float(raw.get("quantity") or raw.get("qty") or 0)
    except (TypeError, ValueError):
        qty = 0.0
    if qty <= 0:
        return None
    curr = str(raw.get("currency") or infer_currency(code)).upper()
    cost = raw.get("cost") or raw.get("price") or raw.get("avg_cost")
    try:
        cost_f = float(cost) if cost is not None and cost != "" else 0.0
    except (TypeError, ValueError):
        cost_f = 0.0
    name = str(raw.get("name") or "").strip()
    note = str(raw.get("note") or "").strip()
    try:
        w = float(raw.get("weight_pct") or 0)
    except (TypeError, ValueError):
        w = 0.0
    return {
        "code": code,
        "name": name,
        "quantity": qty,
        "currency": curr,
        "cost": cost_f,
        "weight_pct": w,
        "note": note,
        "asset_type": str(raw.get("asset_type") or "equity"),
    }


def _load_user_settings(user_id: int) -> dict:
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT settings FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    if not row or not row["settings"]:
        return {}
    try:
        data = json.loads(row["settings"])
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _save_user_settings(user_id: int, settings: dict) -> None:
    payload = json.dumps(settings, ensure_ascii=False)
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET settings = ? WHERE id = ?",
            (payload, user_id),
        )


def list_positions(user_id: int) -> list[dict]:
    st = _load_user_settings(user_id)
    out: list[dict] = []
    seen: set[str] = set()
    for item in st.get("holdings") or []:
        pos = _normalize_position(item)
        if not pos or pos["code"] in seen:
            continue
        seen.add(pos["code"])
        out.append(pos)
    return out


def replace_positions(user_id: int, positions: list[dict]) -> list[dict]:
    st = _load_user_settings(user_id)
    normalized: list[dict] = []
    seen: set[str] = set()
    for item in positions or []:
        pos = _normalize_position(item if isinstance(item, dict) else {})
        if not pos or pos["code"] in seen:
            continue
        seen.add(pos["code"])
        normalized.append(pos)
    st["holdings"] = normalized
    st["allocation_updated_at"] = datetime.now().isoformat(timespec="seconds")
    _save_user_settings(user_id, st)
    return normalized


def upsert_position(user_id: int, raw: dict) -> list[dict]:
    pos = _normalize_position(raw or {})
    if not pos:
        raise ValueError("無效的持倉資料")
    items = list_positions(user_id)
    replaced = False
    for i, existing in enumerate(items):
        if existing["code"] == pos["code"]:
            items[i] = {**existing, **pos}
            replaced = True
            break
    if not replaced:
        items.append(pos)
    return replace_positions(user_id, items)


def remove_position(user_id: int, code: str) -> list[dict]:
    code = _normalize_code(code)
    items = [p for p in list_positions(user_id) if p["code"] != code]
    return replace_positions(user_id, items)


def _a_share_code_key(code: str) -> str:
    c = str(code or "").strip().upper()
    if c.endswith((".SS", ".SZ")):
        return c.split(".")[0].zfill(6)
    if c.isdigit() and len(c) <= 6:
        return c.zfill(6)
    return ""


def _latest_price_for_code(code: str) -> float:
    """K 線收盤價優先；無本地數據時降級即時行情。"""
    from src.core.portfolio_settlement import _latest_price

    raw = str(code or "").strip().upper()
    price = float(_latest_price(raw) or 0.0)
    if price > 0:
        return price

    ashare = _a_share_code_key(raw)
    if ashare:
        try:
            from src.core.realtime import fetch_one_realtime

            q = fetch_one_realtime(ashare)
            p = float((q or {}).get("price") or 0)
            if p > 0:
                return p
        except Exception as e:
            logger.debug(f"配置欄 A 股即時價失敗 {ashare}: {e}")

    try:
        from src.core.global_market import get_global_realtime

        sym = raw
        if ashare and not sym.endswith((".SS", ".SZ")):
            sym = f"{ashare}.SS"
        rows = get_global_realtime([sym]) or []
        p = float((rows[0] or {}).get("price") or 0) if rows else 0.0
        if p > 0:
            return p
    except Exception as e:
        logger.debug(f"配置欄全球即時價失敗 {raw}: {e}")

    return 0.0


def enrich_positions(
    positions: list[dict],
    mode: str = "market_value",
) -> tuple[list[dict], dict[str, float]]:
    """
    為持倉計算 last_price、market_value、weight_pct。
    mode: market_value | quantity
    """
    mode = (mode or "market_value").strip().lower()
    if mode not in ("market_value", "quantity"):
        mode = "market_value"

    rows: list[dict] = []
    for p in positions or []:
        if not isinstance(p, dict):
            continue
        qty = float(p.get("quantity") or 0)
        if qty <= 0:
            continue
        price = float(p.get("last_price") or 0) or _latest_price_for_code(p.get("code", ""))
        cost = float(p.get("cost") or 0)
        mv = qty * price if price > 0 else (qty * cost if cost > 0 else 0.0)
        rows.append({
            **p,
            "last_price": round(price, 4) if price > 0 else 0.0,
            "market_value": round(mv, 2),
        })

    total_mv = sum(float(r.get("market_value") or 0) for r in rows)
    total_qty = sum(float(r.get("quantity") or 0) for r in rows)

    for r in rows:
        if mode == "quantity":
            w = (float(r["quantity"]) / total_qty * 100.0) if total_qty > 0 else 0.0
        else:
            w = (float(r.get("market_value") or 0) / total_mv * 100.0) if total_mv > 0 else 0.0
        r["weight_pct"] = round(w, 2)

    meta = {
        "mode": mode,
        "total_market_value": round(total_mv, 2),
        "total_quantity": round(total_qty, 4),
    }
    return rows, meta


def allocation_payload(user_id: int, *, weight_mode: str = "market_value") -> dict[str, Any]:
    positions = list_positions(user_id)
    enriched, meta = enrich_positions(positions, weight_mode)
    return {
        "success": True,
        "positions": enriched,
        "count": len(enriched),
        "updated_at": _load_user_settings(user_id).get("allocation_updated_at"),
        "weight_mode": meta.get("mode"),
        "total_market_value": meta.get("total_market_value"),
    }
