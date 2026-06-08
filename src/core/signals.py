"""
實時交易信號引擎 — 基於內置策略在最後一根 K 線上的買賣信號
"""

import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import backtrader as bt
import numpy as np
import pandas as pd

from src.config import settings
from src.core.backtest import STRATEGIES, _get_prepared_df
from src.core.db import get_conn, load_daily_kline
from src.utils.logger import logger

_BT_LOOKBACK = 200
_MIN_BARS = 30
_CACHE_TTL_SEC = 300
_snapshot_cache: dict[tuple, tuple[float, list]] = {}
_cache_lock = threading.Lock()


def _cache_bucket() -> str:
    """按小時分桶，交易時段內复用快照。"""
    return datetime.now().strftime("%Y-%m-%d %H")


def _get_cached_snapshot(codes: list[str]) -> list[dict] | None:
    key = (tuple(sorted(codes)), _cache_bucket())
    with _cache_lock:
        entry = _snapshot_cache.get(key)
        if not entry:
            return None
        expires_at, payload = entry
        if time.time() > expires_at:
            _snapshot_cache.pop(key, None)
            return None
        return payload


def _set_cached_snapshot(codes: list[str], payload: list[dict]) -> None:
    key = (tuple(sorted(codes)), _cache_bucket())
    with _cache_lock:
        _snapshot_cache[key] = (time.time() + _CACHE_TTL_SEC, payload)


def _group_signals_by_code(raw: list[dict]) -> list[dict]:
    grouped: dict[str, list] = {}
    for s in raw:
        grouped.setdefault(s["code"], []).append(s)
    return [
        {"code": code, "signals": sigs, "strength": score_signal_strength(sigs)}
        for code, sigs in grouped.items()
    ]


class _LastBarOrderCapture(bt.Analyzer):
    """僅記錄最後一根 K 線當日成交的訂單，避免歷史成交誤判為今日信號。"""

    def __init__(self):
        self.signal_type = None

    def notify_order(self, order):
        if order.status != order.Completed:
            return
        try:
            ex_dt = bt.num2date(order.executed.dt).date()
            bar_dt = self.strategy.data.datetime.date(0)
            if ex_dt != bar_dt:
                return
        except Exception:
            return
        self.signal_type = "buy" if order.isbuy() else "sell"


def _run_bt_last_bar_signal(df: pd.DataFrame, strategy_cls) -> str:
    """在給定 OHLCV 上跑策略，返回 buy/sell/hold。"""
    if len(df) > _BT_LOOKBACK:
        df = df.tail(_BT_LOOKBACK).copy()
    cerebro = bt.Cerebro(stdstats=False)
    cerebro.adddata(bt.feeds.PandasData(dataname=df))
    cerebro.addstrategy(strategy_cls)
    cerebro.broker.setcash(100000)
    cerebro.broker.setcommission(commission=0.0)
    cerebro.addanalyzer(_LastBarOrderCapture, _name="lastbar")
    results = cerebro.run()
    strat = results[0]
    sig = strat.analyzers.lastbar.signal_type
    if sig in ("buy", "sell"):
        return sig
    return "hold"


