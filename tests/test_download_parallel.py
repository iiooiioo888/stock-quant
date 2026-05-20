"""下載並發任務"""
import time
from unittest.mock import patch

from src.core.download_tasks import _download_codes_parallel


def test_parallel_download_faster_than_serial(monkeypatch):
    calls = {"n": 0}

    def fake_download(code, market="a_share"):
        calls["n"] += 1
        time.sleep(0.05)
        return 10

    monkeypatch.setattr("src.core.history.download_one", fake_download)
    monkeypatch.setattr(
        "src.core.download_tasks.settings.download_max_workers",
        4,
        raising=False,
    )
    from src.config import settings
    settings.download_max_workers = 4
    settings.download_throttle_sec = 0

    codes = [f"C{i:03d}" for i in range(8)]
    t0 = time.perf_counter()
    details, total = _download_codes_parallel("a_share", "A股", codes, task_id=None)
    elapsed = time.perf_counter() - t0

    assert len(details) == 8
    assert total == 80
    assert calls["n"] == 8
    assert elapsed < 0.35
