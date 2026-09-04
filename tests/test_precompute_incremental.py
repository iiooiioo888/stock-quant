"""
預計算指標增量更新測試

驗證：
1. 增量模式只重算新增 K 線區間，結果與全量重算一致
2. 無新增數據時 skipped
3. OBV 累積型指標的接力正確
4. 遞歸型指標（RSI/EMA）warmup 窗口收斂
"""

import sqlite3
import uuid
from datetime import datetime, timedelta

import numpy as np
import pytest

from src.config import settings
from src.core.db import clear_data_cache
from src.core.indicators.precomputed_indicators import (
    IndicatorConfig,
    _get_table_max_date,
    _params_hash,
    compute_indicator_for_code,
)


def _insert_klines(code: str, n_bars: int, start: datetime, base_price: float = 10.0):
    """插入合成日 K 線（確定性隨機走勢）"""
    rng = np.random.RandomState(abs(hash(code)) % (2**31))
    dates = [(start + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(n_bars)]
    close = base_price + np.cumsum(rng.randn(n_bars) * 0.1)
    rows = []
    for i, d in enumerate(dates):
        c = float(close[i])
        rows.append(
            (code, d, c * 0.998, c * 1.01, c * 0.99, c, float(1_000_000 + i), None)
        )
    conn = sqlite3.connect(settings.db_path)
    try:
        conn.executemany(
            "INSERT OR REPLACE INTO daily_kline (code, date, open, high, low, close, volume, amount)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        conn.commit()
    finally:
        conn.close()
    clear_data_cache(quiet=True)
    return dates


def _read_indicator_table(code: str, config: IndicatorConfig) -> dict:
    """讀取指標表 {date: {col: val}}"""
    table = f"indicator_{code}_{config.name}_{_params_hash(config.params)}"
    conn = sqlite3.connect(settings.db_path)
    try:
        rows = conn.execute(f'SELECT * FROM "{table}" ORDER BY date').fetchall()
        cols = [d[1] for d in conn.execute(f'PRAGMA table_info("{table}")').fetchall()]
    finally:
        conn.close()
    out = {}
    for r in rows:
        out[r[1]] = {cols[i]: r[i] for i in range(2, len(cols)) if cols[i] != "created_at"}
    return out


def _drop_indicator_table(code: str, config: IndicatorConfig):
    table = f"indicator_{code}_{config.name}_{_params_hash(config.params)}"
    conn = sqlite3.connect(settings.db_path)
    try:
        conn.execute(f'DROP TABLE IF EXISTS "{table}"')
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def kline_code():
    code = f"INC{uuid.uuid4().hex[:5].upper()}"
    yield code
    # 清理指標表
    for cfg in (
        IndicatorConfig("sma", {"period": 20}, ["sma_20"]),
        IndicatorConfig("obv", {}, ["obv"]),
        IndicatorConfig("rsi", {"period": 14}, ["rsi_14"]),
        IndicatorConfig("ema", {"period": 12}, ["ema_12"]),
    ):
        _drop_indicator_table(code, cfg)


def test_incremental_sma_matches_full(kline_code):
    code = kline_code
    cfg = IndicatorConfig("sma", {"period": 20}, ["sma_20"])

    dates = _insert_klines(code, 300, datetime(2024, 1, 1))
    r1 = compute_indicator_for_code(code, cfg, incremental=True)
    assert r1.status == "success"  # 無緩存 → 全量

    # 新增 5 根 K 線
    _insert_klines(code, 305, datetime(2024, 1, 1))
    r2 = compute_indicator_for_code(code, cfg, incremental=True)
    assert r2.status == "success"

    inc_table = _read_indicator_table(code, cfg)
    assert len(inc_table) == 305
    assert dates[299] in inc_table  # 舊行保留

    # 對照：全量重算到另一張「真值」
    _drop_indicator_table(code, cfg)
    compute_indicator_for_code(code, cfg, incremental=False)
    full_table = _read_indicator_table(code, cfg)

    # 全量與增量每個日期數值一致（NaN→None 的前導行跳過）
    for d, cols in full_table.items():
        assert d in inc_table
        if cols["sma_20"] is None:
            assert inc_table[d]["sma_20"] is None
            continue
        assert abs(cols["sma_20"] - inc_table[d]["sma_20"]) < 1e-9, f"{d} 不一致"


def test_incremental_skip_when_up_to_date(kline_code):
    code = kline_code
    cfg = IndicatorConfig("sma", {"period": 20}, ["sma_20"])
    _insert_klines(code, 100, datetime(2024, 1, 1))
    compute_indicator_for_code(code, cfg, incremental=True)

    # 無新增 → skipped
    r = compute_indicator_for_code(code, cfg, incremental=True)
    assert r.status == "skipped"
    assert "已是最新" in (r.error or "")


def test_incremental_obv_continuation(kline_code):
    """OBV 累積型指標：增量接力後與全量一致"""
    code = kline_code
    cfg = IndicatorConfig("obv", {}, ["obv"])

    _insert_klines(code, 200, datetime(2024, 1, 1))
    compute_indicator_for_code(code, cfg, incremental=False)
    before = _read_indicator_table(code, cfg)

    _insert_klines(code, 210, datetime(2024, 1, 1))
    r = compute_indicator_for_code(code, cfg, incremental=True)
    assert r.status == "success"

    inc = _read_indicator_table(code, cfg)

    _drop_indicator_table(code, cfg)
    compute_indicator_for_code(code, cfg, incremental=False)
    full = _read_indicator_table(code, cfg)

    assert len(inc) == len(full) == 210
    for d in full:
        assert abs(full[d]["obv"] - inc[d]["obv"]) < 1e-6, f"OBV {d} 接力不一致"


def test_incremental_recursive_indicators_converge(kline_code):
    """遞歸型指標（RSI/EMA）：warmup 窗口內重算應收斂到全量結果"""
    code = kline_code
    n_bars = 400
    _insert_klines(code, n_bars, datetime(2023, 1, 1))

    for cfg in (
        IndicatorConfig("rsi", {"period": 14}, ["rsi_14"]),
        IndicatorConfig("ema", {"period": 12}, ["ema_12"]),
    ):
        compute_indicator_for_code(code, cfg, incremental=False)
        n_bars += 5  # 每輪追加 5 根新 K 線
        _insert_klines(code, n_bars, datetime(2023, 1, 1))
        r = compute_indicator_for_code(code, cfg, incremental=True)
        assert r.status == "success"
        inc = _read_indicator_table(code, cfg)

        _drop_indicator_table(code, cfg)
        compute_indicator_for_code(code, cfg, incremental=False)
        full = _read_indicator_table(code, cfg)

        col = cfg.output_columns[0]
        # 只比對新增區間（舊行未被重寫，理論上本就一致）
        new_dates = sorted(full.keys())[-6:]
        for d in new_dates:
            if full[d][col] is None:
                continue
            assert abs(full[d][col] - inc[d][col]) < 1e-5, f"{cfg.name} {d} 未收斂"


def test_get_table_max_date_missing():
    assert _get_table_max_date(settings.db_path, "indicator_ghost_none_0000") is None