class SignalEngine:
    """
    實時信號計算引擎。
    對監控列表中的每隻股票，用所有 19 種內置策略計算最新一根 K 線的買賣信號。
    """

    def __init__(self):
        # 策略權重（基於最近回測的夏普比率），初始等權
        self._strategy_weights: dict[str, float] = {name: 1.0 for name in STRATEGIES}

    def compute_signals(self, codes: list[str] = None) -> list[dict]:
        """
        計算指定股票列表的實時信號。
        返回: [{"code": "600519", "strategy": "macd", "signal": "buy", "price": 1800.0, ...}, ...]
        """
        if codes is None:
            codes = list(settings.watchlist)
        codes = [c for c in codes if c]
        if not codes:
            return []

        workers = min(
            max(1, getattr(settings, "multi_strategy_workers", 4)),
            len(codes),
            8,
        )
        all_signals: list[dict] = []

        if len(codes) == 1 or workers <= 1:
            for code in codes:
                try:
                    all_signals.extend(self._compute_single(code))
                except Exception as e:
                    logger.debug(f"信號計算失敗 {code}: {e}")
        else:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {pool.submit(self._compute_single, c): c for c in codes}
                for fut in as_completed(futures):
                    code = futures[fut]
                    try:
                        all_signals.extend(fut.result())
                    except Exception as e:
                        logger.debug(f"信號計算失敗 {code}: {e}")

        if all_signals:
            _save_signals(all_signals)

        return all_signals

    def _compute_single(self, code: str) -> list[dict]:
        """對單隻股票計算所有策略的信號"""
        try:
            bt_df = _get_prepared_df(code)
        except ValueError:
            return []
        if bt_df.empty or len(bt_df) < _MIN_BARS:
            return []

        latest_price = float(bt_df.iloc[-1]["Close"])
        bar_date = bt_df.index[-1]
        triggered_at = (
            bar_date.strftime("%Y-%m-%d %H:%M:%S")
            if hasattr(bar_date, "strftime")
            else str(bar_date)[:19]
        )

        signals = []
        for strategy_name, strategy_cls in STRATEGIES.items():
            try:
                signal_type = _run_bt_last_bar_signal(bt_df, strategy_cls)
                weight = self._strategy_weights.get(strategy_name, 1.0)
                if signal_type == "hold":
                    strength = 0.0
                else:
                    base = 50.0 if signal_type == "buy" else -50.0
                    strength = round(base * weight, 2)
                signals.append(
                    {
                        "code": code,
                        "strategy": strategy_name,
                        "signal": signal_type,
                        "price": latest_price,
                        "strength": strength,
                        "params": "{}",
                        "triggered_at": triggered_at,
                    }
                )
            except Exception as e:
                logger.debug(f"策略 {strategy_name} 在 {code} 上失敗: {e}")

        return signals

    def update_weights_from_backtest(self, codes: list[str] | None = None):
        """用 watchlist 最近回測夏普均值更新策略權重。"""
        from src.core.db import get_backtest_history

        if codes is None:
            codes = list(settings.watchlist)
        codes = [c for c in codes if c][:8]
        if not codes:
            return

        for strategy_name in STRATEGIES:
            sharpes: list[float] = []
            for code in codes:
                try:
                    history = get_backtest_history(
                        code=code,
                        strategy=strategy_name,
                        limit=3,
                    )
                    sharpes.extend(
                        [float(h.get("sharpe_ratio") or 0) for h in history if h]
                    )
                except Exception:
                    continue
            if sharpes:
                avg_sharpe = float(np.mean(sharpes))
                self._strategy_weights[strategy_name] = max(
                    0.2,
                    min(3.0, 1.0 + avg_sharpe),
                )

    @property
    def weights(self) -> dict:
        """返回當前策略權重"""
        return dict(self._strategy_weights)


def score_signal_strength(signals: list[dict]) -> float:
    """
    計算信號強度綜合分數（-100 ~ +100）。
    僅用 buy/sell 計算方向與強度；hold 不稀釋一致性。
    """
    if not signals:
        return 0.0

    active = [s for s in signals if s.get("signal") in ("buy", "sell")]
    if not active:
        return 0.0

    buy_count = sum(1 for s in active if s["signal"] == "buy")
    sell_count = len(active) - buy_count
    total_strength = sum(float(s.get("strength") or 0) for s in active)

    max_possible = len(active) * 50.0
    normalized = (total_strength / max_possible) * 100 if max_possible else 0.0

    agreement = max(buy_count, sell_count) / len(active)
    normalized *= 0.5 + 0.5 * agreement

    return round(max(-100.0, min(100.0, normalized)), 2)


def get_historical_signals(
    code: str,
    start_date: str = None,
    end_date: str = None,
    strategy: str = None,
    days: int = 30,
) -> list[dict]:
    """
    獲取歷史信號記錄。
    如果數據庫中沒有，則回放歷史 K 線數據重新計算。
    """
    # 先查數據庫
    existing = _load_signals_from_db(code, start_date, end_date, strategy, days)
    if existing:
        return existing

    # 數據庫中沒有，回放計算
    return _replay_historical_signals(code, days, strategy)


