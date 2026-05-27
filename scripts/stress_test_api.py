#!/usr/bin/env python
"""簡易 API 壓力抽樣 — 驗證健康檢查與分頁端點。用法: python scripts/stress_test_api.py [base_url]"""
from __future__ import annotations

import sys
import time
import urllib.request

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000").rstrip("/")
PATHS = [
    "/api/health",
    "/api/backtest/history?limit=10&offset=0",
    "/api/cache/stats",
]


def hit(path: str) -> tuple[int, float, str]:
    url = BASE + path
    t0 = time.perf_counter()
    req = urllib.request.Request(url, headers={"Accept-Encoding": "gzip"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            ms = (time.perf_counter() - t0) * 1000
            timing = resp.headers.get("X-Response-Time-Ms", "-")
            return resp.status, ms, timing
    except Exception as e:
        return 0, (time.perf_counter() - t0) * 1000, str(e)


def main() -> int:
    print(f"Stress sample @ {BASE}")
    ok = 0
    for path in PATHS:
        status, ms, extra = hit(path)
        print(f"  {path} -> {status} {ms:.0f}ms ({extra})")
        if status == 200:
            ok += 1
    print(f"Done {ok}/{len(PATHS)} OK")
    return 0 if ok == len(PATHS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
