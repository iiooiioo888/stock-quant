"""資料抓取緩衝：合併進行中請求、新鮮數據跳過外網。"""

import threading
import time

from src.core import data_fetch_buffer as buf


def test_download_one_buffered_coalesces(monkeypatch):
    calls = {"n": 0}
    started = threading.Event()
    release = threading.Event()

    def fake_auto(code, start_date=None, market=None):
        calls["n"] += 1
        started.set()
        release.wait(timeout=2)
        return 5, "fetched"

    monkeypatch.setattr("src.core.auto_kline_fetch.download_one_auto", fake_auto)
    monkeypatch.setattr(buf, "is_fresh", lambda *a, **k: False)

    results = []

    def worker():
        results.append(buf.download_one_buffered("000001", market="a_share"))

    t1 = threading.Thread(target=worker)
    t2 = threading.Thread(target=worker)
    t1.start()
    assert started.wait(timeout=2)
    t2.start()
    time.sleep(0.05)
    release.set()
    t1.join(timeout=2)
    t2.join(timeout=2)
    assert calls["n"] == 1
    assert len(results) == 2
    assert {r[1] for r in results} <= {"fetched", "coalesced", "coalesced_empty", "buffer"}


def test_is_fresh_skips_when_last_ok(monkeypatch):
    monkeypatch.setattr("src.core.local_kline.has_local_kline", lambda *a, **k: True)
    monkeypatch.setattr(buf, "_buffer_hours", lambda: 12)
    buf.mark_fetched("600519")
    assert buf.is_fresh("600519") is True


def test_is_inflight_while_downloading(monkeypatch):
    started = threading.Event()
    release = threading.Event()

    def fake_auto(code, start_date=None, market=None):
        started.set()
        release.wait(timeout=2)
        return 3, "fetched"

    monkeypatch.setattr("src.core.auto_kline_fetch.download_one_auto", fake_auto)
    monkeypatch.setattr(buf, "is_fresh", lambda *a, **k: False)

    t = threading.Thread(target=lambda: buf.download_one_buffered("000002"))
    t.start()
    assert started.wait(timeout=2)
    assert buf.is_inflight("000002") is True
    release.set()
    t.join(timeout=2)
    assert buf.is_inflight("000002") is False


def test_last_ok_persists_across_reload(monkeypatch, tmp_path):
    monkeypatch.setattr(buf, "_buffer_path", lambda: tmp_path / "buf.json")
    monkeypatch.setattr("src.core.local_kline.has_local_kline", lambda *a, **k: True)
    monkeypatch.setattr(buf, "_buffer_hours", lambda: 12)
    buf._last_ok.clear()
    buf._loaded = False
    buf.mark_fetched("000001")
    buf._last_ok.clear()
    buf._loaded = False
    assert buf.is_fresh("000001") is True