def _load_signals_from_db(
    code: str,
    start_date: str = None,
    end_date: str = None,
    strategy: str = None,
    days: int = 30,
) -> list[dict]:
    """從數據庫讀取歷史信號"""
    sql = "SELECT * FROM signal_log WHERE code = ?"
    params = [code]

    if start_date:
        sql += " AND triggered_at >= ?"
        params.append(start_date)
    if end_date:
        sql += " AND triggered_at <= ?"
        params.append(end_date)
    if strategy:
        sql += " AND strategy = ?"
        params.append(strategy)

    sql += " ORDER BY triggered_at DESC LIMIT ?"
    # 限制返回量：每個策略每天最多 1 條，乘以天數
    limit = days * len(STRATEGIES) * 2
    params.append(limit)

    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, params).fetchall()

    return [dict(r) for r in rows]


def _replay_historical_signals(
    code: str, days: int = 30, strategy: str = None
) -> list[dict]:
    """
    回放歷史 K 線，計算每天的策略信號。
    使用滑動窗口：對每一天，用截止到該天的數據運行策略。
    """
    df = load_daily_kline(code)
    if df.empty or len(df) < 60:
        return []

    # 只回放最近 N 天
    df = df.tail(min(days + 60, len(df)))

    strategies_to_run = {strategy: STRATEGIES[strategy]} if strategy else STRATEGIES
    all_signals = []

    # 取最後 days 根 K 線作為回放目標
    replay_bars = df.tail(days)

    for _, bar in replay_bars.iterrows():
        bar_date = str(bar["date"])
        bar_price = float(bar["close"])

        for strat_name, strat_cls in strategies_to_run.items():
            try:
                # 用截止到當天的數據（含當天）
                idx = df[df["date"] == bar_date].index
                if len(idx) == 0:
                    continue
                end_idx = idx[0]
                window = df.iloc[max(0, end_idx - 199) : end_idx + 1]

                if len(window) < 30:
                    continue

                bt_df = window.copy()
                bt_df["date"] = pd.to_datetime(bt_df["date"])
                bt_df = bt_df.set_index("date")
                bt_df = bt_df[["open", "high", "low", "close", "volume"]]
                bt_df.columns = ["Open", "High", "Low", "Close", "Volume"]

                data = bt.feeds.PandasData(dataname=bt_df)
                cerebro = bt.Cerebro()
                cerebro.adddata(data)
                cerebro.addstrategy(strat_cls)
                cerebro.broker.setcash(100000)
                cerebro.broker.setcommission(commission=0.0)

                cerebro.addanalyzer(_LastBarOrderCapture, _name="lastbar")
                results = cerebro.run()
                sig = results[0].analyzers.lastbar.signal_type or "hold"
                all_signals.append(
                    {
                        "code": code,
                        "strategy": strat_name,
                        "signal": sig,
                        "price": bar_price,
                        "strength": (
                            50.0 if sig == "buy" else (-50.0 if sig == "sell" else 0.0)
                        ),
                        "params": "{}",
                        "triggered_at": bar_date,
                    }
                )
            except Exception as e:
                logger.debug(f"回放信號失敗 {code}/{strat_name}/{bar_date}: {e}")

    # 持久化到數據庫
    if all_signals:
        _save_signals(all_signals)

    return all_signals


