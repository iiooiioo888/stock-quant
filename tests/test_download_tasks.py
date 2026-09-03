"""下載任務：信號量、進度 meta、全市場計劃。"""

import time
from unittest.mock import patch

from src.core.download_tasks import (
    _akshare_semaphore,
    _download_codes_parallel,
    run_market_download,
)


def test_akshare_semaphore_singleton(monkeypatch):
    monkeypatch.setattr(
        "src.core.download_tasks.settings.download_akshare_max_concurrent", 2
    )
    s1 = _akshare_semaphore()
    s2 = _akshare_semaphore()
    assert s1 is s2


def test_parallel_download_reports_progress(monkeypatch):
    calls = []

    def fake_download(code, market="a_share"):
        time.sleep(0.01)
        return 3

    monkeypatch.setattr("src.core.download_tasks._history_download_one", fake_download)
    from src.config import settings

    settings.download_max_workers = 3
    settings.download_throttle_sec = 0
    settings.download_akshare_min_interval_sec = 0

    with patch("src.core.download_tasks._update_download_meta") as meta:
        details, total = _download_codes_parallel(
            "crypto", "加密貨幣", ["BTCUSDT", "ETHUSDT"], task_id="t1"
        )
        calls.append(meta.call_count)

    assert len(details) == 2
    assert total == 6
    assert calls[0] >= 2


def test_run_market_download_empty():
    out = run_market_download("forex", [], task_id=None)
    assert out["total_symbols"] == 0
    assert out["total_records"] == 0
