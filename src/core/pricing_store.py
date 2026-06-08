"""
合規估值/報價存儲（P1/P2）

- 用於銀行間估值、OTC/結構化等「不適合公開抓取」的價格輸入
- 僅存本地 JSON，避免引入 DB migration；可後續升級到 SQLite
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass
from typing import Any, Optional

_DEFAULT_PATH = os.path.join("data", "runtime_asset_prices.json")


@dataclass
class PriceRecord:
    symbol: str
    price: float
    ts: float  # epoch seconds
    source: str  # e.g. "manual", "chinabond", "broker_otc"
    kind: str = "valuation"  # price | valuation
    currency: str = ""
    note: str = ""
    updated_by: str = ""  # username or service id


def _load(path: str) -> dict[str, Any]:
    try:
        if not os.path.exists(path):
            return {"version": 1, "updated_at": 0, "records": {}}
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f) or {"version": 1, "updated_at": 0, "records": {}}
    except Exception:
        return {"version": 1, "updated_at": 0, "records": {}}


def _save(path: str, data: dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def get_price(symbol: str, path: str = _DEFAULT_PATH) -> Optional[PriceRecord]:
    sym = (symbol or "").strip()
    if not sym:
        return None
    data = _load(path)
    rec = (data.get("records") or {}).get(sym)
    if not isinstance(rec, dict):
        return None
    try:
        return PriceRecord(
            symbol=sym,
            price=float(rec.get("price") or 0),
            ts=float(rec.get("ts") or 0),
            source=str(rec.get("source") or "manual"),
            kind=str(rec.get("kind") or "valuation"),
            currency=str(rec.get("currency") or ""),
            note=str(rec.get("note") or ""),
            updated_by=str(rec.get("updated_by") or ""),
        )
    except Exception:
        return None


def upsert_prices(
    records: list[PriceRecord],
    path: str = _DEFAULT_PATH,
) -> dict[str, Any]:
    data = _load(path)
    store = data.get("records") or {}
    if not isinstance(store, dict):
        store = {}

    now = time.time()
    saved = 0
    for r in records:
        if not r.symbol:
            continue
        store[r.symbol] = asdict(r)
        saved += 1

    data["version"] = int(data.get("version") or 1)
    data["updated_at"] = now
    data["records"] = store
    _save(path, data)
    return {"success": True, "saved": saved, "updated_at": now, "path": path}