def _save_signals(signals: list[dict]):
    """批量保存信號；僅持久化 buy/sell，減少 hold 刷屏。"""
    rows = [s for s in signals if s.get("signal") in ("buy", "sell")]
    if not rows:
        return
    try:
        with get_conn() as conn:
            conn.executemany(
                """INSERT INTO signal_log (code, strategy, signal, price, strength, params, triggered_at, user_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    (
                        s["code"],
                        s["strategy"],
                        s["signal"],
                        s.get("price"),
                        s.get("strength", 0),
                        s.get("params", "{}"),
                        s["triggered_at"],
                        s.get("user_id"),
                    )
                    for s in rows
                ],
            )
        logger.debug(f"保存 {len(rows)} 條信號記錄（buy/sell）")
    except Exception as e:
        logger.debug(f"保存信號失敗: {e}")


def get_current_signals_for_codes(codes: list[str] = None) -> list[dict]:
    """獲取最新信號快照；DB 無記錄時走引擎實時計算。"""
    if codes is None:
        codes = list(settings.watchlist)
    codes = [c for c in codes if c]

    cached = _get_cached_snapshot(codes)
    if cached is not None:
        return cached

    by_code: dict[str, list[dict]] = {c: [] for c in codes}
    for code in codes:
        sql = """SELECT * FROM signal_log
                 WHERE code = ? AND triggered_at = (
                     SELECT MAX(triggered_at) FROM signal_log WHERE code = ?
                 )"""
        with get_conn() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(sql, (code, code)).fetchall()
        if rows:
            by_code[code] = [dict(r) for r in rows]

    missing = [c for c in codes if not by_code.get(c)]
    if missing:
        engine = SignalEngine()
        engine.update_weights_from_backtest(missing)
        for s in engine.compute_signals(missing):
            by_code.setdefault(s["code"], []).append(s)

    result = []
    for code in codes:
        sigs = by_code.get(code, [])
        result.append(
            {
                "code": code,
                "signals": sigs,
                "strength": score_signal_strength(sigs),
                "updated_at": sigs[0]["triggered_at"] if sigs else None,
            }
        )

    _set_cached_snapshot(codes, result)
    return result


def compute_and_push_signals(
    engine: SignalEngine, codes: list[str] = None
) -> list[dict]:
    """
    計算信號並返回推送數據（用於 WebSocket / API）。
    返回格式: [{"code": "600519", "signals": [...], "strength": 75.0}, ...]
    """
    if codes is None:
        codes = list(settings.watchlist)
    codes = [c for c in codes if c]

    cached = _get_cached_snapshot(codes)
    if cached is not None:
        return cached

    engine.update_weights_from_backtest(codes)
    raw_signals = engine.compute_signals(codes)
    result = _group_signals_by_code(raw_signals)
    _set_cached_snapshot(codes, result)
    return result


# ============================================================
# 信號增強功能 — 回測驗證、熱力圖、綜合排名
# ============================================================


def backtest_signals(
    codes: list[str] = None,
    strategies: list[str] = None,
    days: int = 250,
) -> dict:
    """
    信號回測驗證 — 回放歷史信號，計算跟隨信號交易的實際收益。

    對每個歷史信號，計算前向收益（1d, 3d, 5d, 10d），
    並按策略統計準確率。

    參數:
        codes: 股票代碼列表，None 時用 watchlist
        strategies: 策略名稱列表，None 時用所有策略
        days: 回測天數，默認 250 天

    返回:
        {
            "by_strategy": {
                "macd": {
                    "total_signals": 120,
                    "buy_signals": 60,
                    "sell_signals": 60,
                    "accuracy_1d": 0.55,  # 1 天後方向正確率
                    "accuracy_3d": 0.53,
                    "accuracy_5d": 0.52,
                    "accuracy_10d": 0.50,
                    "avg_return_1d": 0.3,  # 平均 1 天收益%
                    "avg_return_3d": 0.5,
                    "avg_return_5d": 0.8,
                    "avg_return_10d": 1.2,
                    "buy_accuracy_1d": 0.58,  # 買入信號準確率
                    "sell_accuracy_1d": 0.52,  # 賣出信號準確率
                },
                ...
            },
            "overall": { ... },
            "signal_details": [ ... ]
        }
    """
    if codes is None:
        codes = settings.watchlist

    if strategies is None:
        strategies = list(STRATEGIES.keys())

    # 按策略統計
    strategy_stats: dict[str, dict] = {}
    for strat in strategies:
        strategy_stats[strat] = {
            "total_signals": 0,
            "buy_signals": 0,
            "sell_signals": 0,
            # 前向收益累計（用於計算平均值）
            "fwd_returns": {"1d": [], "3d": [], "5d": [], "10d": []},
            # 方向正確次數
            "correct_dir": {"1d": 0, "3d": 0, "5d": 0, "10d": 0},
            # 買入/賣出分開統計
            "buy_returns": {"1d": [], "3d": [], "5d": [], "10d": []},
            "sell_returns": {"1d": [], "3d": [], "5d": [], "10d": []},
        }

    all_details = []

    for code in codes:
        try:
            # 獲取歷史 K 線
            df = load_daily_kline(code)
            if df.empty or len(df) < days + 60:
                continue

            # 只取最近 days 天
            df = df.tail(days + 60).copy()
            df = df.reset_index(drop=True)

            # 獲取歷史信號
            signals = get_historical_signals(code=code, days=days)

            if not signals:
                continue

            # 建立日期到索引的映射
            date_to_idx = {}
            for idx, row in df.iterrows():
                date_str = str(row["date"])[:10]
                date_to_idx[date_str] = idx

            # 對每個信號計算前向收益
            for sig in signals:
                strat_name = sig.get("strategy", "")
                if strat_name not in strategy_stats:
                    continue

                signal_type = sig.get("signal", "hold")
                if signal_type == "hold":
                    continue

                sig_date = str(sig.get("triggered_at", ""))[:10]
                sig_idx = date_to_idx.get(sig_date)
                if sig_idx is None:
                    continue

                stats = strategy_stats[strat_name]
                stats["total_signals"] += 1
                if signal_type == "buy":
                    stats["buy_signals"] += 1
                else:
                    stats["sell_signals"] += 1

                # 計算前向收益
                for days_fwd, key in [(1, "1d"), (3, "3d"), (5, "5d"), (10, "10d")]:
                    fwd_idx = sig_idx + days_fwd
                    if fwd_idx >= len(df):
                        continue

                    entry_price = float(df.iloc[sig_idx]["close"])
                    exit_price = float(df.iloc[fwd_idx]["close"])

                    if entry_price <= 0:
                        continue

                    # 買入信號: 前向收益 = (exit - entry) / entry
                    # 賣出信號: 前向收益 = (entry - exit) / entry（做空方向）
                    if signal_type == "buy":
                        fwd_return = (exit_price - entry_price) / entry_price * 100
                    else:
                        fwd_return = (entry_price - exit_price) / entry_price * 100

                    stats["fwd_returns"][key].append(fwd_return)

                    # 方向正確 = 前向收益 > 0
                    if fwd_return > 0:
                        stats["correct_dir"][key] += 1

                    # 分買賣統計
                    if signal_type == "buy":
                        stats["buy_returns"][key].append(fwd_return)
                    else:
                        stats["sell_returns"][key].append(fwd_return)

                    # 記錄明細（只保留最近 500 條）
                    if len(all_details) < 500:
                        all_details.append(
                            {
                                "code": code,
                                "strategy": strat_name,
                                "signal": signal_type,
                                "date": sig_date,
                                "price": float(sig.get("price", 0)),
                                f"return_{key}": round(fwd_return, 2),
                            }
                        )

        except Exception as e:
            logger.debug(f"信號回測失敗 {code}: {e}")

    # 匯總結果
    by_strategy = {}
    total_signals = 0
    total_correct = {"1d": 0, "3d": 0, "5d": 0, "10d": 0}
    total_count = {"1d": 0, "3d": 0, "5d": 0, "10d": 0}

    for strat_name, stats in strategy_stats.items():
        n = stats["total_signals"]
        if n == 0:
            continue

        total_signals += n
        strat_result = {
            "total_signals": n,
            "buy_signals": stats["buy_signals"],
            "sell_signals": stats["sell_signals"],
        }

        for key in ["1d", "3d", "5d", "10d"]:
            returns = stats["fwd_returns"][key]
            correct = stats["correct_dir"][key]
            count = len(returns)

            total_correct[key] += correct
            total_count[key] += count

            strat_result[f"accuracy_{key}"] = (
                round(correct / count, 4) if count > 0 else 0
            )
            strat_result[f"avg_return_{key}"] = (
                round(np.mean(returns), 4) if returns else 0
            )

            # 買入/賣出分開的準確率
            buy_rets = stats["buy_returns"][key]
            sell_rets = stats["sell_returns"][key]
            if buy_rets:
                buy_correct = sum(1 for r in buy_rets if r > 0)
                strat_result[f"buy_accuracy_{key}"] = round(
                    buy_correct / len(buy_rets), 4
                )
            else:
                strat_result[f"buy_accuracy_{key}"] = 0
            if sell_rets:
                sell_correct = sum(1 for r in sell_rets if r > 0)
                strat_result[f"sell_accuracy_{key}"] = round(
                    sell_correct / len(sell_rets), 4
                )
            else:
                strat_result[f"sell_accuracy_{key}"] = 0

        by_strategy[strat_name] = strat_result

    # 整體統計
    overall = {"total_signals": total_signals}
    for key in ["1d", "3d", "5d", "10d"]:
        overall[f"accuracy_{key}"] = (
            round(total_correct[key] / total_count[key], 4)
            if total_count[key] > 0
            else 0
        )

    return {
        "by_strategy": by_strategy,
        "overall": overall,
        "signal_details": all_details,
    }


def signal_heatmap(codes: list[str] = None, days: int = 30) -> dict:
    """
    信號熱力圖 — 生成 codes × dates × signal_strength 的矩陣數據。

    每個單元格為綜合信號強度分數（-100 到 +100）。
    正值越深表示買入信號越強，負值越深表示賣出信號越強。

    參數:
        codes: 股票代碼列表，None 時用 watchlist
        days: 歷史天數，默認 30 天

    返回:
        {
            "codes": ["600519", "000001", ...],
            "dates": ["2024-01-15", "2024-01-16", ...],
            "matrix": [[score, ...], ...],  # codes × dates
            "max_score": 最大分數,
            "min_score": 最小分數,
        }
    """
    if codes is None:
        codes = settings.watchlist

    all_dates = set()
    # 先收集所有日期
    for code in codes:
        try:
            df = load_daily_kline(code)
            if not df.empty:
                recent = df.tail(days)
                for _, row in recent.iterrows():
                    all_dates.add(str(row["date"])[:10])
        except Exception:
            pass

    if not all_dates:
        return {
            "codes": codes,
            "dates": [],
            "matrix": [],
            "max_score": 0,
            "min_score": 0,
        }

    sorted_dates = sorted(all_dates)
    # 限制日期數量
    sorted_dates = sorted_dates[-days:]

    # 為每隻股票計算每天的信號強度
    matrix = []
    max_score = -100
    min_score = 100

    for code in codes:
        row_scores = []

        # 獲取歷史信號
        try:
            signals = get_historical_signals(code=code, days=days)
        except Exception:
            signals = []

        # 按日期分組信號
        signals_by_date: dict[str, list] = {}
        for sig in signals:
            sig_date = str(sig.get("triggered_at", ""))[:10]
            if sig_date not in signals_by_date:
                signals_by_date[sig_date] = []
            signals_by_date[sig_date].append(sig)

        for date in sorted_dates:
            day_signals = signals_by_date.get(date, [])
            if day_signals:
                score = score_signal_strength(day_signals)
            else:
                score = 0.0

            row_scores.append(round(score, 1))
            max_score = max(max_score, score)
            min_score = min(min_score, score)

        matrix.append(row_scores)

    return {
        "codes": codes,
        "dates": sorted_dates,
        "matrix": matrix,
        "max_score": round(max_score, 1),
        "min_score": round(min_score, 1),
    }


def composite_signal_ranking(codes: list[str] = None) -> list[dict]:
    """
    綜合信號排名 — 按複合信號強度對所有股票排名。

    聚合所有策略的信號，並根據近期策略準確率加權。

    參數:
        codes: 股票代碼列表，None 時用所有有數據的股票

    返回:
        排名列表，每個元素:
            {
                "rank": 排名,
                "code": 股票代碼,
                "composite_score": 綜合分數 (-100 ~ +100),
                "recommendation": "強烈買入" / "買入" / "持有" / "賣出" / "強烈賣出",
                "signal_count": 有效信號數,
                "strategy_details": {
                    "macd": {"signal": "buy", "strength": 50, "weight": 0.15},
                    ...
                },
                "latest_price": 最新價格,
                "updated_at": 更新時間
            }
    """
    if codes is None:
        from src.core.db import load_all_codes

        try:
            codes = load_all_codes()
        except Exception:
            codes = list(settings.watchlist)

    codes = [c for c in (codes or []) if c]
    if not codes:
        return []

    engine = SignalEngine()
    engine.update_weights_from_backtest(codes[:8])
    strategy_weights = engine.weights
    accuracy_weights = _compute_accuracy_weights(codes[:8])

    raw_signals = engine.compute_signals(codes)
    grouped: dict[str, list[dict]] = {}
    for s in raw_signals:
        grouped.setdefault(s["code"], []).append(s)

    rankings = []
    for code in codes:
        try:
            code_signals = grouped.get(code, [])
            if not code_signals:
                continue

            weighted_sum = 0.0
            weight_total = 0.0
            strategy_details = {}

            for sig in code_signals:
                strat_name = sig.get("strategy", "")
                strength = float(sig.get("strength") or 0)
                signal_type = sig.get("signal", "hold")
                if signal_type == "hold":
                    continue

                combined_weight = strategy_weights.get(
                    strat_name, 1.0
                ) * accuracy_weights.get(strat_name, 1.0)
                weighted_sum += strength * combined_weight
                weight_total += abs(combined_weight)
                strategy_details[strat_name] = {
                    "signal": signal_type,
                    "strength": round(strength, 1),
                    "weight": round(combined_weight, 3),
                }

            composite_score = (
                max(-100, min(100, weighted_sum / weight_total))
                if weight_total > 0
                else 0.0
            )

            if composite_score > 50:
                recommendation = "強烈買入"
            elif composite_score > 20:
                recommendation = "買入"
            elif composite_score > -20:
                recommendation = "持有"
            elif composite_score > -50:
                recommendation = "賣出"
            else:
                recommendation = "強烈賣出"

            rankings.append(
                {
                    "code": code,
                    "composite_score": round(composite_score, 1),
                    "recommendation": recommendation,
                    "signal_count": len(code_signals),
                    "strategy_details": strategy_details,
                    "latest_price": code_signals[0].get("price", 0),
                    "updated_at": code_signals[0].get("triggered_at"),
                }
            )

        except Exception as e:
            logger.debug(f"綜合排名計算失敗 {code}: {e}")

    # 按綜合分數排序（買入信號強的在前）
    rankings.sort(key=lambda x: x["composite_score"], reverse=True)

    # 添加排名
    for i, r in enumerate(rankings):
        r["rank"] = i + 1

    return rankings


def _compute_accuracy_weights(codes: list[str]) -> dict[str, float]:
    """
    從回測歷史估算策略準確率權重（輕量，不跑完整信號回測）。
    映射到 [0.5, 2.0]。
    """
    from src.core.db import get_backtest_history

    weights = {name: 1.0 for name in STRATEGIES}
    for strat_name in STRATEGIES:
        win_rates: list[float] = []
        for code in codes:
            try:
                history = get_backtest_history(
                    code=code,
                    strategy=strat_name,
                    limit=5,
                )
                for h in history or []:
                    wr = h.get("win_rate_pct")
                    if wr is not None:
                        win_rates.append(float(wr) / 100.0)
            except Exception:
                continue
        if win_rates:
            acc = float(np.mean(win_rates))
            weights[strat_name] = max(0.5, min(2.0, 1.0 + (acc - 0.5) * 4))
    return weights
