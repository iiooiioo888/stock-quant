#!/usr/bin/env python
"""啟動前預加載示範標的 K 線至緩存。用法: python scripts/warmup_cache.py [code ...]"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.core.database.bootstrap import init_database
from src.core.cache_warmup import warmup_cache_sync


def main() -> int:
    init_database()
    codes = [a for a in sys.argv[1:] if a.strip()] or None
    stats = warmup_cache_sync(codes)
    print(stats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
